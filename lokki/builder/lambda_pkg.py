"""Lambda packaging utilities for building Docker images."""

from __future__ import annotations

import shutil
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
    """Generate shared Lambda package files.

    Creates a single Dockerfile and handler that dispatches to the correct
    step function based on environment variables.

    Args:
        graph: The flow graph (used to determine module name)
        config: Configuration including lambda defaults
        build_dir: Base build directory

    Returns:
        Path to the generated lambdas directory
    """
    lambdas_dir = build_dir / "lambdas"
    lambdas_dir.mkdir(parents=True, exist_ok=True)

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
