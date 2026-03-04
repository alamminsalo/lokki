"""Tests for batch_pkg module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lokki.builder.batchjob import (
    BATCH_DOCKERFILE_TEMPLATE,
    BATCH_HANDLER_TEMPLATE,
    _get_flow_module_path,
    generate_batch_files,
)
from lokki.config import LokkiConfig


class TestGenerateBatchFiles:
    def test_generate_batch_files_default_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            result = generate_batch_files(build_dir, config)

            assert result.exists()
            assert (result / "Dockerfile").exists()
            assert (result / "batch.py").exists()
            assert (result / "batch_main.py").exists()
            assert (result / "pyproject.toml").exists()

    def test_generate_batch_files_custom_base_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict(
                {
                    "batch": {
                        "base_image": "custom-image:v1.0",
                    }
                }
            )

            result = generate_batch_files(build_dir, config)

            dockerfile_content = (result / "Dockerfile").read_text()
            assert "custom-image:v1.0" in dockerfile_content

    def test_generate_batch_files_no_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            build_dir = tmpdir / "build"

            result = generate_batch_files(build_dir, config=None)

            assert result.exists()
            dockerfile_content = (result / "Dockerfile").read_text()
            assert "FROM" in dockerfile_content

    def test_batch_handler_template_content(self):
        assert "LOKKI_STEP_NAME" in BATCH_HANDLER_TEMPLATE
        assert "LOKKI_MODULE_NAME" in BATCH_HANDLER_TEMPLATE
        assert "import importlib" in BATCH_HANDLER_TEMPLATE
        assert "make_batch_handler" in BATCH_HANDLER_TEMPLATE

    def test_batch_dockerfile_template_content(self):
        assert "FROM {base_image}" in BATCH_DOCKERFILE_TEMPLATE
        assert "pip install uv" in BATCH_DOCKERFILE_TEMPLATE
        assert "batch.py" in BATCH_DOCKERFILE_TEMPLATE
        assert "batch_main.py" in BATCH_DOCKERFILE_TEMPLATE
        assert "lokki.runtime.batch_main" in BATCH_DOCKERFILE_TEMPLATE

    def test_generate_batch_files_copies_pyproject_toml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            result = generate_batch_files(build_dir, config)

            pyproject = result / "pyproject.toml"
            assert pyproject.exists()
            assert pyproject.read_text().startswith("[project]")

    def test_generate_batch_files_creates_correct_directory_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            result = generate_batch_files(build_dir, config)

            assert result == build_dir
            assert result.is_dir()
            assert (result / "Dockerfile").exists()
            assert (result / "batch.py").exists()
            assert (result / "batch_main.py").exists()


class TestGetFlowModulePathBatch:
    """Tests for _get_flow_module_path in batch_pkg module."""

    def test_get_flow_module_path_none(self):
        """Test that None input returns None."""
        result = _get_flow_module_path(None)
        assert result is None

    def test_get_flow_module_path_module_not_in_sys_modules(self):
        """Test flow function where module is NOT in sys.modules."""

        def dummy_flow():
            pass

        dummy_flow.__module__ = "nonexistent_module"

        with patch("sys.modules", {}):
            result = _get_flow_module_path(dummy_flow)
            assert result is None

    def test_get_flow_module_path_main_argv_no_file(self):
        """Test __main__ module where sys.argv[0] doesn't exist."""

        def dummy_flow():
            pass

        dummy_flow.__module__ = "__main__"

        with patch("sys.modules", {}):
            with patch("sys.argv", []):
                result = _get_flow_module_path(dummy_flow)
                assert result is None

    def test_get_flow_module_path_main_argv_nonexistent_path(self):
        """Test __main__ module where sys.argv[0] points to non-existent file."""

        def dummy_flow():
            pass

        dummy_flow.__module__ = "__main__"

        with patch("sys.modules", {}):
            with patch("sys.argv", ["/nonexistent/path/script.py"]):
                result = _get_flow_module_path(dummy_flow)
                assert result is None

    def test_get_flow_module_path_with__fn_attribute(self):
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


class TestGenerateBatchFilesWithFlowFn:
    """Tests for generate_batch_files with flow_fn parameter."""

    def test_generate_batch_files_with_flow_fn_copies_flow_pyproject(self):
        """Test that flow's pyproject.toml is copied when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "flow_project"
            flow_dir.mkdir()

            (flow_dir / "pyproject.toml").write_text("[project]\nname = 'flow-project'")
            (flow_dir / "uv.lock").write_text("# uv lock file")

            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "flow_project.flow"

            with patch("sys.modules", {"flow_project.flow": mock_module}):
                result = generate_batch_files(build_dir, config, flow_fn=mock_flow)

            assert result.exists()
            pyproject = result / "pyproject.toml"
            assert pyproject.exists()
            assert pyproject.read_text() == "[project]\nname = 'flow-project'"

    def test_generate_batch_files_with_flow_fn_copies_flow_uv_lock(self):
        """Test that flow's uv.lock is copied when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "flow_project"
            flow_dir.mkdir()

            (flow_dir / "pyproject.toml").write_text("[project]\nname = 'flow-project'")
            (flow_dir / "uv.lock").write_text("# uv lock file")

            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "flow_project.flow"

            with patch("sys.modules", {"flow_project.flow": mock_module}):
                result = generate_batch_files(build_dir, config, flow_fn=mock_flow)

            assert result.exists()
            uv_lock = result / "uv.lock"
            assert uv_lock.exists()
            assert uv_lock.read_text() == "# uv lock file"

    def test_generate_batch_files_with_flow_fn_no_pyproject_in_flow(self):
        """Test when flow module exists but no pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            flow_dir = tmpdir / "flow_project"
            flow_dir.mkdir()

            (flow_dir / "flow.py").write_text("# flow file")

            build_dir = tmpdir / "build"

            config = LokkiConfig.from_dict({})

            mock_module = MagicMock()
            mock_module.__file__ = str(flow_dir / "flow.py")

            def mock_flow():
                pass

            mock_flow.__module__ = "flow_project.flow"

            with patch("sys.modules", {"flow_project.flow": mock_module}):
                result = generate_batch_files(build_dir, config, flow_fn=mock_flow)

            assert result.exists()
            pyproject = result / "pyproject.toml"
            assert pyproject.exists()
            assert pyproject.read_text().startswith("[project]")
