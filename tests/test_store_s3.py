"""Unit tests for S3Store implementation using moto mock."""

import gzip
import json
import os
import pickle

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from lokki.store.s3 import S3Store


@pytest.fixture
def s3_client():
    """Create a boto3 S3 client using moto mock."""
    import boto3

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        yield client


@pytest.fixture
def s3_store(s3_client):
    """Create S3Store with mocked S3."""
    os.environ["LOKKI_ARTIFACT_BUCKET"] = "test-bucket"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    s3_client.create_bucket(Bucket="test-bucket")

    store = S3Store()
    yield store

    os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)
    os.environ.pop("AWS_DEFAULT_REGION", None)


class TestS3StoreInit:
    """Tests for S3Store initialization."""

    def test_init_with_bucket_env(self, s3_client) -> None:
        """Test S3Store initializes with bucket from environment."""
        os.environ["LOKKI_ARTIFACT_BUCKET"] = "test-bucket"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        s3_client.create_bucket(Bucket="test-bucket")
        store = S3Store()

        assert store.bucket == "test-bucket"

        os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)
        os.environ.pop("AWS_DEFAULT_REGION", None)

    def test_init_without_bucket_env(self) -> None:
        """Test S3Store raises error without bucket environment variable."""
        os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)

        with pytest.raises(ValueError, match="LOKKI_ARTIFACT_BUCKET"):
            S3Store()

    def test_init_empty_bucket_env(self) -> None:
        """Test S3Store raises error with empty bucket environment variable."""
        os.environ["LOKKI_ARTIFACT_BUCKET"] = ""

        with pytest.raises(ValueError, match="LOKKI_ARTIFACT_BUCKET"):
            S3Store()

        os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)


class TestS3StoreWriteRead:
    """Tests for S3Store write and read operations."""

    def test_write_read_basic(self, s3_store, s3_client) -> None:
        """Test basic write and read operations."""
        test_data = {"key": "value", "number": 42}

        location = s3_store.write(
            flow_name="test-flow",
            run_id="run-123",
            step_name="process",
            obj=test_data,
        )

        assert location.startswith("s3://test-bucket/")
        result = s3_store.read(location)
        assert result == test_data

    def test_write_read_nested_data(self, s3_store) -> None:
        """Test write and read with nested data structures."""
        test_data = {
            "items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
            "metadata": {"count": 2, "tags": ["x", "y"]},
        }

        location = s3_store.write(
            flow_name="complex-flow",
            run_id="run-456",
            step_name="transform",
            obj=test_data,
        )

        result = s3_store.read(location)
        assert result == test_data

    def test_write_with_input_hash(self, s3_store, s3_client) -> None:
        """Test write with input_hash stores tag."""
        test_data = [1, 2, 3]

        location = s3_store.write(
            flow_name="test-flow",
            run_id="run-789",
            step_name="step1",
            obj=test_data,
            input_hash="abc123",
        )

        result = s3_store.read(location)
        assert result == test_data

        key = "lokki/test-flow/runs/run-789/step1/output.pkl.gz"
        response = s3_client.get_object_tagging(Bucket="test-bucket", Key=key)

        tags = {t["Key"]: t["Value"] for t in response["TagSet"]}
        assert tags["input_hash"] == "abc123"

    def test_write_without_input_hash(self, s3_store, s3_client) -> None:
        """Test write without input_hash has no tags."""
        test_data = [1, 2, 3]

        s3_store.write(
            flow_name="test-flow",
            run_id="run-789",
            step_name="step1",
            obj=test_data,
        )

        key = "lokki/test-flow/runs/run-789/step1/output.pkl.gz"
        response = s3_client.get_object_tagging(Bucket="test-bucket", Key=key)

        assert len(response["TagSet"]) == 0

    def test_write_multiple_steps(self, s3_store) -> None:
        """Test writing multiple steps in same flow."""
        loc1 = s3_store.write("flow1", "run1", "step1", {"data": "step1"})
        loc2 = s3_store.write("flow1", "run1", "step2", {"data": "step2"})
        loc3 = s3_store.write("flow1", "run1", "step3", {"data": "step3"})

        assert s3_store.read(loc1) == {"data": "step1"}
        assert s3_store.read(loc2) == {"data": "step2"}
        assert s3_store.read(loc3) == {"data": "step3"}

    def test_write_multiple_runs(self, s3_store) -> None:
        """Test writing same step in different runs."""
        loc1 = s3_store.write("flow1", "run1", "step1", {"run": 1})
        loc2 = s3_store.write("flow1", "run2", "step1", {"run": 2})

        assert s3_store.read(loc1) == {"run": 1}
        assert s3_store.read(loc2) == {"run": 2}


class TestS3StoreExists:
    """Tests for S3Store exists method."""

    def test_exists_after_write(self, s3_store) -> None:
        """Test exists returns True after write."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        assert s3_store.exists("flow1", "run1", "step1") is True

    def test_exists_before_write(self, s3_store) -> None:
        """Test exists returns False before write."""
        assert s3_store.exists("flow1", "run1", "step1") is False

    def test_exists_different_flows(self, s3_store) -> None:
        """Test exists distinguishes between flows."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        assert s3_store.exists("flow1", "run1", "step1") is True
        assert s3_store.exists("flow2", "run1", "step1") is False

    def test_exists_different_runs(self, s3_store) -> None:
        """Test exists distinguishes between runs."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        assert s3_store.exists("flow1", "run1", "step1") is True
        assert s3_store.exists("flow1", "run2", "step1") is False


class TestS3StoreReadCached:
    """Tests for S3Store read_cached method."""

    def test_read_cached_basic(self, s3_store) -> None:
        """Test basic read_cached operation."""
        test_data = {"cached": "data"}

        s3_store.write("flow1", "run1", "step1", test_data)
        result = s3_store.read_cached("flow1", "run1", "step1")

        assert result == test_data

    def test_read_cached_missing(self, s3_store) -> None:
        """Test read_cached raises error for missing data."""
        with pytest.raises(ClientError):
            s3_store.read_cached("flow1", "run1", "step1")

    def test_read_cached_multiple_steps(self, s3_store) -> None:
        """Test read_cached for multiple steps."""
        s3_store.write("flow1", "run1", "step1", {"step": 1})
        s3_store.write("flow1", "run1", "step2", {"step": 2})

        assert s3_store.read_cached("flow1", "run1", "step1") == {"step": 1}
        assert s3_store.read_cached("flow1", "run1", "step2") == {"step": 2}


class TestS3StoreWriteManifest:
    """Tests for S3Store write_manifest method."""

    def test_write_manifest_basic(self, s3_store, s3_client) -> None:
        """Test basic write_manifest operation."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]

        location = s3_store.write_manifest(
            flow_name="flow1",
            run_id="run1",
            step_name="map_step",
            items=items,
        )

        assert location.startswith("s3://test-bucket/")
        assert "map_manifest.json" in location

        key = "lokki/flow1/runs/run1/map_step/map_manifest.json"
        response = s3_client.get_object(Bucket="test-bucket", Key=key)
        result = json.loads(response["Body"].read().decode())
        assert result == items

    def test_write_manifest_empty(self, s3_store, s3_client) -> None:
        """Test write_manifest with empty list."""
        location = s3_store.write_manifest(
            flow_name="flow1",
            run_id="run1",
            step_name="map_step",
            items=[],
        )

        key = "lokki/flow1/runs/run1/map_step/map_manifest.json"
        response = s3_client.get_object(Bucket="test-bucket", Key=key)
        result = json.loads(response["Body"].read().decode())
        assert result == []

    def test_write_manifest_complex_objects(self, s3_store, s3_client) -> None:
        """Test write_manifest with complex objects."""
        items = [
            {"data": [1, 2, 3], "nested": {"key": "value"}},
            {"data": [4, 5, 6], "nested": {"key": "value2"}},
        ]

        location = s3_store.write_manifest("flow1", "run1", "map_step", items)

        key = "lokki/flow1/runs/run1/map_step/map_manifest.json"
        response = s3_client.get_object(Bucket="test-bucket", Key=key)
        result = json.loads(response["Body"].read().decode())

        assert result == items

    def test_write_manifest_multiple_steps(self, s3_store, s3_client) -> None:
        """Test write_manifest for multiple map steps."""
        loc1 = s3_store.write_manifest("flow1", "run1", "map1", [{"id": 1}])
        loc2 = s3_store.write_manifest("flow1", "run1", "map2", [{"id": 2}])

        key1 = "lokki/flow1/runs/run1/map1/map_manifest.json"
        key2 = "lokki/flow1/runs/run1/map2/map_manifest.json"

        response1 = s3_client.get_object(Bucket="test-bucket", Key=key1)
        response2 = s3_client.get_object(Bucket="test-bucket", Key=key2)

        result1 = json.loads(response1["Body"].read().decode())
        result2 = json.loads(response2["Body"].read().decode())

        assert result1 == [{"id": 1}]
        assert result2 == [{"id": 2}]


class TestS3StoreParseUrl:
    """Tests for S3Store URL parsing."""

    def test_parse_url_valid(self) -> None:
        """Test parsing valid S3 URLs."""
        bucket, key = S3Store._parse_url("s3://my-bucket/path/to/object")
        assert bucket == "my-bucket"
        assert key == "path/to/object"

    def test_parse_url_root_object(self) -> None:
        """Test parsing S3 URL with root-level object."""
        bucket, key = S3Store._parse_url("s3://my-bucket/object")
        assert bucket == "my-bucket"
        assert key == "object"

    def test_parse_url_no_key(self) -> None:
        """Test parsing S3 URL with no key."""
        bucket, key = S3Store._parse_url("s3://my-bucket/")
        assert bucket == "my-bucket"
        assert key == ""

    def test_parse_url_invalid_no_s3_prefix(self) -> None:
        """Test parsing URL without s3:// prefix raises error."""
        with pytest.raises(ValueError, match="Must start with 's3://'"):
            S3Store._parse_url("https://my-bucket.s3.amazonaws.com/object")

    def test_parse_url_invalid_empty_bucket(self) -> None:
        """Test parsing URL with empty bucket raises error."""
        with pytest.raises(ValueError, match="Missing bucket"):
            S3Store._parse_url("s3:///object")


class TestS3StoreGetInputHash:
    """Tests for S3Store get_input_hash method."""

    def test_get_input_hash_with_tag(self, s3_store, s3_client) -> None:
        """Test get_input_hash returns hash when tag exists."""
        s3_store.write(
            "flow1",
            "run1",
            "step1",
            {"data": "test"},
            input_hash="hash123",
        )

        hash_value = s3_store.get_input_hash("flow1", "run1", "step1")
        assert hash_value == "hash123"

    def test_get_input_hash_without_tag(self, s3_store) -> None:
        """Test get_input_hash returns None when no tag."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        hash_value = s3_store.get_input_hash("flow1", "run1", "step1")
        assert hash_value is None

    def test_get_input_hash_missing_object(self, s3_store) -> None:
        """Test get_input_hash returns None for missing object."""
        hash_value = s3_store.get_input_hash("flow1", "run1", "missing_step")
        assert hash_value is None


class TestS3StoreCleanup:
    """Tests for S3Store cleanup method."""

    def test_cleanup_is_noop(self, s3_store) -> None:
        """Test cleanup is a no-op for S3Store."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        s3_store.cleanup()

        assert s3_store.exists("flow1", "run1", "step1") is True


class TestS3StoreErrorCases:
    """Tests for S3Store error cases."""

    def test_read_invalid_url(self, s3_store) -> None:
        """Test read with invalid URL raises error."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            s3_store.read("https://bucket/object")

    def test_read_nonexistent_object(self, s3_store) -> None:
        """Test read raises error for nonexistent object."""
        with pytest.raises(ClientError):
            s3_store.read("s3://test-bucket/nonexistent/object.pkl.gz")

    def test_write_to_missing_bucket(self) -> None:
        """Test write to missing bucket raises error."""
        import boto3

        with mock_aws():
            os.environ["LOKKI_ARTIFACT_BUCKET"] = "nonexistent-bucket"
            os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

            store = S3Store()

            with pytest.raises(ClientError) as exc_info:
                store.write("flow1", "run1", "step1", {"data": "test"})

            assert exc_info.value.response["Error"]["Code"] == "NoSuchBucket"

            os.environ.pop("LOKKI_ARTIFACT_BUCKET", None)
            os.environ.pop("AWS_DEFAULT_REGION", None)

    def test_exists_with_access_denied(self, s3_store, s3_client) -> None:
        """Test exists handles access denied errors."""
        s3_store.write("flow1", "run1", "step1", {"data": "test"})

        assert s3_store.exists("flow1", "run1", "step1") is True

    def test_write_large_object(self, s3_store) -> None:
        """Test writing large objects."""
        large_data = {"items": list(range(10000))}

        location = s3_store.write("flow1", "run1", "step1", large_data)
        result = s3_store.read(location)

        assert result == large_data

    def test_write_special_values(self, s3_store) -> None:
        """Test writing special Python values."""
        test_cases = [
            ("none", None),
            ("empty_list", []),
            ("empty_dict", {}),
            ("boolean_true", True),
            ("boolean_false", False),
            ("zero", 0),
            ("empty_string", ""),
        ]

        for name, value in test_cases:
            location = s3_store.write("flow1", "run1", name, value)
            result = s3_store.read(location)
            assert result == value

    def test_unicode_data(self, s3_store) -> None:
        """Test writing and reading unicode data."""
        unicode_data = {"text": "Hello 世界 🌍", "emoji": "🚀🎉"}

        location = s3_store.write("flow1", "run1", "unicode_step", unicode_data)
        result = s3_store.read(location)

        assert result == unicode_data
