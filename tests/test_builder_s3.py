"""Unit tests for builder/s3.py module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestUploadLambdaZip:
    """Tests for upload_lambda_zip function."""

    def test_upload_lambda_zip_with_bucket_param(self) -> None:
        """Test upload with explicit bucket parameter."""
        from lokki.builder.s3 import upload_lambda_zip

        mock_client = MagicMock()

        with patch("lokki._aws.get_s3_client", return_value=mock_client):
            result = upload_lambda_zip(
                flow_name="test-flow",
                zip_data=b"test-zip-content",
                bucket="my-bucket",
            )

        mock_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="test-flow/artifacts/lambdas/function.zip",
            Body=b"test-zip-content",
        )
        assert result == "s3://my-bucket/test-flow/artifacts/lambdas/function.zip"

    def test_upload_lambda_zip_falls_back_to_env_var(self) -> None:
        """Test upload falls back to LOKKI_ARTIFACT_BUCKET env var."""
        from lokki.builder.s3 import upload_lambda_zip

        mock_client = MagicMock()

        with patch("lokki._aws.get_s3_client", return_value=mock_client):
            with patch.dict("os.environ", {"LOKKI_ARTIFACT_BUCKET": "env-bucket"}):
                result = upload_lambda_zip(
                    flow_name="test-flow",
                    zip_data=b"test-zip-content",
                    bucket="",
                )

        mock_client.put_object.assert_called_once_with(
            Bucket="env-bucket",
            Key="test-flow/artifacts/lambdas/function.zip",
            Body=b"test-zip-content",
        )
        assert result == "s3://env-bucket/test-flow/artifacts/lambdas/function.zip"

    def test_upload_lambda_zip_raises_when_no_bucket(self) -> None:
        """Test that ValueError is raised when no bucket is available."""
        from lokki.builder.s3 import upload_lambda_zip

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(
                ValueError, match="LOKKI_ARTIFACT_BUCKET environment variable not set"
            ):
                upload_lambda_zip(
                    flow_name="test-flow",
                    zip_data=b"test-zip-content",
                    bucket="",
                )

    def test_upload_lambda_zip_raises_when_bucket_env_empty(self) -> None:
        """Test that ValueError is raised when bucket and env var are empty."""
        from lokki.builder.s3 import upload_lambda_zip

        with patch.dict("os.environ", {"LOKKI_ARTIFACT_BUCKET": ""}):
            with pytest.raises(
                ValueError, match="LOKKI_ARTIFACT_BUCKET environment variable not set"
            ):
                upload_lambda_zip(
                    flow_name="test-flow",
                    zip_data=b"test-zip-content",
                    bucket="",
                )
