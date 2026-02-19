"""State machine generation for AWS Step Functions."""

from __future__ import annotations

from typing import Any

from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def build_state_machine(graph: FlowGraph, config: LokkiConfig) -> dict[str, Any]:
    """Build a Step Functions state machine definition.

    Args:
        graph: The flow graph to convert
        config: Configuration including ECR repo prefix

    Returns:
        Amazon States Language dict
    """
    states: dict[str, Any] = {}
    state_order: list[str] = []

    prev_state: str | None = None

    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            state_name = _to_pascal(entry.node.name)
            state = _task_state(entry.node, config, graph.name)
            states[state_name] = state
            state_order.append(state_name)

            if prev_state:
                states[prev_state]["Next"] = state_name

            prev_state = state_name

        elif isinstance(entry, MapOpenEntry):
            source_name = _to_pascal(entry.source.name)
            inner_states = {}

            for _i, step_node in enumerate(entry.inner_steps):
                step_name = _to_pascal(step_node.name)
                inner_states[step_name] = {
                    "Type": "Task",
                    "Resource": _lambda_arn(config, step_node.name, graph.name),
                    "ResultPath": "$.result",
                    "End": True,
                }

            map_state = {
                "Type": "Map",
                "ItemReader": {
                    "Resource": "arn:aws:states:::s3:getObject",
                    "ReaderConfig": {"InputType": "JSON", "MaxItems": 100000},
                    "Parameters": {
                        "Bucket.$": "$.bucket",
                        "Key.$": "$.map_manifest_key",
                    },
                },
                "ItemProcessor": {
                    "ProcessorConfig": {
                        "Mode": "DISTRIBUTED",
                        "ExecutionType": "STANDARD",
                    },
                    "StartAt": list(inner_states.keys())[0],
                    "States": inner_states,
                },
                "ResultWriter": {
                    "Resource": "arn:aws:states:::s3:putObject",
                    "Parameters": {
                        "Bucket.$": "$.bucket",
                        "Prefix.$": "States.Format('lokki/"
                        + graph.name
                        + "/{}/', $.run_id)",
                    },
                },
                "Next": None,
            }

            map_state_name = f"{source_name}Map"
            states[map_state_name] = map_state
            state_order.append(map_state_name)

            if prev_state:
                states[prev_state]["Next"] = map_state_name

            prev_state = map_state_name

        elif isinstance(entry, MapCloseEntry):
            state_name = _to_pascal(entry.agg_step.name)
            state = _task_state(entry.agg_step, config, graph.name)
            states[state_name] = state
            state_order.append(state_name)

            if prev_state:
                states[prev_state]["Next"] = state_name

            prev_state = state_name

    if prev_state and prev_state in states:
        if "Next" in states[prev_state]:
            del states[prev_state]["Next"]
        states[prev_state]["End"] = True

    start_at = state_order[0] if state_order else "Pass"

    return {
        "StartAt": start_at,
        "States": states,
    }


def _task_state(step_node: Any, config: LokkiConfig, flow_name: str) -> dict[str, Any]:
    """Generate a Task state for a step."""
    return {
        "Type": "Task",
        "Resource": _lambda_arn(config, step_node.name, flow_name),
        "ResultPath": "$.result",
        "Next": None,
    }


def _lambda_arn(config: LokkiConfig, step_name: str, flow_name: str) -> str:
    """Construct Lambda ARN."""
    return (
        f"arn:aws:lambda:${{AWS::Region}}:${{AWS::AccountId}}:"
        f"function:{flow_name}-{step_name}"
    )


def _to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))
