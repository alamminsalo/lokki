"""Shared test utilities."""

import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_aws_env():
    """Remove AWS_ENDPOINT_URL to prevent tests from hitting LocalStack."""
    original = os.environ.get("AWS_ENDPOINT_URL")
    os.environ.pop("AWS_ENDPOINT_URL", None)
    yield
    if original:
        os.environ["AWS_ENDPOINT_URL"] = original


def create_build_dir() -> Path:
    """Create a temp build dir with statemachine.json."""
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "statemachine.json").write_text(
        json.dumps({"StartAt": "End", "States": {"End": {"Type": "Pass"}}})
    )
    return tmpdir
