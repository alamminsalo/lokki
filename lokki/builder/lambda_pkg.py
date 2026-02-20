"""Lambda packaging utilities for building Docker images or ZIP archives."""

from __future__ import annotations

import shutil
import zipfile
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
    graph: FlowGraph, config: LokkiConfig, build_dir: Path
) -> Path:
    """Generate Lambda package files.

    Creates either Docker-based or ZIP-based Lambda packages based on
    the package_type configuration.

    Args:
        graph: The flow graph (used to determine module name)
        config: Configuration including lambda defaults
        build_dir: Base build directory

    Returns:
        Path to the generated lambdas directory
    """
    lambdas_dir = build_dir / "lambdas"
    lambdas_dir.mkdir(parents=True, exist_ok=True)

    if config.lambda_cfg.package_type == "zip":
        return _generate_shared_zip_package(graph, config, lambdas_dir)
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


def _generate_shared_zip_package(
    graph: FlowGraph, config: LokkiConfig, lambdas_dir: Path
) -> Path:
    """Generate a single shared ZIP package with all dependencies and handlers.

    Creates a single zip file containing all dependencies and generates
    separate handler files for each step. This avoids duplicating dependencies
    in multiple zip files.

    Args:
        graph: The flow graph
        config: Configuration including lambda defaults
        lambdas_dir: The lambdas directory to create files in

    Returns:
        Path to the generated lambdas directory
    """
    lokki_src = Path(__file__).parent.parent
    project_root = lokki_src.parent

    print("Generating shared ZIP package")
    print(f"  lokki_src: {lokki_src}")
    print(f"  project_root: {project_root}")
    print(f"  graph.name: {graph.name}")

    step_names = _get_step_names_from_graph(graph)

    build_dir = lambdas_dir.parent
    deps_dir = build_dir / "deps"

    if not deps_dir.exists():
        deps_dir.mkdir(parents=True, exist_ok=True)
        import subprocess

        subprocess.run(
            ["uv", "pip", "install", "-t", str(deps_dir), "boto3", "pyyaml"],
            check=True,
            capture_output=True,
        )

    shared_zip_dir = lambdas_dir
    shared_zip_dir.mkdir(parents=True, exist_ok=True)

    lokki_target_dir = shared_zip_dir / "lokki"
    if not lokki_target_dir.exists():
        lokki_target_dir.mkdir(parents=True, exist_ok=True)

    for item in lokki_src.rglob("*"):
        if item.is_file():
            relative = item.relative_to(lokki_src)
            target = lokki_target_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(item, target)

    flow_examples_dir = project_root / "examples"
    if flow_examples_dir.exists() and flow_examples_dir.is_dir():
        for py_file in flow_examples_dir.glob("*.py"):
            if not py_file.name.startswith("_"):
                target = shared_zip_dir / py_file.name
                if not target.exists():
                    shutil.copy(py_file, target)

    for dep_item in deps_dir.iterdir():
        target = shared_zip_dir / dep_item.name
        if not target.exists():
            if dep_item.is_dir():
                shutil.copytree(dep_item, target, dirs_exist_ok=True)
            else:
                shutil.copy(dep_item, target)

    module_name = graph.name.replace("-", "_")

    handler_content = _get_dispatcher_handler_content(module_name)
    (shared_zip_dir / "handler.py").write_text(handler_content)

    _create_shared_zip(shared_zip_dir, step_names)

    print(f"Created shared ZIP package with dispatcher handler for: {step_names}")

    return lambdas_dir


def _get_dispatcher_handler_content(module_name: str) -> str:
    """Generate dispatcher handler code that routes based on LOKKI_STEP_NAME."""
    return """import os
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
