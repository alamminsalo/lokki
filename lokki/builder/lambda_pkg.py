"""Lambda packaging utilities for building Docker images."""

from __future__ import annotations

from pathlib import Path

from lokki.config import LokkiConfig
from lokki.decorators import StepNode
from lokki.graph import FlowGraph

DOCKERFILE_TEMPLATE = """FROM public.ecr.aws/lambda/python:{image_tag} AS builder

RUN pip install uv --no-cache-dir

WORKDIR /build

COPY pyproject.toml uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml --target /build/deps

FROM public.ecr.aws/lambda/python:{image_tag}

COPY --from=builder /build/deps ${{LAMBDA_TASK_ROOT}}/

COPY lokki/ ${{LAMBDA_TASK_ROOT}}/lokki/

COPY handler.py ${{LAMBDA_TASK_ROOT}}/handler.py

CMD ["handler.lambda_handler"]
"""

HANDLER_TEMPLATE = """from {module_name} import {function_name}
from lokki.runtime.handler import make_handler

lambda_handler = make_handler({function_name})
"""


def generate_lambda_dir(
    step_node: StepNode, graph: FlowGraph, config: LokkiConfig, build_dir: Path
) -> Path:
    """Generate Lambda package directory for a step.

    Args:
        step_node: The step node to generate a Lambda for
        graph: The flow graph (used to determine module name)
        config: Configuration including lambda defaults
        build_dir: Base build directory

    Returns:
        Path to the generated Lambda directory
    """
    step_name = step_node.name
    lambda_dir = build_dir / "lambdas" / step_name
    lambda_dir.mkdir(parents=True, exist_ok=True)

    image_tag = config.lambda_cfg.image_tag
    dockerfile_content = DOCKERFILE_TEMPLATE.format(image_tag=image_tag)
    (lambda_dir / "Dockerfile").write_text(dockerfile_content)

    module_name = _get_module_name(graph)
    handler_content = HANDLER_TEMPLATE.format(
        module_name=module_name, function_name=step_name
    )
    (lambda_dir / "handler.py").write_text(handler_content)

    return lambda_dir


def _get_module_name(graph: FlowGraph) -> str:
    """Infer the Python module name from the flow graph.

    For now, assumes the flow script is named after the flow.
    """
    return f"{graph.name.replace('-', '_')}_flow"
