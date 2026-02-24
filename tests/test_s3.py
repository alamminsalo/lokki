"""Unit tests for lokki S3 module."""

import gzip
import pickle

import boto3
import pytest
from moto import mock_aws

from lokki.store import S3Store


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
    def test_write_returns_s3_url(self) -> None:
        """Test that write returns the s3:// URL."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-bucket")

        store = S3Store("my-bucket")
        result = store.write(
            bucket="my-bucket", key="path/to/obj.pkl.gz", obj={"key": "value"}
        )

        assert result == "s3://my-bucket/path/to/obj.pkl.gz"

    @mock_aws
    def test_write_serializes_with_gzip_pickle(self) -> None:
        """Test that write uses gzip and pickle."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store("bucket")
        test_obj = {"data": [1, 2, 3]}
        store.write(bucket="bucket", key="key", obj=test_obj)

        response = s3.get_object(Bucket="bucket", Key="key")
        body = response["Body"].read()

        uncompressed = gzip.decompress(body)
        unpickled = pickle.loads(uncompressed)
        assert unpickled == test_obj

    @mock_aws
    def test_write_with_flow_params(self) -> None:
        """Test write with flow_name, run_id, step_name parameters."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store("bucket")
        result = store.write(
            flow_name="my-flow",
            run_id="run-123",
            step_name="my-step",
            obj={"data": "test"},
        )

        assert result == "s3://bucket/lokki/my-flow/run-123/my-step/output.pkl.gz"


class TestS3StoreRead:
    """Tests for S3Store.read method."""

    @mock_aws
    def test_read_deserializes_object(self) -> None:
        """Test that read deserializes the object from S3."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="my-bucket")

        test_obj = {"result": "success"}
        serialized = gzip.compress(
            pickle.dumps(test_obj, protocol=pickle.HIGHEST_PROTOCOL)
        )
        s3.put_object(Bucket="my-bucket", Key="path/to/obj.pkl.gz", Body=serialized)

        store = S3Store("my-bucket")
        result = store.read("s3://my-bucket/path/to/obj.pkl.gz")

        assert result == test_obj

    @mock_aws
    def test_read_uses_parsed_url(self) -> None:
        """Test that read correctly uses parsed bucket and key."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        test_obj = "test data"
        serialized = gzip.compress(
            pickle.dumps(test_obj, protocol=pickle.HIGHEST_PROTOCOL)
        )
        s3.put_object(Bucket="bucket", Key="key", Body=serialized)

        store = S3Store("bucket")
        store.read("s3://bucket/key")

        response = s3.get_object(Bucket="bucket", Key="key")
        assert response is not None


class TestS3StoreWriteManifest:
    """Tests for S3Store.write_manifest method."""

    @mock_aws
    def test_write_manifest_with_bucket_key(self) -> None:
        """Test write_manifest with bucket and key parameters."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store("bucket")
        items = [{"key": "value1"}, {"key": "value2"}]
        result = store.write_manifest(bucket="bucket", key="manifest.json", items=items)

        assert result == "s3://bucket/manifest.json"

    @mock_aws
    def test_write_manifest_with_flow_params(self) -> None:
        """Test write_manifest with flow_name, run_id, step_name parameters."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store("bucket")
        items = [{"index": 0}, {"index": 1}]
        result = store.write_manifest(
            flow_name="my-flow",
            run_id="run-123",
            step_name="map-step",
            items=items,
        )

        assert result == "s3://bucket/lokki/my-flow/run-123/map-step/map_manifest.json"

    @mock_aws
    def test_write_manifest_content_type_json(self) -> None:
        """Test that write_manifest sets correct content type."""
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="bucket")

        store = S3Store("bucket")
        items = [{"key": "value"}]
        store.write_manifest(bucket="bucket", key="manifest.json", items=items)

        response = s3.get_object(Bucket="bucket", Key="manifest.json")
        assert response["ContentType"] == "application/json"


class TestS3StoreErrors:
    """Tests for S3Store error handling."""

    def test_write_missing_params(self) -> None:
        """Test that write raises error without required params."""
        store = S3Store("bucket")

        with pytest.raises(ValueError, match="Must provide either"):
            store.write()

    def test_write_partial_params(self) -> None:
        """Test that write raises error with partial params."""
        store = S3Store("bucket")

        with pytest.raises(ValueError, match="Must provide either"):
            store.write(flow_name="my-flow")

    def test_write_manifest_missing_params(self) -> None:
        """Test that write_manifest raises error without required params."""
        store = S3Store("bucket")

        with pytest.raises(ValueError, match="Must provide either"):
            store.write_manifest()
