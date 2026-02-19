"""Unit tests for lokki S3 module."""

import gzip
import pickle
from unittest.mock import MagicMock, patch

import pytest

from lokki.s3 import _parse_url, read, write


class TestParseUrl:
    """Tests for _parse_url function."""

    def test_parse_valid_url(self) -> None:
        """Test parsing a valid s3:// URL."""
        bucket, key = _parse_url("s3://my-bucket/path/to/file.txt")
        assert bucket == "my-bucket"
        assert key == "path/to/file.txt"

    def test_parse_url_with_multiple_slashes(self) -> None:
        """Test parsing URL with multiple path segments."""
        bucket, key = _parse_url("s3://bucket/a/b/c/d.txt")
        assert bucket == "bucket"
        assert key == "a/b/c/d.txt"

    def test_parse_url_root(self) -> None:
        """Test parsing URL with only bucket."""
        bucket, key = _parse_url("s3://my-bucket")
        assert bucket == "my-bucket"
        assert key == ""

    def test_parse_url_missing_protocol(self) -> None:
        """Test that missing s3:// protocol raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            _parse_url("my-bucket/path/to/file.txt")

    def test_parse_url_empty_bucket(self) -> None:
        """Test that empty bucket raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            _parse_url("s3:///path/to/file.txt")

    def test_parse_url_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid S3 URL"):
            _parse_url("")


class TestWrite:
    """Tests for write function."""

    @patch("lokki.s3.boto3")
    def test_write_returns_s3_url(self, mock_boto3: MagicMock) -> None:
        """Test that write returns the s3:// URL."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        result = write("my-bucket", "path/to/obj.pkl.gz", {"key": "value"})

        assert result == "s3://my-bucket/path/to/obj.pkl.gz"
        mock_s3.put_object.assert_called_once()

    @patch("lokki.s3.boto3")
    def test_write_serializes_with_gzip_pickle(self, mock_boto3: MagicMock) -> None:
        """Test that write uses gzip and pickle."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        test_obj = {"data": [1, 2, 3]}
        write("bucket", "key", test_obj)

        call_args = mock_s3.put_object.call_args
        body = call_args.kwargs["Body"]

        uncompressed = gzip.decompress(body)
        unpickled = pickle.loads(uncompressed)
        assert unpickled == test_obj


class TestRead:
    """Tests for read function."""

    @patch("lokki.s3.boto3")
    def test_read_deserializes_object(self, mock_boto3: MagicMock) -> None:
        """Test that read deserializes the object from S3."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        test_obj = {"result": "success"}
        serialized = gzip.compress(
            pickle.dumps(test_obj, protocol=pickle.HIGHEST_PROTOCOL)
        )
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=serialized))
        }

        result = read("s3://my-bucket/path/to/obj.pkl.gz")

        assert result == test_obj
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="path/to/obj.pkl.gz"
        )

    @patch("lokki.s3.boto3")
    def test_read_uses_parsed_url(self, mock_boto3: MagicMock) -> None:
        """Test that read correctly uses parsed bucket and key."""
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        test_obj = "test data"
        serialized = gzip.compress(
            pickle.dumps(test_obj, protocol=pickle.HIGHEST_PROTOCOL)
        )
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=serialized))
        }

        read("s3://bucket/key")

        mock_s3.get_object.assert_called_with(Bucket="bucket", Key="key")
