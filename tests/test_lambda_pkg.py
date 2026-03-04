"""Tests for lambda_pkg module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lokki.builder.lambdafunction import (
    _get_flow_module_path,
    generate_shared_lambda_files,
)


class TestGenerateSharedLambdaFilesWithFlowFn:
    """Tests for generate_shared_lambda_files with flow_fn parameter."""

    def test_generate_docker_packages_with_flow_fn_copies_flow_pyproject(self):
        """Test that flow's pyproject.toml is copied for Docker packages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "flow_project"
            flow_dir.mkdir()

            (flow_dir / "pyproject.toml").write_text("[project]\nname = 'flow-project'")
            (flow_dir / "uv.lock").write_text("# uv lock file")

            build_dir = tmpdir / "lokki-build"
            lambdas_dir = build_dir / "lambdas"
            lambdas_dir.mkdir(parents=True)

            from lokki.decorators import step
            from lokki.graph import FlowGraph

            @step
            def step1():
                pass

            graph = FlowGraph(name="test-flow", head=step1)

            from lokki.config import LokkiConfig

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "flow_project.flow"

            with patch("sys.modules", {"flow_project.flow": mock_module}):
                result = generate_shared_lambda_files(
                    graph, config, build_dir, pkg_dir=None, flow_fn=mock_flow
                )

            assert result.exists()
            pyproject = result / "pyproject.toml"
            assert pyproject.exists()
            assert pyproject.read_text() == "[project]\nname = 'flow-project'"

    def test_generate_docker_packages_with_flow_fn_copies_flow_uv_lock(self):
        """Test that flow's uv.lock path is checked (branch coverage)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "my_flow_project"
            flow_dir.mkdir()

            (flow_dir / "pyproject.toml").write_text("[project]\nname = 'my-flow'")
            (flow_dir / "uv.lock").write_text("flow-uv-lock-content")

            build_dir = tmpdir / "lokki-build"
            lambdas_dir = build_dir / "lambdas"
            lambdas_dir.mkdir(parents=True)

            (lambdas_dir / "pyproject.toml").write_text("[project]\nname = 'other'")

            from lokki.decorators import step
            from lokki.graph import FlowGraph

            @step
            def step1():
                pass

            graph = FlowGraph(name="test-flow", head=step1)

            from lokki.config import LokkiConfig

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "my_flow_project.flow"

            with patch("sys.modules", {"my_flow_project.flow": mock_module}):
                result = generate_shared_lambda_files(
                    graph, config, build_dir, pkg_dir=None, flow_fn=mock_flow
                )

            assert result.exists()
            uv_lock = result / "uv.lock"
            assert uv_lock.exists()

    def test_generate_docker_packages_with_flow_fn_no_pyproject(self):
        """Test when flow module exists but no pyproject.toml (falls back to lokki's).

        This test verifies that the code path where flow_pyproject doesn't exist
        still allows lokki's pyproject.toml to be used (line 160 in lambda_pkg.py).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "flow_project3"
            flow_dir.mkdir()

            (flow_dir / "flow.py").write_text("# flow file")

            build_dir = tmpdir / "lokki-build"
            lambdas_dir = build_dir / "lambdas"
            lambdas_dir.mkdir(parents=True)

            from lokki.decorators import step
            from lokki.graph import FlowGraph

            @step
            def step1():
                pass

            graph = FlowGraph(name="test-flow", head=step1)

            from lokki.config import LokkiConfig

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "flow_project3.flow"

            with patch("sys.modules", {"flow_project3.flow": mock_module}):
                result = generate_shared_lambda_files(
                    graph, config, build_dir, pkg_dir=None, flow_fn=mock_flow
                )

            assert result.exists()


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
