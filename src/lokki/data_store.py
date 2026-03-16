"""Data store implementations for Lokki pipeline library."""

import gzip
import io
import os
import pickle
import tempfile
import uuid
from typing import Any

from .models import DataStoreConfig, StepArtifact

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = RuntimeError  # type: ignore[assignment,misc]
    NoCredentialsError = RuntimeError  # type: ignore[assignment,misc]


class DataStore:
    """Abstract base class for pipeline data storage backends."""

    def __init__(self, config: DataStoreConfig | None = None) -> None:
        self.config = config or DataStoreConfig()
        self.artifacts: dict[str, StepArtifact] = {}

    def store(self, key: str, data: Any, metadata: dict[str, Any] | None = None) -> str:
        """Store data and return storage key."""
        raise NotImplementedError

    def retrieve(self, key: str) -> Any:
        """Retrieve data by storage key."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check if data exists for given key."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Clean up storage resources."""
        raise NotImplementedError

    def store_step_result(
        self, step_name: str, result: Any, metadata: dict[str, Any] | None = None
    ) -> StepArtifact:
        """Store a step result and return artifact metadata."""
        artifact_id = str(uuid.uuid4())
        storage_key = self.store(artifact_id, result, metadata)

        artifact = StepArtifact(
            step_name=step_name,
            artifact_id=artifact_id,
            storage_key=storage_key,
            metadata=metadata or {},
        )

        self.artifacts[artifact_id] = artifact
        return artifact

    def retrieve_step_result(self, artifact: StepArtifact) -> Any:
        """Retrieve a step result from artifact metadata."""
        return self.retrieve(artifact.storage_key)


class TempFileDataStore(DataStore):
    """Default datastore backend using temporary files with pickle and gzip."""

    def __init__(self, config: DataStoreConfig | None = None) -> None:
        super().__init__(config)
        self.temp_files: dict[str, str] = {}
        self._temp_dir: str | None = None

    @property
    def temp_dir(self) -> str:
        """Get or create temporary directory."""
        if self._temp_dir is None:
            if self.config.temp_dir:
                os.makedirs(self.config.temp_dir, exist_ok=True)
                self._temp_dir = self.config.temp_dir
            else:
                self._temp_dir = tempfile.mkdtemp(prefix="lokki_")
        return self._temp_dir

    def store(self, key: str, data: Any, metadata: dict[str, Any] | None = None) -> str:
        """Store data in a compressed pickle file."""
        fd, temp_path = tempfile.mkstemp(
            suffix=".pkl.gz",
            prefix=f"lokki_{key}_",
            dir=self.temp_dir,
        )

        try:
            with os.fdopen(fd, "wb") as temp_file:
                with gzip.GzipFile(
                    fileobj=temp_file, compresslevel=self.config.compression_level
                ) as gz_file:
                    pickle.dump(
                        {
                            "data": data,
                            "metadata": metadata or {},
                            "key": key,
                        },
                        gz_file,
                    )

            self.temp_files[key] = temp_path
            return temp_path

        except Exception as e:
            try:
                os.close(fd)
                os.unlink(temp_path)
            except Exception:
                pass
            raise RuntimeError(f"Failed to store data for key '{key}': {e}") from e

    def retrieve(self, key: str) -> Any:
        """Retrieve data from compressed pickle file."""
        if key not in self.temp_files:
            raise KeyError(f"No data found for key '{key}'")

        file_path = self.temp_files[key]

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data file not found: {file_path}")

        try:
            with open(file_path, "rb") as f:
                with gzip.GzipFile(fileobj=f) as gz_file:
                    stored_data = pickle.load(gz_file)
                    return stored_data["data"]

        except Exception as e:
            raise RuntimeError(f"Failed to retrieve data for key '{key}': {e}") from e

    def exists(self, key: str) -> bool:
        """Check if data exists for given key."""
        return key in self.temp_files and os.path.exists(self.temp_files[key])

    def cleanup(self) -> None:
        """Remove all temporary files."""
        for _key, file_path in self.temp_files.items():
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Warning: Could not clean up file {file_path}: {e}")

        self.temp_files.clear()

        if self._temp_dir and not self.config.temp_dir:
            try:
                os.rmdir(self._temp_dir)
            except OSError:
                pass

    def __del__(self) -> None:
        """Cleanup on object destruction."""
        if self.config.cleanup_on_exit:
            self.cleanup()


class S3Config(DataStoreConfig):
    """Configuration for S3 datastore backend."""

    def __init__(
        self,
        bucket_name: str = "",
        key_prefix: str = "lokki/",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        temp_dir: str | None = None,
        compression_level: int = 6,
        cleanup_on_exit: bool = True,
    ) -> None:
        super().__init__(temp_dir, compression_level, cleanup_on_exit)
        self.bucket_name = bucket_name
        self.key_prefix = key_prefix
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.region_name = region_name
        self.endpoint_url = endpoint_url


class S3DataStore(DataStore):
    """S3-based datastore backend for distributed pipeline execution."""

    def __init__(self, config: S3Config) -> None:
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for S3DataStore. Install with: pip install boto3"
            )

        super().__init__(config)
        self.s3_config = config

        if not config.bucket_name:
            raise ValueError("bucket_name must be specified for S3DataStore")

        session_kwargs = {
            "region_name": config.region_name,
        }

        if config.aws_access_key_id:
            session_kwargs["aws_access_key_id"] = config.aws_access_key_id
        if config.aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = config.aws_secret_access_key
        if config.aws_session_token:
            session_kwargs["aws_session_token"] = config.aws_session_token

        self.session = boto3.Session(**session_kwargs)

        client_kwargs = {}
        if config.endpoint_url:
            client_kwargs["endpoint_url"] = config.endpoint_url

        self.s3_client = self.session.client("s3", **client_kwargs)
        self.bucket_name = config.bucket_name
        self.key_prefix = config.key_prefix

        self._verify_bucket_access()

    def _verify_bucket_access(self) -> None:
        """Verify that we can access the S3 bucket."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except Exception as e:
            error_code: str | None = None
            response = getattr(e, "response", None)
            if response and "Error" in response:
                error_code = response["Error"].get("Code")
            if error_code == "404":
                raise ValueError(
                    f"S3 bucket '{self.bucket_name}' does not exist"
                ) from e
            elif error_code == "403":
                raise ValueError(
                    f"Access denied to S3 bucket '{self.bucket_name}'"
                ) from e
            elif isinstance(e, NoCredentialsError):
                raise ValueError(
                    "AWS credentials not found. Please configure AWS credentials."
                ) from e
            raise

    def _get_s3_key(self, key: str) -> str:
        """Get full S3 key with prefix."""
        return f"{self.key_prefix}{key}.pkl.gz"

    def store(self, key: str, data: Any, metadata: dict[str, Any] | None = None) -> str:
        """Store data in S3 as compressed pickle."""
        s3_key = self._get_s3_key(key)

        buffer = io.BytesIO()
        with gzip.GzipFile(
            fileobj=buffer, mode="wb", compresslevel=self.config.compression_level
        ) as gz_file:
            pickle.dump(
                {
                    "data": data,
                    "metadata": metadata or {},
                    "key": key,
                },
                gz_file,
            )

        buffer.seek(0)

        s3_metadata = {
            "lokki-key": key,
            "lokki-timestamp": str(uuid.uuid4()),
        }
        if metadata:
            for k, v in metadata.items():
                safe_key = f"lokki-meta-{k.replace('_', '-').lower()}"
                s3_metadata[safe_key] = str(v)[:1000]

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=buffer.getvalue(),
            Metadata=s3_metadata,
            ContentEncoding="gzip",
            ContentType="application/octet-stream",
        )

        return s3_key

    def retrieve(self, key: str) -> Any:
        """Retrieve data from S3."""
        s3_key = self._get_s3_key(key)

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)

            with gzip.GzipFile(fileobj=response["Body"]) as gz_file:
                stored_data = pickle.load(gz_file)
                return stored_data["data"]

        except Exception as e:
            error_code: str | None = None
            resp = getattr(e, "response", None)
            if resp and "Error" in resp:
                error_code = resp["Error"].get("Code")
            if error_code == "NoSuchKey":
                raise KeyError(f"No data found for key '{key}' in S3") from e
            raise RuntimeError(
                f"Failed to retrieve data from S3 for key '{key}': {e}"
            ) from e

    def exists(self, key: str) -> bool:
        """Check if data exists in S3."""
        s3_key = self._get_s3_key(key)

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except Exception as e:
            error_code: str | None = None
            resp = getattr(e, "response", None)
            if resp and "Error" in resp:
                error_code = resp["Error"].get("Code")
            if error_code == "404":
                return False
            raise RuntimeError(
                f"Error checking existence of key '{key}' in S3: {e}"
            ) from e

    def cleanup(self) -> None:
        """Clean up S3 objects (optional)."""
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.key_prefix)

            objects_to_delete = []
            for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        objects_to_delete.append({"Key": obj["Key"]})

            if objects_to_delete:
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i : i + 1000]
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": batch},
                    )

        except Exception as e:
            print(f"Warning: Could not clean up S3 objects: {e}")
