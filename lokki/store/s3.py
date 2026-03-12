"""S3 store implementation for transient data."""

from __future__ import annotations

import gzip
import json
import os
import pickle
from typing import TYPE_CHECKING, Any, cast

from botocore.exceptions import ClientError

from lokki._aws import get_s3_client
from lokki.store.protocol import TransientStore

if TYPE_CHECKING:
    from collections.abc import Sequence


class S3Store(TransientStore):
    """S3-based store implementing TransientStore interface.

    Bucket is read from LOKKI_ARTIFACT_BUCKET environment variable.
    """

    def __init__(self) -> None:
        self.bucket = os.environ.get("LOKKI_ARTIFACT_BUCKET", "")
        if not self.bucket:
            raise ValueError(
                "LOKKI_ARTIFACT_BUCKET environment variable not set. "
                "This should be set in the Lambda/Batch container environment."
            )
        self._client = get_s3_client()

    def _make_key(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> str:
        return f"lokki/{flow_name}/runs/{run_id}/{step_name}/{filename}"

    def write(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        obj: Any,
        input_hash: str | None = None,
    ) -> str:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))

        if input_hash:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                Tagging="input_hash=" + input_hash,
            )
        else:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

        return f"s3://{self.bucket}/{key}"

    def get_input_hash(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> str | None:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        try:
            response = self._client.get_object_tagging(
                Bucket=self.bucket,
                Key=key,
            )
            for tag in response.get("TagSet", []):
                if tag["Key"] == "input_hash":
                    return cast(str, tag["Value"])
            return None
        except self._client.exceptions.NoSuchKey:
            return None

    def read(self, location: str) -> Any:
        bucket, key = self._parse_url(location)
        data = self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return pickle.loads(gzip.decompress(data))

    def exists(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> bool:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def read_cached(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> Any:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        data = self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return pickle.loads(gzip.decompress(data))

    def write_manifest(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        items: Sequence[Any],
    ) -> str:
        key = self._make_key(flow_name, run_id, step_name, "map_manifest.json")
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(items),
            ContentType="application/json",
        )
        return f"s3://{self.bucket}/{key}"

    def cleanup(self) -> None:
        pass

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> str:
        key = f"{flow_name}/{run_id}/{step_name}/{filename}"
        return f"s3://{self.bucket}/{key}"

    @staticmethod
    def _parse_url(url: str) -> tuple[str, str]:
        if not url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL: {url}. Must start with 's3://'")
        parts = url[5:].split("/", 1)
        bucket = parts[0]
        if not bucket:
            raise ValueError(f"Invalid S3 URL: {url}. Missing bucket")
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key
