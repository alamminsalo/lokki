"""Unit tests for _aws module."""

import os
from unittest.mock import patch

from moto import mock_aws


class TestAwsClients:
    """Tests for AWS client factory functions."""

    @mock_aws
    def test_get_s3_client_without_endpoint(self) -> None:
        """Test S3 client creation without endpoint."""
        from lokki._aws import get_s3_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_s3_client()

        assert client is not None
        assert client._service_model.service_name == "s3"

    @mock_aws
    def test_get_s3_client_with_endpoint(self) -> None:
        """Test S3 client creation with endpoint."""
        from lokki._aws import get_s3_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_s3_client()

        assert client is not None

    @mock_aws
    def test_get_sfn_client_without_endpoint(self) -> None:
        """Test Step Functions client creation without endpoint."""
        from lokki._aws import get_sfn_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_sfn_client()

        assert client is not None
        assert client._service_model.service_name == "stepfunctions"

    @mock_aws
    def test_get_sfn_client_with_endpoint(self) -> None:
        """Test Step Functions client creation with endpoint."""
        from lokki._aws import get_sfn_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_sfn_client(region="eu-west-1")

        assert client is not None

    @mock_aws
    def test_get_cf_client_without_endpoint(self) -> None:
        """Test CloudFormation client creation without endpoint."""
        from lokki._aws import get_cf_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_cf_client()

        assert client is not None
        assert client._service_model.service_name == "cloudformation"

    @mock_aws
    def test_get_cf_client_with_endpoint(self) -> None:
        """Test CloudFormation client creation with endpoint."""
        from lokki._aws import get_cf_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_cf_client(region="us-west-2")

        assert client is not None

    @mock_aws
    def test_get_logs_client_without_endpoint(self) -> None:
        """Test CloudWatch Logs client creation without endpoint."""
        from lokki._aws import get_logs_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_logs_client()

        assert client is not None
        assert client._service_model.service_name == "logs"

    @mock_aws
    def test_get_logs_client_with_endpoint(self) -> None:
        """Test CloudWatch Logs client creation with endpoint."""
        from lokki._aws import get_logs_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_logs_client(region="ap-southeast-1")

        assert client is not None

    @mock_aws
    def test_get_ecr_client_without_endpoint(self) -> None:
        """Test ECR client creation without endpoint."""
        from lokki._aws import get_ecr_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_ecr_client()

        assert client is not None
        assert client._service_model.service_name == "ecr"

    @mock_aws
    def test_get_ecr_client_with_endpoint(self) -> None:
        """Test ECR client creation with endpoint."""
        from lokki._aws import get_ecr_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_ecr_client(region="ca-central-1")

        assert client is not None

    @mock_aws
    def test_get_sts_client_without_endpoint(self) -> None:
        """Test STS client creation without endpoint."""
        from lokki._aws import get_sts_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_sts_client()

        assert client is not None
        assert client._service_model.service_name == "sts"

    @mock_aws
    def test_get_sts_client_with_endpoint(self) -> None:
        """Test STS client creation with endpoint."""
        from lokki._aws import get_sts_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_sts_client(region="eu-central-1")

        assert client is not None

    @mock_aws
    def test_get_batch_client_without_endpoint(self) -> None:
        """Test Batch client creation without endpoint."""
        from lokki._aws import get_batch_client

        with patch.dict(os.environ, {}, clear=True):
            client = get_batch_client()

        assert client is not None
        assert client._service_model.service_name == "batch"

    @mock_aws
    def test_get_batch_client_with_endpoint(self) -> None:
        """Test Batch client creation with endpoint."""
        from lokki._aws import get_batch_client

        with patch.dict(os.environ, {"AWS_ENDPOINT_URL": "http://localhost:4566"}):
            client = get_batch_client(region="us-west-1")

        assert client is not None
