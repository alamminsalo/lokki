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

from lokki.builder.batchjob.batch_pkg import generate_batch_files
from lokki.builder.cloudformation import build_template
from lokki.builder.lambdafunction import (
    _get_flow_module_path,
    generate_shared_lambda_files,
)
from lokki.builder.state_machine import build_state_machine
from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def _get_flow_module_name(
    flow_fn: Callable[[], FlowGraph] | None,
    graph: FlowGraph,
) -> str:
    """Get the flow module name for template generation."""
    flow_module_path = _get_flow_module_path(flow_fn)
    if flow_module_path:
        return flow_module_path.stem
    return graph.name.replace("-", "_")


def _has_lambda_steps(graph: FlowGraph) -> bool:
    """Check if the graph contains any Lambda job steps."""
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            if entry.job_type != "batch":
                return True
        elif isinstance(entry, MapOpenEntry):
            for step in entry.inner_steps:
                if getattr(step, "job_type", "lambda") != "batch":
                    return True
        elif isinstance(entry, MapCloseEntry):
            if getattr(entry.agg_step, "job_type", "lambda") != "batch":
                return True
    return False


def _has_batch_steps(graph: FlowGraph) -> bool:
    """Check if the graph contains any Batch job steps."""
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            if entry.job_type == "batch":
                return True
        elif isinstance(entry, MapOpenEntry):
            for step in entry.inner_steps:
                if getattr(step, "job_type", "lambda") == "batch":
                    return True
        elif isinstance(entry, MapCloseEntry):
            if getattr(entry.agg_step, "job_type", "lambda") == "batch":
                return True
    return False


def _package_deps(config: LokkiConfig) -> Path:
    """
    Collects dependencies into build_dir for ZIP deployments.
    Returns package dir path.

    For image deployments, this function returns an empty Path since
    dependencies are installed inside the Docker image.
    """
    build_dir = Path(config.build_dir)

    # For image deployments, dependencies are installed in Dockerfile
    if config.lambda_cfg.package_type == "image":
        return build_dir / "packages"

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

    # Map lokki architecture to manylinux platform
    arch_platform_map = {
        "x86_64": "x86_64-manylinux2014",
        "arm64": "aarch64-manylinux2014",
    }
    platform = arch_platform_map.get(
        config.lambda_cfg.architecture, "x86_64-manylinux2014"
    )
    python_version = config.lambda_cfg.python_version

    # Collect packages dir
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--no-installer-metadata",
            "--no-compile-bytecode",
            "--python-platform",
            platform,
            "--python",
            python_version,
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
        force: bool = False,
    ) -> None:
        """Build deployment artifacts for a flow.

        Args:
            graph: The flow graph to build
            config: Lokki configuration
            flow_fn: The flow function (used for module name derivation)
            force: If True, always rebuild even if build dir exists
        """
        build_dir = Path(config.build_dir)

        if build_dir.exists() and not force:
            print(f"Build directory already exists at {build_dir}, skipping build.")
            print("Use --force to rebuild.")
            return

        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        flow_module_name = _get_flow_module_name(flow_fn, graph)

        has_lambda = _has_lambda_steps(graph)
        has_batch = _has_batch_steps(graph)

        if has_lambda:
            lambdas_dir = build_dir / "lambdas"
            lambdas_dir.mkdir(parents=True, exist_ok=True)

            pkg_dir: Path | None = None
            if config.lambda_cfg.package_type == "zip":
                pkg_dir = _package_deps(config)

            generate_shared_lambda_files(graph, config, build_dir, pkg_dir, flow_fn)

        if has_batch:
            generate_batch_files(build_dir, config, flow_fn)

        state_machine = build_state_machine(graph, config)
        state_machine_path = build_dir / "statemachine.json"
        state_machine_path.write_text(json.dumps(state_machine, indent=2))

        template = build_template(graph, config, flow_module_name, build_dir)
        template_path = build_dir / "template.yaml"
        template_path.write_text(template)

        print(f"Build complete! Artifacts written to {build_dir}")
        if has_lambda:
            print(f"  - Lambda packages: {build_dir / 'lambdas'}")
        if has_batch:
            print(f"  - Batch packages: {build_dir / 'batch'}")
        print(f"  - State machine: {state_machine_path}")
        print(f"  - CloudFormation template: {template_path}")
