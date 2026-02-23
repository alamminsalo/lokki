"""AWS Batch packaging utilities for lokki flows."""

from __future__ import annotations

from pathlib import Path

from lokki.config import LokkiConfig

BATCH_DOCKERFILE_TEMPLATE = """FROM {base_image} AS builder

RUN pip install uv --no-cache-dir

WORKDIR /build

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

FROM {base_image}

COPY --from=builder /build/deps ${{LAMBDA_TASK_ROOT}}/

COPY batch.py ${{LAMBDA_TASK_ROOT}}/batch.py
COPY batch_main.py ${{LAMBDA_TASK_ROOT}}/batch_main.py
COPY handler.py ${{LAMBDA_TASK_ROOT}}/handler.py

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

from lokki.runtime.batch import make_batch_handler

batch_handler = make_batch_handler(step_func)
"""


def generate_batch_files(
    build_dir: Path,
    config: LokkiConfig | None = None,
) -> Path:
    """Generate Batch-specific packaging files.

    Args:
        build_dir: The build output directory
        config: Optional LokkiConfig for customizable base image

    Returns:
        Path to the generated batch directory
    """
    batch_dir = build_dir / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)

    if config and config.batch_cfg.base_image:
        base_image = config.batch_cfg.base_image
    else:
        from lokki.config import BatchConfig

        base_image = BatchConfig().base_image

    dockerfile_content = BATCH_DOCKERFILE_TEMPLATE.format(base_image=base_image)
    (batch_dir / "Dockerfile").write_text(dockerfile_content)

    handler_content = BATCH_HANDLER_TEMPLATE
    (batch_dir / "batch.py").write_text(handler_content)

    runtime_dir = Path(__file__).parent.parent / "runtime"
    batch_main_src = runtime_dir / "batch_main.py"
    if batch_main_src.exists():
        batch_main_content = batch_main_src.read_text()
        (batch_dir / "batch_main.py").write_text(batch_main_content)

    pyproject_src = Path(__file__).parent.parent.parent / "pyproject.toml"
    pyproject_target = batch_dir / "pyproject.toml"
    if not pyproject_target.exists():
        import shutil

        shutil.copy(pyproject_src, pyproject_target)

    uv_lock_src = Path(__file__).parent.parent.parent / "uv.lock"
    if uv_lock_src.exists():
        import shutil

        uv_lock_target = batch_dir / "uv.lock"
        if not uv_lock_target.exists():
            shutil.copy(uv_lock_src, uv_lock_target)

    return batch_dir
