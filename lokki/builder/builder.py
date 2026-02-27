"""Build orchestrator for lokki flows.

This module provides the Builder class which orchestrates the build process
to generate deployment artifacts:
- Lambda packages (Dockerfiles or ZIPs)
- AWS Step Functions state machine (JSON)
- AWS CloudFormation template (YAML)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from lokki.builder.cloudformation import build_template
from lokki.builder.lambda_pkg import (
    _get_flow_module_path,
    generate_shared_lambda_files,
)
from lokki.builder.state_machine import build_state_machine
from lokki.config import LokkiConfig
from lokki.graph import FlowGraph


def _get_flow_module_name(
    flow_fn: Callable[[], FlowGraph] | None,
    graph: FlowGraph,
) -> str:
    """Get the flow module name for template generation."""
    flow_module_path = _get_flow_module_path(flow_fn)
    if flow_module_path:
        return flow_module_path.stem
    return graph.name.replace("-", "_")


def _package_deps(config: LokkiConfig) -> Path:
    """
    Collects dependencies into build_dir.
    Returns package dir path.
    """

    build_dir = Path(config.build_dir)
    requirements = build_dir / "requirements.txt"

    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Could not collect package dependencies: uv is not found.")

    # Create requirements.txt
    subprocess.run(
        [uv, "export", "--frozen", "--no-dev", "--no-editable", "-o", requirements],
        capture_output=True,
    ).check_returncode()

    # Make pkg dir
    pkg_dir = build_dir / "packages"
    pkg_dir.mkdir(parents=True)

    # Collect packages dir
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--no-installer-metadata",
            "--no-compile-bytecode",
            "--python-platform",
            "x86_64-manylinux2014",
            "--python",
            "3.13",
            "--target",
            pkg_dir,
            "-r",
            requirements,
        ],
        capture_output=True,
    ).check_returncode()

    return pkg_dir


class Builder:
    """Orchestrates building deployment artifacts for lokki flows.

    The Builder generates all necessary files for deploying a flow to AWS:
    - Lambda packages (Docker images or ZIP archives)
    - Step Functions state machine definition
    - CloudFormation template
    """

    @staticmethod
    def build(
        graph: FlowGraph,
        config: LokkiConfig,
        flow_fn: Callable[[], FlowGraph] | None = None,
    ) -> None:
        """Build deployment artifacts for a flow."""
        build_dir = Path(config.build_dir)

        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        lambdas_dir = build_dir / "lambdas"
        lambdas_dir.mkdir(parents=True, exist_ok=True)

        flow_module_name = _get_flow_module_name(flow_fn, graph)

        # Collect package deps
        pkg_dir = _package_deps(config)

        generate_shared_lambda_files(graph, config, build_dir, pkg_dir, flow_fn)

        state_machine = build_state_machine(graph, config)
        state_machine_path = build_dir / "statemachine.json"
        state_machine_path.write_text(json.dumps(state_machine, indent=2))

        template = build_template(graph, config, flow_module_name, build_dir)
        template_path = build_dir / "template.yaml"
        template_path.write_text(template)

        print(f"Build complete! Artifacts written to {build_dir}")
        print(f"  - Lambda packages: {lambdas_dir}")
        print(f"  - State machine: {state_machine_path}")
        print(f"  - CloudFormation template: {template_path}")
