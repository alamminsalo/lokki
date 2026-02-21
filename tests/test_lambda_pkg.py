"""Tests for lambda_pkg module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from lokki.builder.lambda_pkg import generate_shared_lambda_files


def test_zip_installs_to_lambdas_not_deps():
    """Test that lokki is installed directly to lambdas directory, not to separate deps.

    This verifies the fix for the issue where dependencies were being copied
    to both deps and lambdas directories.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        build_dir = tmpdir / "lokki-build"
        lambdas_dir = build_dir / "lambdas"

        graph = MagicMock()
        graph.name = "test-flow"

        config = MagicMock()
        config.lambda_cfg.package_type = "zip"

        generate_shared_lambda_files(graph, config, build_dir, flow_fn=None)

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

        graph = MagicMock()
        graph.name = "test-flow"

        config = MagicMock()
        config.lambda_cfg.package_type = "zip"

        generate_shared_lambda_files(graph, config, build_dir, flow_fn=None)

        assert not (parent_dir / "deps").exists(), (
            "No deps directory should be created in parent directory"
        )
