"""Unit tests for deploy module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from lokki.cli.deploy import Deployer, DeployError, DockerNotAvailableError


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
    """Tests for image pushing with Docker mocking."""

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

    @mock_aws
    @patch("lokki.cli.deploy.subprocess.run")
    def test_push_images_local_success(self, mock_subprocess: MagicMock) -> None:
        """Test successful local Docker image push."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

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
            (lambdas_dir / "Dockerfile").write_text("FROM python:3.13")

            deployer._push_images("local", build_dir)

            # Verify docker build was called
            assert mock_subprocess.call_count >= 1

    @mock_aws
    @patch("lokki.cli.deploy.subprocess.run")
    def test_push_images_local_docker_not_available(
        self, mock_subprocess: MagicMock
    ) -> None:
        """Test error when docker is not available."""
        from lokki.cli.deploy import DockerNotAvailableError

        mock_subprocess.side_effect = FileNotFoundError("docker not found")

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
            (lambdas_dir / "Dockerfile").write_text("FROM python:3.13")

            with pytest.raises(DockerNotAvailableError):
                deployer._push_images("local", build_dir)

    @patch("lokki.cli.deploy.subprocess.run")
    def test_push_images_ecr_success(self, mock_subprocess: MagicMock) -> None:
        """Test successful ECR Docker image push."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

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
            (lambdas_dir / "Dockerfile").write_text("FROM python:3.13")

            # Push to ECR (non-local) - needs mocked ECR client
            with patch.object(deployer, "ecr_client") as mock_ecr:
                # ECR returns bytes for authorizationToken
                mock_ecr.get_authorization_token.return_value = {
                    "authorizationData": [
                        {
                            "authorizationToken": b"user:pass",
                            "proxyEndpoint": "https://123456789.dkr.ecr.us-east-1.amazonaws.com",
                        }
                    ]
                }
                deployer._push_images(
                    "123456789.dkr.ecr.us-east-1.amazonaws.com/test", build_dir
                )

            # Verify docker commands were called
            assert mock_subprocess.call_count >= 2


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


class TestDeployerDeployStack:
    """Tests for CloudFormation stack deployment."""

    def test_deploy_stack_raises_template_not_found(self) -> None:
        """Test error when template file doesn't exist."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            with pytest.raises(DeployError, match="Template file not found"):
                deployer._deploy_stack(
                    flow_name="test-flow",
                    artifact_bucket="test-bucket",
                    image_repository="test-repo",
                    aws_endpoint="",
                    build_dir=build_dir,
                )

    @mock_aws
    @patch("lokki.cli.deploy.subprocess.run")
    def test_deploy_with_zip_skips_image_push(self, mock_subprocess: MagicMock) -> None:
        """Test that ZIP package type skips image push."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            package_type="zip",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            template = """AWSTemplateFormatVersion: '2010-09-09'
Resources:
  TestBucket:
    Type: AWS::S3::Bucket
"""
            template_path = build_dir / "template.yaml"
            template_path.write_text(template)

            deployer._deploy_stack(
                flow_name="test-flow",
                artifact_bucket="test-bucket",
                image_repository="test-repo",
                aws_endpoint="",
                build_dir=build_dir,
            )

            # Verify stack was created in AWS
            cf_client = boto3.client("cloudformation", region_name="us-east-1")
            stacks = cf_client.describe_stacks(StackName="test-stack")
            assert len(stacks["Stacks"]) == 1

    @mock_aws
    @patch("lokki.cli.deploy.subprocess.run")
    def test_deploy_stack_updates_existing_stack(
        self, mock_subprocess: MagicMock
    ) -> None:
        """Test updating an existing CloudFormation stack."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        cf_client = boto3.client("cloudformation", region_name="us-east-1")
        cf_client.create_stack(
            StackName="test-stack",
            TemplateBody=(
                "AWSTemplateFormatVersion: '2010-09-09'\n"
                "Resources:\n"
                "  Bucket:\n"
                "    Type: AWS::S3::Bucket"
            ),
        )

        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            template = """AWSTemplateFormatVersion: '2010-09-09'
Resources:
  TestBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: updated-bucket
"""
            template_path = build_dir / "template.yaml"
            template_path.write_text(template)

            deployer._deploy_stack(
                flow_name="test-flow",
                artifact_bucket="test-bucket",
                image_repository="test-repo",
                aws_endpoint="",
                build_dir=build_dir,
            )

            # Verify stack was updated
            stacks = cf_client.describe_stacks(StackName="test-stack")
            assert len(stacks["Stacks"]) == 1


class TestDeployerValidateCredentials:
    """Tests for credential validation."""

    @mock_aws
    def test_validate_credentials_with_endpoint(self) -> None:
        """Test credentials not checked when endpoint is set."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
            endpoint="http://localhost:4566",
        )
        # Should not raise - endpoint is set so credentials not checked
        deployer._validate_credentials()

    @mock_aws
    def test_validate_credentials_no_docker(self) -> None:
        """Test error when docker is not available."""
        deployer = Deployer(
            stack_name="test-stack",
            region="us-east-1",
        )

        with patch("lokki.cli.deploy.shutil.which") as mock_which:
            mock_which.return_value = None  # Docker not found

            with pytest.raises(
                DockerNotAvailableError, match="Docker is not installed"
            ):
                deployer._validate_credentials()


class TestDeployerBoto3:
    """Tests for boto3 deployment."""

    @mock_aws
    @patch("lokki.cli.deploy.subprocess.run")
    def test_deploy_boto3_create_stack(self, mock_subprocess: MagicMock) -> None:
        """Test boto3 stack creation."""
        mock_subprocess.return_value = MagicMock(returncode=0, stderr="")

        deployer = Deployer(
            stack_name="test-stack-boto3",
            region="us-east-1",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            template = """AWSTemplateFormatVersion: '2010-09-09'
Resources:
  TestBucket:
    Type: AWS::S3::Bucket
"""
            template_path = build_dir / "template.yaml"
            template_path.write_text(template)

            deployer._deploy_with_boto3(
                template_body=template,
                flow_name="test-flow",
                artifact_bucket="test-bucket",
                image_repository="test-repo",
                aws_endpoint="",
            )

            cf_client = boto3.client("cloudformation", region_name="us-east-1")
            stacks = cf_client.describe_stacks(StackName="test-stack-boto3")
            assert len(stacks["Stacks"]) == 1
