"""Tests for batch_pkg module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lokki.builder.batch_pkg import (
    BATCH_DOCKERFILE_TEMPLATE,
    BATCH_HANDLER_TEMPLATE,
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

            assert result == build_dir / "batch"
            assert result.is_dir()
