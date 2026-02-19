"""Configuration loading and management for lokki."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lokki.logging import LoggingConfig

GLOBAL_CONFIG_PATH = Path.home() / ".lokki" / "lokki.yml"
LOCAL_CONFIG_PATH = Path.cwd() / "lokki.yml"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if not found."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
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
class RolesConfig:
    """IAM role configuration."""

    pipeline: str = ""
    lambda_: str = ""


@dataclass
class AwsConfig:
    """AWS configuration."""

    artifact_bucket: str = ""
    ecr_repo_prefix: str = ""
    endpoint: str = ""
    roles: RolesConfig = field(default_factory=RolesConfig)


@dataclass
class LambdaConfig:
    """Lambda configuration."""

    timeout: int = 900
    memory: int = 512
    image_tag: str = "latest"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class LokkiConfig:
    """Main lokki configuration."""

    aws: AwsConfig = field(default_factory=AwsConfig)
    lambda_cfg: LambdaConfig = field(default_factory=LambdaConfig)
    build_dir: str = "lokki-build"
    flow_name: str = ""
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LokkiConfig":
        """Create a LokkiConfig from a dictionary."""
        roles_cfg = RolesConfig(
            pipeline=d.get("aws", {}).get("roles", {}).get("pipeline", ""),
            lambda_=d.get("aws", {}).get("roles", {}).get("lambda", ""),
        )
        aws_cfg = AwsConfig(
            artifact_bucket=d.get("aws", {}).get("artifact_bucket", ""),
            ecr_repo_prefix=d.get("aws", {}).get("ecr_repo_prefix", ""),
            endpoint=d.get("aws", {}).get("endpoint", ""),
            roles=roles_cfg,
        )
        lambda_cfg = LambdaConfig(
            timeout=d.get("lambda", {}).get("timeout", 900),
            memory=d.get("lambda", {}).get("memory", 512),
            image_tag=d.get("lambda", {}).get("image_tag", "latest"),
            env=d.get("lambda", {}).get("env", {}),
        )
        logging_cfg = LoggingConfig(
            level=d.get("logging", {}).get("level", "INFO"),
            format=d.get("logging", {}).get("format", "human"),
            progress_interval=d.get("logging", {}).get("progress_interval", 10),
            show_timestamps=d.get("logging", {}).get("show_timestamps", True),
        )
        return cls(
            aws=aws_cfg,
            lambda_cfg=lambda_cfg,
            build_dir=d.get("build_dir", "lokki-build"),
            flow_name=d.get("flow_name", ""),
            logging=logging_cfg,
        )


def load_config() -> LokkiConfig:
    """Load and merge configuration from global and local YAML files.

    Applies environment variable overrides.
    """
    global_cfg = _load_yaml(GLOBAL_CONFIG_PATH)
    local_cfg = _load_yaml(LOCAL_CONFIG_PATH)
    merged = _deep_merge(global_cfg, local_cfg)

    config = LokkiConfig.from_dict(merged)

    if env_bucket := os.environ.get("LOKKI_ARTIFACT_BUCKET"):
        config.aws.artifact_bucket = env_bucket
    if env_ecr := os.environ.get("LOKKI_ECR_REPO_PREFIX"):
        config.aws.ecr_repo_prefix = env_ecr
    if env_endpoint := os.environ.get("LOKKI_AWS_ENDPOINT"):
        config.aws.endpoint = env_endpoint
    if env_build := os.environ.get("LOKKI_BUILD_DIR"):
        config.build_dir = env_build
    if env_log_level := os.environ.get("LOKKI_LOG_LEVEL"):
        config.logging.level = env_log_level

    return config
