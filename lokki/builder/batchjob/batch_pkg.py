"""AWS Batch packaging utilities for lokki flows."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph

BATCH_DOCKERFILE_TEMPLATE = """FROM {base_image} AS builder

RUN pip install uv --no-cache-dir

WORKDIR /build

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

FROM {base_image}

COPY --from=builder /build/deps ${{LAMBDA_TASK_ROOT}}/

COPY batch.py ${{LAMBDA_TASK_ROOT}}/batch.py
COPY batch_main.py ${{LAMBDA_TASK_ROOT}}/batch_main.py

{include_copy}

ENV PYTHONPATH=/var/task

CMD ["python", "-m", "lokki.runtime.batch_main"]
"""

BATCH_HANDLER_TEMPLATE = """import os
import sys

step_name = os.environ.get("LOKKI_STEP_NAME", "")
if not step_name:
    raise ValueError("LOKKI_STEP_NAME environment variable not set")

module_name = os.environ.get("LOKKI_MODULE_NAME", "")
if not module_name:
    raise ValueError("LOKKI_MODULE_NAME environment variable not set")

import importlib

mod = importlib.import_module(module_name)

step_node = getattr(mod, step_name, None)
if step_node is None:
    raise ValueError(f"Step function '{step_name}' not found in module '{module_name}'")

step_func = step_node.fn if hasattr(step_node, 'fn') else step_node

from lokki.runtime.batchjob import make_batch_handler

batch_handler = make_batch_handler(step_func)
"""


def _get_flow_module_path(
    flow_fn: Callable[[], FlowGraph] | None,
) -> Path | None:
    """Detect the flow module path from the flow function."""
    if flow_fn is None:
        return None

    original_fn = flow_fn
    if hasattr(flow_fn, "_fn"):
        original_fn = flow_fn._fn

    if hasattr(original_fn, "__module__"):
        module_name = original_fn.__module__

        if module_name in __import__("sys").modules:
            module = __import__("sys").modules[module_name]
            if hasattr(module, "__file__") and module.__file__:
                return Path(module.__file__)

        if module_name == "__main__":
            import sys

            if hasattr(sys, "argv") and len(sys.argv) > 0:
                script_path = Path(sys.argv[0]).resolve()
                if script_path.exists():
                    return script_path

    return None


def _get_python_version_from_pyproject(
    flow_fn: Callable[[], FlowGraph] | None,
) -> str:
    """Extract Python version from flow module's pyproject.toml.

    Args:
        flow_fn: The flow function to detect project path

    Returns:
        Python version as major.minor string (e.g., "3.10"), or "3.13" as fallback
    """
    flow_module_path = _get_flow_module_path(flow_fn)
    if not flow_module_path:
        return "3.13"

    pyproject_path = flow_module_path.parent / "pyproject.toml"
    if not pyproject_path.exists():
        return "3.13"

    try:
        import tomllib

        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)

        requires_python = data.get("project", {}).get("requires-python", "")
        if not requires_python:
            return "3.13"

        import re

        match = re.search(r"(\d+)\.(\d+)", requires_python)
        if match:
            major = match.group(1)
            minor = match.group(2)
            return f"{major}.{minor}"

        return "3.13"
    except Exception:
        return "3.13"


def generate_batch_files(
    build_dir: Path,
    config: LokkiConfig | None = None,
    flow_fn: Callable[[], FlowGraph] | None = None,
) -> Path:
    """Generate Batch-specific packaging files.

    Args:
        build_dir: The build output directory
        config: Optional LokkiConfig for customizable base image
        flow_fn: Optional flow function for detecting project files

    Returns:
        Path to the generated batch directory
    """
    batch_dir = build_dir
    batch_dir.mkdir(parents=True, exist_ok=True)

    if config and config.batch_cfg.base_image:
        base_image = config.batch_cfg.base_image
    else:
        python_version = _get_python_version_from_pyproject(flow_fn)
        base_image = f"python:{python_version}-slim"

    included_files = _copy_included_files(config, batch_dir, flow_fn)

    if included_files:
        include_copy = "COPY included/ ./"
    else:
        include_copy = ""

    dockerfile_content = BATCH_DOCKERFILE_TEMPLATE.format(
        base_image=base_image, include_copy=include_copy
    )
    (batch_dir / "Dockerfile").write_text(dockerfile_content)

    handler_content = BATCH_HANDLER_TEMPLATE
    (batch_dir / "batch.py").write_text(handler_content)

    lokki_root = Path(__file__).resolve().parent.parent.parent.parent
    runtime_dir = lokki_root / "lokki" / "runtime"
    batch_main_src = runtime_dir / "batch_main.py"
    if batch_main_src.exists():
        batch_main_content = batch_main_src.read_text()
        (batch_dir / "batch_main.py").write_text(batch_main_content)

    pyproject_target = batch_dir / "pyproject.toml"
    lokki_pyproject = lokki_root / "pyproject.toml"
    if not pyproject_target.exists():
        flow_module_path = _get_flow_module_path(flow_fn)
        flow_pyproject = (
            flow_module_path.parent / "pyproject.toml" if flow_module_path else None
        )

        if flow_pyproject and flow_pyproject.exists():
            import shutil

            shutil.copy(flow_pyproject, pyproject_target)
        elif lokki_pyproject.exists():
            import shutil

            shutil.copy(lokki_pyproject, pyproject_target)

    uv_lock_target = batch_dir / "uv.lock"
    if not uv_lock_target.exists():
        lokki_uv_lock = lokki_root / "uv.lock"
        flow_module_path = _get_flow_module_path(flow_fn)
        flow_uv_lock = flow_module_path.parent / "uv.lock" if flow_module_path else None

        if flow_uv_lock and flow_uv_lock.exists():
            import shutil

            shutil.copy(flow_uv_lock, uv_lock_target)
        elif lokki_uv_lock.exists():
            import shutil

            shutil.copy(lokki_uv_lock, uv_lock_target)

    # Note: lokki is installed via pyproject.toml dependencies, not copied as source
    return batch_dir


def _copy_included_files(
    config: LokkiConfig | None,
    build_dir: Path,
    flow_fn: Callable[[], FlowGraph] | None,
    target_subdir: str = "included",
) -> list[Path]:
    """Copy included files to build directory based on glob patterns.

    Args:
        config: LokkiConfig with include.paths (optional)
        build_dir: The build directory to copy files to
        flow_fn: The flow function to detect flow module path
        target_subdir: Subdirectory name for included files

    Returns:
        List of copied file paths
    """
    import shutil

    included_files: list[Path] = []

    if not config or not config.include.paths:
        return included_files

    flow_module_path = _get_flow_module_path(flow_fn)
    if not flow_module_path:
        return included_files

    flow_module_dir = flow_module_path.parent.resolve()
    target_dir = build_dir / target_subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    for pattern in config.include.paths:
        matched = list(flow_module_dir.glob(pattern))

        if not matched:
            print(f"Warning: Include pattern '{pattern}' matched no files")
            continue

        for src_file in matched:
            if src_file.is_file():
                rel_path = src_file.relative_to(flow_module_dir)
                dest_file = target_dir / rel_path.name
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                included_files.append(dest_file)
                print(f"  +include {rel_path}")

    return included_files
