"""Lambda packaging utilities for building Docker images or ZIP archives."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph

SHARED_DOCKERFILE_TEMPLATE = """FROM public.ecr.aws/lambda/python:{image_tag} AS builder

RUN pip install uv --no-cache-dir

WORKDIR /build

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

FROM public.ecr.aws/lambda/python:{image_tag}

COPY --from=builder /build/deps ${{LAMBDA_TASK_ROOT}}/

COPY handler.py ${{LAMBDA_TASK_ROOT}}/handler.py

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


def generate_shared_lambda_files(
    graph: FlowGraph,
    config: LokkiConfig,
    build_dir: Path,
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
        return _generate_shared_zip_package(graph, config, lambdas_dir, flow_fn)
    else:
        return _generate_docker_packages(graph, config, lambdas_dir)


def _generate_docker_packages(
    graph: FlowGraph, config: LokkiConfig, lambdas_dir: Path
) -> Path:
    """Generate Docker-based Lambda packages (container images)."""
    image_tag = config.lambda_cfg.image_tag
    dockerfile_content = SHARED_DOCKERFILE_TEMPLATE.format(image_tag=image_tag)
    (lambdas_dir / "Dockerfile").write_text(dockerfile_content)

    handler_content = SHARED_HANDLER_TEMPLATE
    (lambdas_dir / "handler.py").write_text(handler_content)

    pyproject_src = Path(__file__).parent.parent.parent / "pyproject.toml"
    pyproject_target = lambdas_dir / "pyproject.toml"
    if not pyproject_target.exists():
        shutil.copy(pyproject_src, pyproject_target)

    uv_lock_src = Path(__file__).parent.parent.parent / "uv.lock"
    if uv_lock_src.exists():
        uv_lock_target = lambdas_dir / "uv.lock"
        if not uv_lock_target.exists():
            shutil.copy(uv_lock_src, uv_lock_target)

    return lambdas_dir


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
    print(f"  graph.name: {graph.name}")

    step_names = _get_step_names_from_graph(graph)

    build_dir = lambdas_dir.parent
    shared_zip_dir = lambdas_dir
    shared_zip_dir.mkdir(parents=True, exist_ok=True)

    uv_path = shutil.which("uv")
    if uv_path:
        subprocess.run(
            [uv_path, "pip", "install", "--target", str(shared_zip_dir), "lokki"],
            check=False,
            capture_output=True,
        )

    flow_module_path = _get_flow_module_path(flow_fn)
    if flow_module_path:
        flow_module_dir = flow_module_path.parent.resolve()
        flow_module_name = flow_module_path.stem

        if flow_module_dir.exists() and flow_module_dir.is_dir():
            build_dir_resolved = (build_dir).resolve()

            for item in flow_module_dir.iterdir():
                item_resolved = item.resolve() if item.exists() else None

                if item.name in {
                    ".git",
                    "__pycache__",
                    ".venv",
                    "venv",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    "lokki-build",
                    "lokki-builddeps",
                }:
                    continue

                if item_resolved and item_resolved == build_dir_resolved:
                    continue

                target = shared_zip_dir / item.name
                if not target.exists():
                    if item.is_dir():
                        try:
                            shutil.copytree(item, target, dirs_exist_ok=True)
                        except Exception:
                            pass
                    else:
                        try:
                            shutil.copy(item, target)
                        except Exception:
                            pass

            print(f"  Added flow directory: {flow_module_dir.name}/")
    else:
        flow_module_name = graph.name.replace("-", "_")

    module_name = flow_module_name

    handler_content = _get_dispatcher_handler_content(module_name)
    (shared_zip_dir / "handler.py").write_text(handler_content)

    _create_shared_zip(shared_zip_dir, step_names)

    print(f"Created shared ZIP package with dispatcher handler for: {step_names}")

    return lambdas_dir


def _get_dispatcher_handler_content(module_name: str) -> str:
    """Generate dispatcher handler code that routes based on LOKKI_STEP_NAME."""
    return """import os
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
    raise ValueError(
        f"Step function '{step_name}' not found in module '{module_name}'"
    )

step_func = step_node.fn if hasattr(step_node, 'fn') else step_node

from lokki.runtime.handler import make_handler

lambda_handler = make_handler(step_func)
"""


def _create_shared_zip(shared_zip_dir: Path, step_names: set[str]) -> None:
    """Create a single ZIP archive with all dependencies and handlers."""
    zip_path = shared_zip_dir / "function.zip"

    excluded_names = {".lock", "function.zip"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in shared_zip_dir.rglob("*"):
            if file_path.is_file() and file_path.name not in excluded_names:
                arcname = file_path.relative_to(shared_zip_dir)
                zf.write(file_path, arcname)

    print(f"Created shared ZIP package: {zip_path}")


def _get_step_names_from_graph(graph: FlowGraph) -> set[str]:
    """Extract unique step names from graph."""
    from lokki.graph import MapCloseEntry, MapOpenEntry, TaskEntry

    names = set()
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            names.add(entry.node.name)
        elif isinstance(entry, MapOpenEntry):
            names.add(entry.source.name)
            for step in entry.inner_steps:
                names.add(step.name)
        elif isinstance(entry, MapCloseEntry):
            names.add(entry.agg_step.name)
    return names
