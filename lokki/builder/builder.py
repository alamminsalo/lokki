"""Build orchestrator for lokki flows."""

from __future__ import annotations

import json
from pathlib import Path

from lokki.builder.cloudformation import build_template
from lokki.builder.lambda_pkg import generate_shared_lambda_files
from lokki.builder.state_machine import build_state_machine
from lokki.config import LokkiConfig
from lokki.graph import FlowGraph


class Builder:
    @staticmethod
    def build(graph: FlowGraph, config: LokkiConfig) -> None:
        """Build deployment artifacts for a flow."""
        build_dir = Path(config.build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        lambdas_dir = build_dir / "lambdas"
        lambdas_dir.mkdir(parents=True, exist_ok=True)

        generate_shared_lambda_files(graph, config, build_dir)

        state_machine = build_state_machine(graph, config)
        state_machine_path = build_dir / "statemachine.json"
        state_machine_path.write_text(json.dumps(state_machine, indent=2))

        template = build_template(graph, config)
        template_path = build_dir / "template.yaml"
        template_path.write_text(template)

        print(f"Build complete! Artifacts written to {build_dir}")
        print(f"  - Lambda packages: {lambdas_dir}")
        print(f"  - State machine: {state_machine_path}")
        print(f"  - CloudFormation template: {template_path}")
