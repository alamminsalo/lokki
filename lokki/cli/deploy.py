"""Deployment utilities for lokki flows.

This module provides the Deployer class for deploying lokki flows to AWS.
It handles:
- Docker image building and pushing to ECR
- CloudFormation stack creation/update
- ZIP-based deployment to Lambda
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from lokki._aws import get_cf_client, get_ecr_client, get_sts_client
from lokki._errors import DeployError, DockerNotAvailableError


class Deployer:
    """Deploys lokki flows to AWS.

    Handles building Docker images, pushing to ECR, and deploying
    CloudFormation stacks for lambda-based deployments.

    Attributes:
        stack_name: Name of the CloudFormation stack.
        region: AWS region for deployment.
        image_tag: Docker image tag.
        endpoint: AWS endpoint URL (for LocalStack).
        package_type: "image" (Docker) or "zip" (Lambda ZIP).
    """

    def __init__(
        self,
        stack_name: str,
        region: str = "us-east-1",
        image_tag: str = "latest",
        endpoint: str = "",
        package_type: str = "image",
    ) -> None:
        self.stack_name = stack_name
        self.region = region
        self.image_tag = image_tag
        self.endpoint = endpoint
        self.package_type = package_type

        self.cf_client = get_cf_client(region)
        self.ecr_client = get_ecr_client(region)
        self.sts_client = get_sts_client(region)
        self._account_id: str | None = None

    @property
    def account_id(self) -> str:
        if self._account_id is None:
            self._account_id = str(self.sts_client.get_caller_identity()["Account"])
        return self._account_id

    def deploy(
        self,
        flow_name: str,
        artifact_bucket: str,
        image_repository: str,
        build_dir: Path,
        aws_endpoint: str = "",
        package_type: str = "image",
    ) -> None:
        self._validate_credentials()
        if package_type == "zip":
            print("Uploading Lambda ZIP to S3...")
            self._upload_lambda_zip(flow_name, artifact_bucket, build_dir)
        else:
            print("Pushing Docker images...")
            self._push_images(image_repository, build_dir)
        self._deploy_stack(
            flow_name, artifact_bucket, image_repository, aws_endpoint, build_dir
        )

    def _validate_credentials(self, require_ecr: bool = True) -> None:
        if self.endpoint:
            return

        try:
            self.sts_client.get_caller_identity()
        except Exception as e:
            raise DeployError(f"AWS credentials not configured: {e}") from e

        if not shutil.which("docker"):
            raise DockerNotAvailableError(
                "Docker is not installed or not running. "
                "Please install Docker and try again."
            )

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise DockerNotAvailableError(
                    "Docker is not running. Please start Docker and try again."
                )
        except subprocess.TimeoutExpired:
            raise DockerNotAvailableError(
                "Docker command timed out. Please check Docker installation."
            ) from None
        except FileNotFoundError:
            raise DockerNotAvailableError(
                "Docker is not installed. Please install Docker and try again."
            ) from None

    def _push_images(self, image_repository: str, build_dir: Path) -> None:
        lambdas_dir = build_dir / "lambdas"
        if not lambdas_dir.exists():
            raise DeployError(f"Lambda directory not found: {lambdas_dir}")

        dockerfile_path = lambdas_dir / "Dockerfile"
        if not dockerfile_path.exists():
            raise DeployError(f"Dockerfile not found: {dockerfile_path}")

        is_local = image_repository == "local"

        if is_local:
            image_name = "lokki"
            image_uri = f"{image_name}:{self.image_tag}"
            print(f"Building local Docker image: {image_uri}...")
            self._build_image(lambdas_dir, image_uri)
            print(f"Successfully built local image: {image_uri}")
        else:
            self._login_to_ecr()
            image_name = "lokki"
            image_uri = f"{image_repository}/{image_name}:{self.image_tag}"
            print(f"Building and pushing shared Docker image: {image_uri}...")
            self._build_image(lambdas_dir, image_uri)
            self._push_image(image_uri)
            print(f"Successfully pushed image: {image_uri}")

    def _upload_lambda_zip(self, flow_name: str, bucket: str, build_dir: Path) -> None:
        from lokki.builder.s3 import upload_lambda_zip

        zip_path = build_dir / "lambdas" / "function.zip"
        if not zip_path.exists():
            raise DeployError(f"Lambda ZIP not found: {zip_path}")

        zip_data = zip_path.read_bytes()
        upload_lambda_zip(flow_name, zip_data, bucket)

    def _login_to_ecr(self) -> None:
        try:
            token = self.ecr_client.get_authorization_token()
            auth_data = token["authorizationData"][0]
            username, password = (
                auth_data["authorizationToken"].decode("utf-8").split(":", 1)
            )
            registry = auth_data["proxyEndpoint"]

            result = subprocess.run(
                [
                    "docker",
                    "login",
                    "--username",
                    username,
                    "--password",
                    password,
                    registry,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise DeployError(f"ECR login failed: {result.stderr}")
        except Exception as e:
            raise DeployError(f"Failed to login to ECR: {e}") from e

    def _build_image(self, context: Path, image_uri: str) -> None:
        try:
            build_result = subprocess.run(
                ["docker", "build", "-t", image_uri, "."],
                cwd=context,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if build_result.returncode != 0:
                raise DeployError(f"Docker build failed: {build_result.stderr}")
        except subprocess.TimeoutExpired:
            raise DeployError(f"Docker build timed out for {context.name}") from None
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed") from None

    def _push_image(self, image_uri: str) -> None:
        try:
            push_result = subprocess.run(
                ["docker", "push", image_uri],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if push_result.returncode != 0:
                raise DeployError(f"Docker push failed: {push_result.stderr}")
        except subprocess.TimeoutExpired:
            raise DeployError(f"Docker push timed out for {image_uri}") from None

    def _deploy_stack(
        self,
        flow_name: str,
        artifact_bucket: str,
        image_repository: str,
        aws_endpoint: str = "",
        build_dir: Path | None = None,
    ) -> None:
        if build_dir is None:
            build_dir = Path("lokki-build")

        template_path = build_dir / "template.yaml"
        if not template_path.exists():
            template_path = Path(self.stack_name).parent / "template.yaml"

        if not template_path.exists():
            raise DeployError(f"Template file not found: {template_path}")

        try:
            template_body = template_path.read_text()
        except Exception as e:
            raise DeployError(f"Failed to read template: {e}") from e

        self._deploy_with_boto3(
            template_body, flow_name, artifact_bucket, image_repository, aws_endpoint
        )

    def _deploy_with_boto3(
        self,
        template_body: str,
        flow_name: str,
        artifact_bucket: str,
        image_repository: str,
        aws_endpoint: str,
    ) -> None:
        try:
            existing_stack = None
            try:
                existing_stack = self.cf_client.describe_stacks(
                    StackName=self.stack_name
                )["Stacks"][0]
            except self.cf_client.exceptions.StackNotFoundException:
                pass
            except self.cf_client.exceptions.ClientError as e:
                if "does not exist" in str(e):
                    pass
                else:
                    raise

            if existing_stack:
                print(f"Updating stack '{self.stack_name}'...")
                self.cf_client.update_stack(
                    StackName=self.stack_name,
                    TemplateBody=template_body,
                    Capabilities=["CAPABILITY_IAM"],
                    Parameters=[
                        {
                            "ParameterKey": "FlowName",
                            "ParameterValue": flow_name,
                        },
                        {
                            "ParameterKey": "S3Bucket",
                            "ParameterValue": artifact_bucket,
                        },
                        {
                            "ParameterKey": "ECRRepoPrefix",
                            "ParameterValue": image_repository,
                        },
                        {
                            "ParameterKey": "ImageTag",
                            "ParameterValue": self.image_tag,
                        },
                        {
                            "ParameterKey": "AWSEndpoint",
                            "ParameterValue": aws_endpoint,
                        },
                    ],
                )
            else:
                print(f"Creating stack '{self.stack_name}'...")
                self.cf_client.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=template_body,
                    Capabilities=["CAPABILITY_IAM"],
                    Parameters=[
                        {
                            "ParameterKey": "FlowName",
                            "ParameterValue": flow_name,
                        },
                        {
                            "ParameterKey": "S3Bucket",
                            "ParameterValue": artifact_bucket,
                        },
                        {
                            "ParameterKey": "ECRRepoPrefix",
                            "ParameterValue": image_repository,
                        },
                        {
                            "ParameterKey": "ImageTag",
                            "ParameterValue": self.image_tag,
                        },
                        {
                            "ParameterKey": "AWSEndpoint",
                            "ParameterValue": aws_endpoint,
                        },
                    ],
                )

            self._wait_for_stack()

            outputs = self._get_stack_outputs()
            print(f"✓ Deployed stack '{self.stack_name}'")
            for output in outputs:
                if output["OutputKey"] == "StateMachineArn":
                    print(f"  State Machine: {output['OutputValue']}")

        except self.cf_client.exceptions.AlreadyExistsException:
            print(f"Stack '{self.stack_name}' already exists")
        except self.cf_client.exceptions.ClientError as e:
            error_message = str(e)
            if "No updates" in error_message:
                print(f"Stack '{self.stack_name}' is up to date")
            else:
                raise DeployError(f"CloudFormation error: {error_message}") from e

    def _wait_for_stack(self) -> None:
        print("Waiting for stack operation to complete...")

        while True:
            stack = self.cf_client.describe_stacks(StackName=self.stack_name)["Stacks"][
                0
            ]
            status = stack["StackStatus"]

            if status == "CREATE_COMPLETE" or status == "UPDATE_COMPLETE":
                return
            elif "FAILED" in status or "ROLLBACK" in status:
                raise DeployError(
                    f"Stack {status}: {stack.get('StackStatusReason', 'Unknown error')}"
                )

    def _get_stack_outputs(self) -> list[dict[str, Any]]:
        stack = self.cf_client.describe_stacks(StackName=self.stack_name)["Stacks"][0]
        outputs: list[dict[str, Any]] = stack.get("Outputs", []) or []
        return outputs
