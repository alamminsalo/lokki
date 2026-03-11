"""Lambda packaging utilities for building Docker images or ZIP archives."""

from __future__ import annotations

import shutil
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph

SHARED_DOCKERFILE_TEMPLATE = """FROM {base_image} AS builder

RUN pip install uv --no-cache-dir

WORKDIR /build

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

FROM {base_image}

COPY --from=builder /build/deps ${{LAMBDA_TASK_ROOT}}/

COPY handler.py ${{LAMBDA_TASK_ROOT}}/handler.py

{include_copy}

ENV LAMBDA_TASK_ROOT=/var/task

CMD ["handler.lambda_handler"]
"""

PYPI_INSTALL_TEMPLATE = ""

SHARED_HANDLER_TEMPLATE = """import os
import sys
import importlib

step_name = os.environ.get("LOKKI_STEP_NAME", "")
if not step_name:
    raise ValueError("LOKKI_STEP_NAME environment variable not set")

module_name = os.environ.get("LOKKI_MODULE_NAME", "")
if not module_name:
    raise ValueError("LOKKI_MODULE_NAME environment variable not set")

# Import the user's flow module and get the step function
mod = importlib.import_module(module_name)

step_node = getattr(mod, step_name, None)
if step_node is None:
    raise ValueError(f"Step function '{step_name}' not found in module '{module_name}'")

step_func = step_node.fn if hasattr(step_node, 'fn') else step_node

from lokki.runtime.lambdafunction import make_handler

lambda_handler = make_handler(step_func)
"""

BATCH_HANDLER_TEMPLATE = """import os
import sys

# Add current directory to path for module imports
sys.path.insert(0, os.path.dirname(__file__))

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


def generate_shared_lambda_files(
    graph: FlowGraph,
    config: LokkiConfig,
    build_dir: Path,
    pkg_dir: Path | None = None,
    flow_fn: Callable[[], FlowGraph] | None = None,
) -> Path:
    """Generate Lambda package files.

    Creates either Docker-based or ZIP-based Lambda packages based on
    the package_type configuration.

    Args:
        graph: The flow graph (used to determine module name)
        config: Configuration including lambda defaults
        build_dir: Base build directory
        flow_fn: The flow function (optional, used to detect module path)

    Returns:
        Path to the generated lambdas directory
    """
    lambdas_dir = build_dir / "lambdas"
    lambdas_dir.mkdir(parents=True, exist_ok=True)

    if config.lambda_cfg.package_type == "zip":
        if pkg_dir is None:
            raise ValueError("pkg_dir is required for ZIP package type")
        return _generate_shared_zip_package(
            graph, config, lambdas_dir, pkg_dir, flow_fn
        )
    else:
        return _generate_docker_packages(graph, config, lambdas_dir, flow_fn)


def _generate_docker_packages(
    graph: FlowGraph,
    config: LokkiConfig,
    lambdas_dir: Path,
    flow_fn: Callable[[], FlowGraph] | None = None,
) -> Path:
    """Generate Docker-based Lambda packages (container images)."""
    base_image = config.lambda_cfg.base_image

    if not base_image or base_image == "public.ecr.aws/lambda/python:3.13":
        python_version = _get_python_version_from_pyproject(flow_fn)
        base_image = f"public.ecr.aws/lambda/python:{python_version}"

    included_files = _copy_included_files(
        config, lambdas_dir, flow_fn, target_subdir="included"
    )

    if included_files:
        include_copy = "COPY included/ ${LAMBDA_TASK_ROOT}/"
    else:
        include_copy = ""

    dockerfile_content = SHARED_DOCKERFILE_TEMPLATE.format(
        base_image=base_image, include_copy=include_copy
    )
    (lambdas_dir / "Dockerfile").write_text(dockerfile_content)

    handler_content = SHARED_HANDLER_TEMPLATE
    (lambdas_dir / "handler.py").write_text(handler_content)

    _copy_project_files(lambdas_dir, flow_fn)

    return lambdas_dir


def _copy_included_files(
    config: LokkiConfig,
    build_dir: Path,
    flow_fn: Callable[[], FlowGraph] | None,
    target_subdir: str = "included",
) -> list[Path]:
    """Copy included files to build directory based on glob patterns.

    Args:
        config: LokkiConfig with include.paths
        build_dir: The build directory to copy files to
        flow_fn: The flow function to detect flow module path
        target_subdir: Subdirectory name for included files

    Returns:
        List of copied file paths
    """
    import shutil

    included_files: list[Path] = []

    if not config.include.paths:
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


def _copy_project_files(
    lambdas_dir: Path, flow_fn: Callable[[], FlowGraph] | None
) -> None:
    """Copy pyproject.toml, uv.lock, and lokki source from project or flow module."""
    lokki_root = Path(__file__).resolve().parent.parent.parent.parent

    flow_module_path = _get_flow_module_path(flow_fn)

    pyproject_target = lambdas_dir / "pyproject.toml"

    if not pyproject_target.exists():
        if flow_module_path:
            flow_pyproject = flow_module_path.parent / "pyproject.toml"
            if flow_pyproject.exists():
                shutil.copy(flow_pyproject, pyproject_target)

    uv_lock_src = lokki_root / "uv.lock"
    if uv_lock_src.exists():
        uv_lock_target = lambdas_dir / "uv.lock"
        if not uv_lock_target.exists():
            shutil.copy(uv_lock_src, uv_lock_target)

    if flow_module_path:
        flow_uv_lock = flow_module_path.parent / "uv.lock"
        if flow_uv_lock.exists():
            uv_lock_target = lambdas_dir / "uv.lock"
            if not uv_lock_target.exists():
                shutil.copy(flow_uv_lock, uv_lock_target)

    # Note: lokki is installed via pyproject.toml dependencies, not copied as source


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


def _get_flow_module_path(
    flow_fn: Callable[[], FlowGraph] | None,
) -> Path | None:
    """Detect the flow module path from the flow function.

    Args:
        flow_fn: The flow function

    Returns:
        Path to the flow module file, or None if not detectable
    """

    if flow_fn is None:
        return None

    original_fn = flow_fn
    if hasattr(flow_fn, "_fn"):
        original_fn = flow_fn._fn

    if hasattr(original_fn, "__module__"):
        module_name = original_fn.__module__

        if module_name in sys.modules:
            module = sys.modules[module_name]
            if hasattr(module, "__file__") and module.__file__:
                return Path(module.__file__)

        if module_name == "__main__":
            if hasattr(sys, "argv") and len(sys.argv) > 0:
                script_path = Path(sys.argv[0]).resolve()
                if script_path.exists():
                    return script_path

    return None


def _generate_shared_zip_package(
    graph: FlowGraph,
    config: LokkiConfig,
    lambdas_dir: Path,
    pkg_dir: Path,
    flow_fn: Callable[[], FlowGraph] | None = None,
) -> Path:
    """Generate a single shared ZIP package with all dependencies and handlers.

    Creates a single zip file containing all dependencies and generates
    separate handler files for each step. This avoids duplicating dependencies
    in multiple zip files.

    Args:
        graph: The flow graph
        config: Configuration including lambda defaults
        lambdas_dir: The lambdas directory to create files in
        flow_fn: The flow function (optional, used to detect module path)

    Returns:
        Path to the generated lambdas directory
    """

    print("Generating shared ZIP package")

    exclude_dirs = {".venv", "__pycache__", "build_dir", ".git", "lokki-build"}
    exclude_names = {".lock", "pyproject.toml", "uv.lock"}

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded from the zip."""
        for part in path.parts:
            if part in exclude_dirs:
                return True
        if path.name in exclude_names:
            return True
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            return True
        return False

    zip_path = lambdas_dir / "function.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if flow_module_path := _get_flow_module_path(flow_fn):
            flow_module_dir = flow_module_path.parent.resolve()

            if flow_module_dir.exists() and flow_module_dir.is_dir():
                for item in flow_module_dir.rglob("*.py"):
                    if should_exclude(item):
                        continue
                    arcname = item.relative_to(flow_module_dir)
                    print(f"  +prj {arcname}")
                    zf.write(item, arcname=arcname)

        (pkg_dir / "handler.py").write_text(_get_dispatcher_handler_content())

        for item in pkg_dir.rglob("*"):
            if item.parent == pkg_dir:
                print(f"  +dep {item}")
            arcname = item.relative_to(pkg_dir)
            zf.write(item, arcname=arcname)

    return lambdas_dir


def _get_dispatcher_handler_content() -> str:
    """Generate dispatcher handler code that routes based on LOKKI_STEP_NAME."""
    return """import os
import sys
import importlib
from lokki.runtime.lambdafunction import make_handler

# Add current directory to path for module imports
sys.path.insert(0, os.path.dirname(__file__))

step_name = os.environ.get("LOKKI_STEP_NAME", "")
if not step_name:
    raise ValueError("LOKKI_STEP_NAME environment variable not set")

module_name = os.environ.get("LOKKI_MODULE_NAME", "")
if not module_name:
    raise ValueError("LOKKI_MODULE_NAME environment variable not set")

mod = importlib.import_module(module_name)

step_node = getattr(mod, step_name, None)
if step_node is None:
    raise ValueError(
        f"Step function '{step_name}' not found in module '{module_name}'"
    )

step_func = step_node.fn if hasattr(step_node, 'fn') else step_node

lambda_handler = make_handler(step_func)
"""


def _create_zip(pkg_dir: Path, zip_path: Path) -> Path:
    """Creates zipfile from given directory path"""

    print(f"Created shared ZIP package: {zip_path}")
    return zip_path
