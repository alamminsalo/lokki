"""Deployment utilities for lokki flows."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import boto3


class DeployError(Exception):
    """Raised when deployment fails."""

    pass


class DockerNotAvailableError(DeployError):
    """Raised when Docker is not available."""

    pass


class Deployer:
    def __init__(
        self,
        stack_name: str,
        region: str = "us-east-1",
        image_tag: str = "latest",
    ) -> None:
        self.stack_name = stack_name
        self.region = region
        self.image_tag = image_tag
        self.cf_client = boto3.client("cloudformation", region_name=region)
        self.ecr_client = boto3.client("ecr", region_name=region)
        self.sts_client = boto3.client("sts")
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
        ecr_repo_prefix: str,
        build_dir: Path,
    ) -> None:
        self._validate_credentials()
        self._push_images(ecr_repo_prefix, build_dir)
        self._deploy_stack(flow_name, artifact_bucket, ecr_repo_prefix)

    def _validate_credentials(self) -> None:
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

    def _push_images(self, ecr_repo_prefix: str, build_dir: Path) -> None:
        lambdas_dir = build_dir / "lambdas"
        if not lambdas_dir.exists():
            raise DeployError(f"Lambda directory not found: {lambdas_dir}")

        self._login_to_ecr()

        step_dirs = sorted(lambdas_dir.iterdir())
        total = len(step_dirs)

        for i, step_dir in enumerate(step_dirs, 1):
            step_name = step_dir.name
            image_uri = f"{ecr_repo_prefix}/{step_name}:{self.image_tag}"

            print(f"[{i}/{total}] Building and pushing {step_name}...")

            self._build_and_push_image(step_dir, image_uri)

        print(f"Successfully pushed {total} images to ECR")

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

    def _build_and_push_image(self, context: Path, image_uri: str) -> None:
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
        ecr_repo_prefix: str,
    ) -> None:
        template_path = Path("lokki-build") / "template.yaml"
        if not template_path.exists():
            template_path = Path(self.stack_name).parent / "template.yaml"

        if not template_path.exists():
            raise DeployError(f"Template file not found: {template_path}")

        try:
            template_body = template_path.read_text()
        except Exception as e:
            raise DeployError(f"Failed to read template: {e}") from e

        try:
            existing_stack = None
            try:
                existing_stack = self.cf_client.describe_stacks(
                    StackName=self.stack_name
                )["Stacks"][0]
            except self.cf_client.exceptions.StackNotFoundException:
                pass

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
                            "ParameterValue": ecr_repo_prefix,
                        },
                        {
                            "ParameterKey": "ImageTag",
                            "ParameterValue": self.image_tag,
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
                            "ParameterValue": ecr_repo_prefix,
                        },
                        {
                            "ParameterKey": "ImageTag",
                            "ParameterValue": self.image_tag,
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
