"""Configuration loading and management for lokki."""

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
    """Lambda configuration."""

    package_type: str = "image"  # "image" or "zip"
    timeout: int = 900
    memory: int = 512
    image_tag: str = "latest"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class BatchConfig:
    """AWS Batch configuration."""

    job_queue: str = ""
    job_definition_name: str = ""
    timeout_seconds: int = 3600
    vcpu: int = 2
    memory_mb: int = 4096
    image: str = ""


@dataclass
class LokkiConfig:
    """Main lokki configuration."""

    # Top-level fields
    build_dir: str = "lokki-build"

    # AWS configuration (from [aws] table)
    artifact_bucket: str = ""
    image_repository: str = ""  # "local", "docker.io", or ECR prefix
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
            timeout=lambda_config.get("timeout", 900),
            memory=lambda_config.get("memory", 512),
            image_tag=lambda_config.get("image_tag", "latest"),
            env=lambda_config.get("env", {}),
        )
        batch_cfg = BatchConfig(
            job_queue=batch_config.get("job_queue", ""),
            job_definition_name=batch_config.get("job_definition_name", ""),
            timeout_seconds=batch_config.get("timeout_seconds", 3600),
            vcpu=batch_config.get("vcpu", 2),
            memory_mb=batch_config.get("memory_mb", 4096),
            image=batch_config.get("image", ""),
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
