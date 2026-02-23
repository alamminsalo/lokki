"""Configuration loading and management for lokki.

This module provides configuration management for lokki pipelines.
Configuration is loaded from TOML files with environment variable overrides.

Configuration precedence (highest to lowest):
1. Environment variables
2. Local config (./lokki.toml)
3. Global config (~/.lokki/lokki.toml)
4. Default values
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lokki.logging import LoggingConfig

GLOBAL_CONFIG_PATH = Path.home() / ".lokki" / "lokki.toml"
LOCAL_CONFIG_PATH = Path.cwd() / "lokki.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning empty dict if not found."""
    if path.exists():
        with path.open("rb") as f:
            return tomllib.load(f)
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base.

    Lists and scalars are replaced; dicts are merged recursively.
    """
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class LambdaConfig:
    """Lambda function configuration.

    Attributes:
        package_type: Package type - "image" (Docker) or "zip".
        base_image: Docker base image for Lambda.
        timeout: Lambda timeout in seconds.
        memory: Lambda memory in MB.
        image_tag: Docker image tag for Lambda.
        env: Environment variables passed to Lambda functions.
    """

    package_type: str = "image"  # "image" or "zip"
    base_image: str = "public.ecr.aws/lambda/python:3.13"
    timeout: int = 900
    memory: int = 512
    image_tag: str = "latest"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class BatchConfig:
    """AWS Batch job configuration.

    Attributes:
        job_queue: AWS Batch job queue name.
        job_definition_name: Base name for job definitions.
        base_image: Docker base image for Batch jobs.
        timeout_seconds: Default job timeout in seconds.
        vcpu: Default number of vCPUs for jobs.
        memory_mb: Default memory in MB for jobs.
        image: Docker image for jobs (defaults to Lambda image if empty).
        env: Environment variables passed to Batch jobs.
    """

    job_queue: str = ""
    job_definition_name: str = ""
    base_image: str = "python:3.11-slim"
    timeout_seconds: int = 3600
    vcpu: int = 2
    memory_mb: int = 4096
    image: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class LokkiConfig:
    """Main lokki configuration.

    Attributes:
        build_dir: Output directory for build artifacts.
        artifact_bucket: S3 bucket for pipeline data and artifacts.
        image_repository: Docker repository ("local", "docker.io", or ECR prefix).
        aws_region: AWS region for deployments.
        aws_endpoint: AWS endpoint for local development (e.g., LocalStack).
        stepfunctions_role: ARN of existing Step Functions execution role.
        lambda_execution_role: ARN of existing Lambda execution role.
        lambda_cfg: Lambda function configuration.
        batch_cfg: AWS Batch job configuration.
        flow_name: Name of the flow (derived from function name).
        logging: Logging configuration.
    """

    # Top-level fields
    build_dir: str = "lokki-build"

    # AWS configuration (from [aws] table)
    artifact_bucket: str = ""
    image_repository: str = ""  # "local", "docker.io", or ECR prefix
    aws_region: str = "us-east-1"
    aws_endpoint: str = ""
    stepfunctions_role: str = ""
    lambda_execution_role: str = ""

    # Nested config
    lambda_cfg: LambdaConfig = field(default_factory=LambdaConfig)
    batch_cfg: BatchConfig = field(default_factory=BatchConfig)
    flow_name: str = ""
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LokkiConfig":
        """Create a LokkiConfig from a dictionary."""
        aws_config = d.get("aws", {})
        lambda_config = d.get("lambda", {})
        batch_config = d.get("batch", {})
        logging_config = d.get("logging", {})

        lambda_cfg = LambdaConfig(
            package_type=lambda_config.get("package_type", "image"),
            base_image=lambda_config.get(
                "base_image", "public.ecr.aws/lambda/python:3.13"
            ),
            timeout=lambda_config.get("timeout", 900),
            memory=lambda_config.get("memory", 512),
            image_tag=lambda_config.get("image_tag", "latest"),
            env=lambda_config.get("env", {}),
        )
        batch_cfg = BatchConfig(
            job_queue=batch_config.get("job_queue", ""),
            job_definition_name=batch_config.get("job_definition_name", ""),
            base_image=batch_config.get("base_image", "python:3.11-slim"),
            timeout_seconds=batch_config.get("timeout_seconds", 3600),
            vcpu=batch_config.get("vcpu", 2),
            memory_mb=batch_config.get("memory_mb", 4096),
            image=batch_config.get("image", ""),
            env=batch_config.get("env", {}),
        )
        logging_cfg = LoggingConfig(
            level=logging_config.get("level", "INFO"),
            format=logging_config.get("format", "human"),
            progress_interval=logging_config.get("progress_interval", 10),
            show_timestamps=logging_config.get("show_timestamps", True),
        )
        return cls(
            build_dir=d.get("build_dir", "lokki-build"),
            artifact_bucket=aws_config.get("artifact_bucket", ""),
            image_repository=aws_config.get("image_repository", ""),
            aws_region=aws_config.get("region", "us-east-1"),
            aws_endpoint=aws_config.get("endpoint", ""),
            stepfunctions_role=aws_config.get("stepfunctions_role", ""),
            lambda_execution_role=aws_config.get("lambda_execution_role", ""),
            lambda_cfg=lambda_cfg,
            batch_cfg=batch_cfg,
            flow_name=d.get("flow_name", ""),
            logging=logging_cfg,
        )


def load_config() -> LokkiConfig:
    """Load and merge configuration from global and local TOML files.

    Applies environment variable overrides.
    """
    global_cfg = _load_toml(GLOBAL_CONFIG_PATH)
    local_cfg = _load_toml(LOCAL_CONFIG_PATH)
    merged = _deep_merge(global_cfg, local_cfg)

    config = LokkiConfig.from_dict(merged)

    if env_bucket := os.environ.get("LOKKI_ARTIFACT_BUCKET"):
        config.artifact_bucket = env_bucket
    if env_repo := os.environ.get("LOKKI_IMAGE_REPOSITORY"):
        config.image_repository = env_repo
    if env_region := os.environ.get("LOKKI_AWS_REGION"):
        config.aws_region = env_region
    if env_endpoint := os.environ.get("LOKKI_AWS_ENDPOINT"):
        config.aws_endpoint = env_endpoint
    if env_build := os.environ.get("LOKKI_BUILD_DIR"):
        config.build_dir = env_build
    if env_log_level := os.environ.get("LOKKI_LOG_LEVEL"):
        config.logging.level = env_log_level
    if env_batch_queue := os.environ.get("LOKKI_BATCH_JOB_QUEUE"):
        config.batch_cfg.job_queue = env_batch_queue
    if env_batch_def := os.environ.get("LOKKI_BATCH_JOB_DEFINITION"):
        config.batch_cfg.job_definition_name = env_batch_def

    return config
