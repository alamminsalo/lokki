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
COPY batch.py ${{LAMBDA_TASK_ROOT}}/batch.py
COPY batch_main.py ${{LAMBDA_TASK_ROOT}}/batch_main.py

ENV LAMBDA_TASK_ROOT=/var/task

CMD ["handler.lambda_handler"]
"""

PYPI_INSTALL_TEMPLATE = ""

SHARED_HANDLER_TEMPLATE = """import os
import sys

step_name = os.environ.get("LOKKI_STEP_NAME", "")
if not step_name:
    raise ValueError("LOKKI_STEP_NAME environment variable not set")

module_name = os.environ.get("LOKKI_MODULE_NAME", "")
if not module_name:
    raise ValueError("LOKKI_MODULE_NAME environment variable not set")

# Import the user's flow module and get the step function
import importlib
mod = importlib.import_module(module_name)

step_func = getattr(mod, step_name, None)
if step_func is None:
    raise ValueError(f"Step function '{step_name}' not found in module '{module_name}'")

from lokki.runtime.handler import make_handler

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

from lokki.runtime.batch import make_batch_handler

batch_handler = make_batch_handler(step_func)
"""


def generate_shared_lambda_files(
    graph: FlowGraph,
    config: LokkiConfig,
    build_dir: Path,
    pkg_dir: Path,
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
    dockerfile_content = SHARED_DOCKERFILE_TEMPLATE.format(base_image=base_image)
    (lambdas_dir / "Dockerfile").write_text(dockerfile_content)

    handler_content = SHARED_HANDLER_TEMPLATE
    (lambdas_dir / "handler.py").write_text(handler_content)

    batch_handler_content = BATCH_HANDLER_TEMPLATE
    (lambdas_dir / "batch.py").write_text(batch_handler_content)

    runtime_dir = Path(__file__).parent.parent / "runtime"
    batch_main_src = runtime_dir / "batch_main.py"
    if batch_main_src.exists():
        batch_main_content = batch_main_src.read_text()
        (lambdas_dir / "batch_main.py").write_text(batch_main_content)

    _copy_project_files(lambdas_dir, flow_fn)

    return lambdas_dir


def _copy_project_files(
    lambdas_dir: Path, flow_fn: Callable[[], FlowGraph] | None
) -> None:
    """Copy pyproject.toml and uv.lock from project or flow module."""
    lokki_dir = Path(__file__).parent.parent.parent

    pyproject_src = lokki_dir / "pyproject.toml"
    pyproject_target = lambdas_dir / "pyproject.toml"

    if pyproject_target.exists():
        return

    if pyproject_src.exists():
        shutil.copy(pyproject_src, pyproject_target)
        return

    flow_module_path = _get_flow_module_path(flow_fn)
    if flow_module_path:
        flow_pyproject = flow_module_path.parent / "pyproject.toml"
        if flow_pyproject.exists():
            shutil.copy(flow_pyproject, pyproject_target)

    uv_lock_src = lokki_dir / "uv.lock"
    if uv_lock_src.exists():
        uv_lock_target = lambdas_dir / "uv.lock"
        if not uv_lock_target.exists():
            shutil.copy(uv_lock_src, uv_lock_target)
        return

    if flow_module_path:
        flow_uv_lock = flow_module_path.parent / "uv.lock"
        if flow_uv_lock.exists():
            uv_lock_target = lambdas_dir / "uv.lock"
            if not uv_lock_target.exists():
                shutil.copy(flow_uv_lock, uv_lock_target)


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

    EXCLUDE_DIRS = {".venv", "__pycache__", "build_dir", ".git", "lokki-build"}
    EXCLUDE_NAMES = {".lock", "pyproject.toml", "uv.lock"}

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded from the zip."""
        for part in path.parts:
            if part in EXCLUDE_DIRS:
                return True
        if path.name in EXCLUDE_NAMES:
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
from lokki.runtime.handler import make_handler

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
