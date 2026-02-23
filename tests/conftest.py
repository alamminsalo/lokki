"""Shared test utilities."""

import json
import tempfile
from pathlib import Path


def create_build_dir() -> Path:
    """Create a temp build dir with statemachine.json."""
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "statemachine.json").write_text(
        json.dumps({"StartAt": "End", "States": {"End": {"Type": "Pass"}}})
    )
    return tmpdir
