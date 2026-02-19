"""Unit tests for lokki configuration module."""

from pathlib import Path

import pytest
import yaml

from lokki.config import (
    LambdaDefaultsConfig,
    LokkiConfig,
    RolesConfig,
    _deep_merge,
    _load_yaml,
    load_config,
)


class TestDeepMerge:
    """Tests for _deep_merge function."""

    def test_scalar_override(self) -> None:
        """Test that scalar values in override replace base values."""
        base = {"key": "base_value"}
        override = {"key": "override_value"}
        result = _deep_merge(base, override)
        assert result["key"] == "override_value"

    def test_list_replacement(self) -> None:
        """Test that lists are replaced entirely, not concatenated."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = _deep_merge(base, override)
        assert result["items"] == [4, 5]

    def test_nested_dict_merge(self) -> None:
        """Test that nested dicts are merged recursively."""
        base = {"parent": {"child1": "base1", "child2": "base2"}}
        override = {"parent": {"child1": "override1"}}
        result = _deep_merge(base, override)
        assert result["parent"]["child1"] == "override1"
        assert result["parent"]["child2"] == "base2"

    def test_missing_keys_in_base(self) -> None:
        """Test that new keys in override are added."""
        base = {"existing": "value"}
        override = {"new": "added"}
        result = _deep_merge(base, override)
        assert result["existing"] == "value"
        assert result["new"] == "added"

    def test_missing_keys_in_override(self) -> None:
        """Test that missing keys in override preserve base values."""
        base = {"keep": "this", "replace": "old"}
        override = {"replace": "new"}
        result = _deep_merge(base, override)
        assert result["keep"] == "this"
        assert result["replace"] == "new"

    def test_empty_override(self) -> None:
        """Test that empty override returns copy of base."""
        base = {"key": "value"}
        override: dict = {}
        result = _deep_merge(base, override)
        assert result == base
        assert result is not base  # Should be a copy

    def test_empty_base(self) -> None:
        """Test that empty base returns copy of override."""
        base: dict = {}
        override = {"key": "value"}
        result = _deep_merge(base, override)
        assert result == override
        assert result is not override  # Should be a copy


class TestLoadYaml:
    """Tests for _load_yaml function."""

    def test_load_existing_file(self, tmp_path: Path) -> None:
        """Test loading an existing YAML file."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("key: value\nnested:\n  item: 123")
        result = _load_yaml(config_file)
        assert result == {"key": "value", "nested": {"item": 123}}

    def test_load_nonexistent_file(self) -> None:
        """Test loading a non-existent file returns empty dict."""
        result = _load_yaml(Path("/nonexistent/path/config.yml"))
        assert result == {}

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty YAML file returns empty dict."""
        config_file = tmp_path / "empty.yml"
        config_file.write_text("")
        result = _load_yaml(config_file)
        assert result == {}


class TestRolesConfig:
    """Tests for RolesConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values for RolesConfig."""
        config = RolesConfig()
        assert config.pipeline == ""
        assert config.lambda_ == ""

    def test_custom_values(self) -> None:
        """Test custom values for RolesConfig."""
        config = RolesConfig(
            pipeline="arn:aws:iam::123456789::role/pipeline",
            lambda_="arn:aws:iam::123456789::role/lambda",
        )
        assert config.pipeline == "arn:aws:iam::123456789::role/pipeline"
        assert config.lambda_ == "arn:aws:iam::123456789::role/lambda"


class TestLambdaDefaultsConfig:
    """Tests for LambdaDefaultsConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values for LambdaDefaultsConfig."""
        config = LambdaDefaultsConfig()
        assert config.timeout == 900
        assert config.memory == 512
        assert config.image_tag == "latest"

    def test_custom_values(self) -> None:
        """Test custom values for LambdaDefaultsConfig."""
        config = LambdaDefaultsConfig(timeout=300, memory=256, image_tag="v1.0")
        assert config.timeout == 300
        assert config.memory == 256
        assert config.image_tag == "v1.0"


class TestLokkiConfig:
    """Tests for LokkiConfig dataclass."""

    def test_from_dict_minimal(self) -> None:
        """Test creating LokkiConfig from minimal dict."""
        config = LokkiConfig.from_dict({})
        assert config.artifact_bucket == ""
        assert config.ecr_repo_prefix == ""
        assert config.build_dir == "lokki-build"
        assert config.roles.pipeline == ""
        assert config.roles.lambda_ == ""
        assert config.lambda_defaults.timeout == 900
        assert config.lambda_defaults.memory == 512
        assert config.lambda_defaults.image_tag == "latest"

    def test_from_dict_full(self) -> None:
        """Test creating LokkiConfig from full dict."""
        data = {
            "artifact_bucket": "my-bucket",
            "ecr_repo_prefix": "123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject",
            "build_dir": "custom-build",
            "roles": {
                "pipeline": "arn:aws:iam::123::role/pipeline",
                "lambda": "arn:aws:iam::123::role/lambda",
            },
            "lambda_env": {"LOG_LEVEL": "INFO"},
            "lambda_defaults": {"timeout": 600, "memory": 256, "image_tag": "v1.0"},
        }
        config = LokkiConfig.from_dict(data)
        assert config.artifact_bucket == "my-bucket"
        assert (
            config.ecr_repo_prefix
            == "123456789.dkr.ecr.eu-west-1.amazonaws.com/myproject"
        )
        assert config.build_dir == "custom-build"
        assert config.roles.pipeline == "arn:aws:iam::123::role/pipeline"
        assert config.roles.lambda_ == "arn:aws:iam::123::role/lambda"
        assert config.lambda_env == {"LOG_LEVEL": "INFO"}
        assert config.lambda_defaults.timeout == 600
        assert config.lambda_defaults.memory == 256
        assert config.lambda_defaults.image_tag == "v1.0"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_no_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_config when no config files exist."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "")
        monkeypatch.setenv("LOKKI_ECR_REPO_PREFIX", "")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.yml")
            )
            mp.setattr("lokki.config.LOCAL_CONFIG_PATH", Path("/nonexistent/local.yml"))

            config = load_config()
            assert config.artifact_bucket == ""
            assert config.build_dir == "lokki-build"

    def test_load_config_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment variables override config file values."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "env-bucket")
        monkeypatch.setenv("LOKKI_ECR_REPO_PREFIX", "env-ecr")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "env-build")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.yml")
            )
            mp.setattr("lokki.config.LOCAL_CONFIG_PATH", Path("/nonexistent/local.yml"))

            config = load_config()
            assert config.artifact_bucket == "env-bucket"
            assert config.ecr_repo_prefix == "env-ecr"
            assert config.build_dir == "env-build"

    def test_load_config_with_local_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading config with local config file."""
        local_config = tmp_path / "lokki.yml"
        local_config.write_text(
            yaml.dump(
                {
                    "artifact_bucket": "local-bucket",
                    "build_dir": "local-build",
                }
            )
        )

        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "")
        monkeypatch.setenv("LOKKI_ECR_REPO_PREFIX", "")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.yml")
            )
            mp.setattr("lokki.config.LOCAL_CONFIG_PATH", local_config)

            config = load_config()
            assert config.artifact_bucket == "local-bucket"
            assert config.build_dir == "local-build"
