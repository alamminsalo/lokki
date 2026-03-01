"""Tests for lambda_pkg module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lokki.builder.lambda_pkg import (
    _get_flow_module_path,
    generate_shared_lambda_files,
)


def test_zip_installs_to_lambdas_not_deps():
    """Test that lokki is installed directly to lambdas directory, not to separate deps.

    This verifies the fix for the issue where dependencies were being copied
    to both deps and lambdas directories.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        build_dir = tmpdir / "lokki-build"
        lambdas_dir = build_dir / "lambdas"
        pkg_dir = build_dir / "packages"
        pkg_dir.mkdir(parents=True)

        graph = MagicMock()
        graph.name = "test-flow"

        config = MagicMock()
        config.lambda_cfg.package_type = "zip"

        generate_shared_lambda_files(graph, config, build_dir, pkg_dir, flow_fn=None)

        deps_dir = build_dir / "deps"

        assert not deps_dir.exists(), (
            f"deps directory should not exist at {deps_dir}, "
            "lokki should be installed directly to lambdas directory"
        )

        assert lambdas_dir.exists(), f"lambdas directory should exist at {lambdas_dir}"


def test_no_deps_in_parent_directory():
    """Test that no separate deps directory is created in the build parent.

    This ensures we don't create duplicate directories with the same content.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        parent_dir = tmpdir / "project"
        parent_dir.mkdir()

        build_dir = parent_dir / "lokki-build"
        pkg_dir = build_dir / "packages"
        pkg_dir.mkdir(parents=True)

        graph = MagicMock()
        graph.name = "test-flow"

        config = MagicMock()
        config.lambda_cfg.package_type = "zip"

        generate_shared_lambda_files(graph, config, build_dir, pkg_dir, flow_fn=None)

        assert not (parent_dir / "deps").exists(), (
            "No deps directory should be created in parent directory"
        )


def test_get_flow_module_path_none():
    result = _get_flow_module_path(None)
    assert result is None


def test_get_flow_module_path_with_fn():
    def dummy_flow():
        pass

    with patch("sys.modules", {"__main__": MagicMock(__file__="/fake/path/main.py")}):
        with patch("sys.argv", ["/fake/path/main.py"]):
            result = _get_flow_module_path(dummy_flow)
            assert result is None


def test_get_flow_module_path_with_module():
    mock_module = MagicMock()
    mock_module.__file__ = "/fake/path/flow.py"

    def dummy_flow():
        pass

    dummy_flow.__module__ = "test_module"

    with patch("sys.modules", {"test_module": mock_module}):
        result = _get_flow_module_path(dummy_flow)
        assert result == Path("/fake/path/flow.py")


def test_get_flow_module_path_main_no_file():
    """Test __main__ module with no __file__ attribute."""

    def dummy_flow():
        pass

    mock_module = MagicMock(spec=[])  # No __file__ attribute
    mock_module.__module__ = "__main__"

    with patch("sys.modules", {"__main__": mock_module}):
        with patch("sys.argv", []):
            result = _get_flow_module_path(dummy_flow)
            assert result is None


def test_get_flow_module_path_with__fn_attribute():
    """Test flow function with _fn attribute."""

    def actual_flow():
        pass

    def wrapper_flow():
        return actual_flow()

    wrapper_flow._fn = actual_flow
    actual_flow.__module__ = "test_module"

    mock_module = MagicMock()
    mock_module.__file__ = "/test/path.py"

    with patch("sys.modules", {"test_module": mock_module}):
        result = _get_flow_module_path(wrapper_flow)
        assert result == Path("/test/path.py")
