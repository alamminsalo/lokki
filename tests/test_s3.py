"""Unit tests for S3Store (TransientStore)."""

import gzip
import os
import pickle

import boto3
import pytest
from moto import mock_aws

from lokki.store import S3Store


class TestS3StoreInit:
    """Tests for S3Store initialization."""

    def test_init_requires_env_var(self):
        """Test that S3Store raises error when LOKKI_ARTIFACT_BUCKET is not set."""
        original = os.environ.get("LOKKI_ARTIFACT_BUCKET")
        try:
            os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)
            with pytest.raises(ValueError, match="LOKKI_ARTIFACT_BUCKET"):
                S3Store()
        finally:
            if original:
                os.environ["LOKKI_ARTIFACT_BUCKET"] = original

    @mock_aws
    def test_init_with_env_var(self):
        """Test that S3Store reads bucket from environment."""
        os.environ["LOKKI_ARTIFACT_BUCKET"] = "test-bucket"
        try:
            store = S3Store()
            assert store.bucket == "test-bucket"
        finally:
            os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)


class TestParseUrl:
    """Tests for _parse_url function."""

    def test_parse_valid_url(self) -> None:
        """Test parsing a valid s3:// URL."""
        bucket, key = S3Store._parse_url("s3://my-bucket/path/to/file.txt")
        assert bucket == "my-bucket"
        assert key == "path/to/file.txt"

    def test_parse_url_with_multiple_slashes(self) -> None:
        """Test parsing URL with multiple path segments."""
        bucket, key = S3Store._parse_url("s3://bucket/a/b/c/d.txt")
        assert bucket == "bucket"
        assert key == "a/b/c/d.txt"

    def test_parse_url_root(self) -> None:
        """Test parsing URL with only bucket."""
        bucket, key = S3Store._parse_url("s3://my-bucket")
        assert bucket == "my-bucket"
        assert key == ""

    def test_parse_url_missing_protocol(self) -> None:
        """Test that missing s3:// protocol raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            S3Store._parse_url("my-bucket/path/to/file.txt")

    def test_parse_url_empty_bucket(self) -> None:
        """Test that empty bucket raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            S3Store._parse_url("s3:///path/to/file.txt")

    def test_parse_url_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            S3Store._parse_url("")


class TestS3StoreWrite:
    """Tests for S3Store.write method."""

    @mock_aws
    def test_write_returns_s3_url(self, monkeypatch) -> None:
        """Test that write returns the s3:// URL."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "my-bucket")

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-bucket")

        store = S3Store()
        result = store.write(
            flow_name="my-flow",
            run_id="run-123",
            step_name="my-step",
            obj={"key": "value"},
        )

        assert result == "s3://my-bucket/lokki/my-flow/run-123/my-step/output.pkl.gz"

    @mock_aws
    def test_write_serializes_with_gzip_pickle(self, monkeypatch) -> None:
        """Test that write uses gzip and pickle."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "bucket")

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store()
        test_obj = {"data": [1, 2, 3]}
        store.write(
            flow_name="test-flow",
            run_id="run-1",
            step_name="test-step",
            obj=test_obj,
        )

        response = s3.get_object(
            Bucket="bucket", Key="lokki/test-flow/run-1/test-step/output.pkl.gz"
        )
        body = response["Body"].read()

        uncompressed = gzip.decompress(body)
        unpickled = pickle.loads(uncompressed)
        assert unpickled == test_obj


class TestS3StoreRead:
    """Tests for S3Store.read method."""

    @mock_aws
    def test_read_deserializes_object(self, monkeypatch) -> None:
        """Test that read deserializes the object from S3."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "my-bucket")

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-bucket")

        test_obj = {"result": "success"}
        serialized = gzip.compress(
            pickle.dumps(test_obj, protocol=pickle.HIGHEST_PROTOCOL)
        )
        s3.put_object(Bucket="my-bucket", Key="path/to/obj.pkl.gz", Body=serialized)

        store = S3Store()
        result = store.read("s3://my-bucket/path/to/obj.pkl.gz")

        assert result == test_obj


class TestS3StoreWriteManifest:
    """Tests for S3Store.write_manifest method."""

    @mock_aws
    def test_write_manifest(self, monkeypatch) -> None:
        """Test write_manifest creates JSON file."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "bucket")

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store()
        items = [{"key": "value1"}, {"key": "value2"}]
        result = store.write_manifest(
            flow_name="my-flow",
            run_id="run-123",
            step_name="map-step",
            items=items,
        )

        assert result == "s3://bucket/lokki/my-flow/run-123/map-step/map_manifest.json"


class TestS3StoreCleanup:
    """Tests for S3Store.cleanup method."""

    def test_cleanup_is_noop(self, monkeypatch) -> None:
        """Test that S3Store cleanup is a no-op."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "bucket")

        store = S3Store()
        store.cleanup()  # Should not raise
