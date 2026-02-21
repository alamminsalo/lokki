"""Unit tests for lokki configuration module."""

from pathlib import Path

import pytest

from lokki.config import (
    LambdaConfig,
    LokkiConfig,
    _deep_merge,
    _load_toml,
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
        assert result is not base

    def test_empty_base(self) -> None:
        """Test that empty base returns copy of override."""
        base: dict = {}
        override = {"key": "value"}
        result = _deep_merge(base, override)
        assert result == override
        assert result is not override


class TestLoadToml:
    """Tests for _load_toml function."""

    def test_load_existing_file(self, tmp_path: Path) -> None:
        """Test loading an existing TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('key = "value"\nnested = { item = 123 }')
        result = _load_toml(config_file)
        assert result == {"key": "value", "nested": {"item": 123}}

    def test_load_nonexistent_file(self) -> None:
        """Test loading a non-existent file returns empty dict."""
        result = _load_toml(Path("/nonexistent/path/config.toml"))
        assert result == {}

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty TOML file returns empty dict."""
        config_file = tmp_path / "empty.toml"
        config_file.write_text("")
        result = _load_toml(config_file)
        assert result == {}


class TestLambdaConfig:
    """Tests for LambdaConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values for LambdaConfig."""
        config = LambdaConfig()
        assert config.package_type == "image"
        assert config.timeout == 900
        assert config.memory == 512
        assert config.image_tag == "latest"
        assert config.env == {}

    def test_custom_values(self) -> None:
        """Test custom values for LambdaConfig."""
        config = LambdaConfig(
            package_type="zip",
            timeout=300,
            memory=256,
            image_tag="v1.0",
            env={"KEY": "val"},
        )
        assert config.package_type == "zip"
        assert config.timeout == 300
        assert config.memory == 256
        assert config.image_tag == "v1.0"
        assert config.env == {"KEY": "val"}


class TestLokkiConfig:
    """Tests for LokkiConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values for LokkiConfig."""
        config = LokkiConfig()
        assert config.build_dir == "lokki-build"
        assert config.artifact_bucket == ""
        assert config.image_repository == ""
        assert config.stepfunctions_role == ""
        assert config.lambda_execution_role == ""
        assert config.aws_endpoint == ""
        assert config.lambda_cfg.package_type == "image"
        assert config.lambda_cfg.timeout == 900
        assert config.lambda_cfg.memory == 512

    def test_from_dict_minimal(self) -> None:
        """Test creating LokkiConfig from minimal dict."""
        config = LokkiConfig.from_dict({})
        assert config.build_dir == "lokki-build"
        assert config.artifact_bucket == ""
        assert config.image_repository == ""
        assert config.stepfunctions_role == ""
        assert config.lambda_execution_role == ""
        assert config.aws_endpoint == ""
        assert config.lambda_cfg.package_type == "image"
        assert config.lambda_cfg.timeout == 900
        assert config.lambda_cfg.memory == 512

    def test_from_dict_full(self) -> None:
        """Test creating LokkiConfig from full dict."""
        data = {
            "build_dir": "custom-build",
            "aws": {
                "artifact_bucket": "my-bucket",
                "image_repository": "123456789.dkr.ecr.us-east-1.amazonaws.com/myproject",
                "endpoint": "http://localhost:4566",
                "stepfunctions_role": "arn:aws:iam::123::role/sfn",
                "lambda_execution_role": "arn:aws:iam::123::role/lambda",
            },
            "lambda": {
                "package_type": "zip",
                "timeout": 600,
                "memory": 256,
                "image_tag": "v1.0",
                "env": {"LOG_LEVEL": "INFO"},
            },
            "logging": {
                "level": "DEBUG",
                "format": "json",
            },
        }
        config = LokkiConfig.from_dict(data)
        assert config.build_dir == "custom-build"
        assert config.artifact_bucket == "my-bucket"
        assert (
            config.image_repository
            == "123456789.dkr.ecr.us-east-1.amazonaws.com/myproject"
        )
        assert config.stepfunctions_role == "arn:aws:iam::123::role/sfn"
        assert config.lambda_execution_role == "arn:aws:iam::123::role/lambda"
        assert config.aws_endpoint == "http://localhost:4566"
        assert config.lambda_cfg.package_type == "zip"
        assert config.lambda_cfg.timeout == 600
        assert config.lambda_cfg.memory == 256
        assert config.lambda_cfg.image_tag == "v1.0"
        assert config.lambda_cfg.env == {"LOG_LEVEL": "INFO"}
        assert config.logging.level == "DEBUG"
        assert config.logging.format == "json"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_no_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test load_config when no config files exist."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "")
        monkeypatch.setenv("LOKKI_IMAGE_REPOSITORY", "")
        monkeypatch.setenv("LOKKI_AWS_ENDPOINT", "")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.toml")
            )
            mp.setattr(
                "lokki.config.LOCAL_CONFIG_PATH", Path("/nonexistent/local.toml")
            )

            config = load_config()
            assert config.artifact_bucket == ""
            assert config.build_dir == "lokki-build"

    def test_load_config_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment variables override config file values."""
        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "env-bucket")
        monkeypatch.setenv("LOKKI_IMAGE_REPOSITORY", "env-repo")
        monkeypatch.setenv("LOKKI_AWS_ENDPOINT", "http://localhost:4566")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "env-build")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.toml")
            )
            mp.setattr(
                "lokki.config.LOCAL_CONFIG_PATH", Path("/nonexistent/local.toml")
            )

            config = load_config()
            assert config.artifact_bucket == "env-bucket"
            assert config.image_repository == "env-repo"
            assert config.aws_endpoint == "http://localhost:4566"
            assert config.build_dir == "env-build"

    def test_load_config_with_local_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading config with local config file."""
        local_config = tmp_path / "lokki.toml"
        local_config.write_text("[aws]\nartifact_bucket = 'local-bucket'")

        monkeypatch.setenv("LOKKI_ARTIFACT_BUCKET", "")
        monkeypatch.setenv("LOKKI_IMAGE_REPOSITORY", "")
        monkeypatch.setenv("LOKKI_AWS_ENDPOINT", "")
        monkeypatch.setenv("LOKKI_BUILD_DIR", "")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "lokki.config.GLOBAL_CONFIG_PATH", Path("/nonexistent/global.toml")
            )
            mp.setattr("lokki.config.LOCAL_CONFIG_PATH", local_config)

            config = load_config()
            assert config.artifact_bucket == "local-bucket"
