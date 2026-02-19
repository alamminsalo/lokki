"""Build orchestrator for lokki flows."""

from __future__ import annotations

import json
from pathlib import Path

from lokki.builder.cloudformation import build_template
from lokki.builder.lambda_pkg import generate_lambda_dir
from lokki.builder.state_machine import build_state_machine
from lokki.config import LokkiConfig
from lokki.decorators import StepNode
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


class Builder:
    @staticmethod
    def build(graph: FlowGraph, config: LokkiConfig) -> None:
        """Build deployment artifacts for a flow."""
        build_dir = Path(config.build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        lambdas_dir = build_dir / "lambdas"
        lambdas_dir.mkdir(parents=True, exist_ok=True)

        step_names_generated: set[str] = set()

        for entry in graph.entries:
            if isinstance(entry, TaskEntry):
                _generate_lambda(
                    entry.node, graph, config, build_dir, step_names_generated
                )
            elif isinstance(entry, MapOpenEntry):
                _generate_lambda(
                    entry.source, graph, config, build_dir, step_names_generated
                )
                for step in entry.inner_steps:
                    _generate_lambda(
                        step, graph, config, build_dir, step_names_generated
                    )
            elif isinstance(entry, MapCloseEntry):
                _generate_lambda(
                    entry.agg_step, graph, config, build_dir, step_names_generated
                )

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


def _generate_lambda(
    step_node: StepNode,
    graph: FlowGraph,
    config: LokkiConfig,
    build_dir: Path,
    step_names_generated: set[str],
) -> None:
    """Generate Lambda package if not already generated."""
    step_name = step_node.name
    if step_name not in step_names_generated:
        step_names_generated.add(step_name)
        generate_lambda_dir(step_node, graph, config, build_dir)
