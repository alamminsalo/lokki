"""Configuration loading and management for lokki."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

GLOBAL_CONFIG_PATH = Path.home() / ".lokki" / "lokki.yml"
LOCAL_CONFIG_PATH = Path.cwd() / "lokki.yml"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict if not found."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base. Lists and scalars are replaced; dicts are merged recursively."""
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
class LambdaDefaultsConfig:
    """Default Lambda configuration."""

    timeout: int = 900
    memory: int = 512
    image_tag: str = "latest"


@dataclass
class LokkiConfig:
    """Main lokki configuration."""

    artifact_bucket: str = ""
    ecr_repo_prefix: str = ""
    build_dir: str = "lokki-build"
    roles: RolesConfig = field(default_factory=RolesConfig)
    lambda_env: dict[str, str] = field(default_factory=dict)
    lambda_defaults: LambdaDefaultsConfig = field(default_factory=LambdaDefaultsConfig)

    @classmethod
    def from_dict(cls, d: dict) -> "LokkiConfig":
        """Create a LokkiConfig from a dictionary."""
        roles = RolesConfig(
            pipeline=d.get("roles", {}).get("pipeline", ""),
            lambda_=d.get("roles", {}).get("lambda", ""),
        )
        lambda_defaults = LambdaDefaultsConfig(
            timeout=d.get("lambda_defaults", {}).get("timeout", 900),
            memory=d.get("lambda_defaults", {}).get("memory", 512),
            image_tag=d.get("lambda_defaults", {}).get("image_tag", "latest"),
        )
        return cls(
            artifact_bucket=d.get("artifact_bucket", ""),
            ecr_repo_prefix=d.get("ecr_repo_prefix", ""),
            build_dir=d.get("build_dir", "lokki-build"),
            roles=roles,
            lambda_env=d.get("lambda_env", {}),
            lambda_defaults=lambda_defaults,
        )


def load_config() -> LokkiConfig:
    """Load and merge configuration from global and local YAML files with env overrides."""
    global_cfg = _load_yaml(GLOBAL_CONFIG_PATH)
    local_cfg = _load_yaml(LOCAL_CONFIG_PATH)
    merged = _deep_merge(global_cfg, local_cfg)

    config = LokkiConfig.from_dict(merged)

    if env_bucket := os.environ.get("LOKKI_ARTIFACT_BUCKET"):
        config.artifact_bucket = env_bucket
    if env_ecr := os.environ.get("LOKKI_ECR_REPO_PREFIX"):
        config.ecr_repo_prefix = env_ecr
    if env_build := os.environ.get("LOKKI_BUILD_DIR"):
        config.build_dir = env_build

    return config
