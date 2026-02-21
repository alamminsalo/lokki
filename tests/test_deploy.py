"""Unit tests for deploy module."""

import tempfile
from pathlib import Path

import pytest
from moto import mock_aws

from lokki.deploy import Deployer, DeployError


class TestDeployerInit:
    """Tests for Deployer initialization."""

    def test_basic_init(self) -> None:
        """Test basic Deployer initialization."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            image_tag="latest",
        )
        assert deployer.stack_name == "test-stack"
        assert deployer.region == "us-east-1"
        assert deployer.image_tag == "latest"

    def test_init_with_endpoint(self) -> None:
        """Test Deployer with custom endpoint."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            image_tag="v1",
            endpoint="http://localhost:4566",
        )
        assert deployer.endpoint == "http://localhost:4566"

    def test_init_with_zip_package(self) -> None:
        """Test Deployer with ZIP package type."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            image_tag="latest",
            package_type="zip",
        )
        assert deployer.package_type == "zip"


class TestDeployerCredentials:
    """Tests for credential validation with moto."""

    @mock_aws
    def test_validate_credentials_no_endpoint(self) -> None:
        """Test credential validation when no endpoint is set."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        # moto mocks boto3, so this will work
        deployer._validate_credentials()

    def test_validate_credentials_with_endpoint(self) -> None:
        """Test credential validation when endpoint is set (LocalStack)."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            endpoint="http://localhost:4566",
        )

        # Should not call STS when endpoint is set
        deployer._validate_credentials()


class TestDeployerPushImages:
    """Tests for image pushing."""

    def test_push_images_raises_when_no_dockerfile(self) -> None:
        """Test that error is raised when Dockerfile doesn't exist."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            image_tag="latest",
            package_type="image",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            lambdas_dir = build_dir / "lambdas"
            lambdas_dir.mkdir()
            # No Dockerfile

            with pytest.raises(DeployError, match="Dockerfile not found"):
                deployer._push_images("local", build_dir)

    def test_push_images_raises_when_no_lambdas_dir(self) -> None:
        """Test that error is raised when lambdas directory doesn't exist."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            image_tag="latest",
            package_type="image",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            with pytest.raises(DeployError, match="Lambda directory not found"):
                deployer._push_images("local", build_dir)


class TestDeployerClients:
    """Tests for boto3 client initialization with moto."""

    @mock_aws
    def test_clients_initialized(self) -> None:
        """Test that boto3 clients are properly initialized."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        # Clients should be initialized
        assert deployer.cf_client is not None
        assert deployer.ecr_client is not None
        assert deployer.sts_client is not None

    @mock_aws
    def test_account_id_property(self) -> None:
        """Test that account_id is fetched correctly."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        # moto returns a mock account ID
        account_id = deployer.account_id
        assert account_id is not None
        assert isinstance(account_id, str)
