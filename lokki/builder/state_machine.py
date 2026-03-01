"""State machine generation for AWS Step Functions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lokki._utils import to_pascal
from lokki.config import LokkiConfig
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry

if TYPE_CHECKING:
    from lokki.decorators import RetryConfig


def _exception_to_error_equals(exc_type: type[Exception]) -> str:
    """Map Python exception types to AWS Step Functions error names."""
    exc_map: dict[type[Exception], str] = {
        Exception: "Lambda.ServiceException",
        ConnectionError: "Lambda.SdkClientException",
        TimeoutError: "Lambda.AWSException",
        OSError: "Lambda.SdkClientException",
        IOError: "Lambda.SdkClientException",
    }
    return exc_map.get(exc_type, f"java.lang.RuntimeException.{exc_type.__name__}")


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

    # InitFlow Pass state to prepare input for first step
    # Transforms execution input -> {"input": {}, "flow": {"run_id": ..., "params": {...}}}
    # First step gets empty input - flow params passed via kwargs
    states["InitFlow"] = {
        "Type": "Pass",
        "Parameters": {
            "input": {},
            "flow": {
                "run_id.$": "$$.Execution.Id",
                "params.$": "$$.Execution.Input",
            },
        },
        "Next": None,
    }

    first_state: str | None = None

    prev_state: str | None = None

    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            state_name = to_pascal(entry.node.name)
            if first_state is None:
                first_state = state_name
            job_type = entry.job_type or "lambda"
            if job_type == "batch":
                state = _batch_task_state(entry, config, graph.name)
            else:
                state = _task_state(entry.node, config, graph.name)
            states[state_name] = state
            state_order.append(state_name)

            if prev_state:
                states[prev_state]["Next"] = state_name

            prev_state = state_name

        elif isinstance(entry, MapOpenEntry):
            source_name = to_pascal(entry.source.name)
            if first_state is None:
                first_state = f"{source_name}Map"
            inner_states = {}

            step_names = [to_pascal(step_node.name) for step_node in entry.inner_steps]

            for i, step_node in enumerate(entry.inner_steps):
                step_name = to_pascal(step_node.name)
                job_type = getattr(step_node, "job_type", "lambda") or "lambda"
                if job_type == "batch":
                    inner_states[step_name] = _batch_task_state_from_node(
                        step_node, config, graph.name
                    )
                else:
                    inner_states[step_name] = {
                        "Type": "Task",
                        "Resource": _lambda_arn(config, step_node.name, graph.name),
                        "Parameters": {
                            "input.$": "$.input",
                            "flow": {
                                "run_id.$": "$$.Execution.Id",
                                "params.$": "$$.Execution.Input",
                            },
                        },
                        "InputPath": "$",
                        "ResultPath": "$.input",
                    }

                if i < len(entry.inner_steps) - 1:
                    inner_states[step_name]["Next"] = step_names[i + 1]
                else:
                    inner_states[step_name]["End"] = True

            map_state: dict[str, Any] = {
                "Type": "Map",
                "ItemReader": {
                    "Resource": "arn:aws:states:::s3:getObject",
                    "ReaderConfig": {"InputType": "JSON", "MaxItems": 100000},
                    "Parameters": {
                        "Bucket": config.artifact_bucket,
                        "Key.$": "$.input",
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
                "Next": None,
            }

            if entry.concurrency_limit is not None:
                map_state["MaxConcurrency"] = entry.concurrency_limit

            map_state_name = f"{source_name}Map"
            states[map_state_name] = map_state
            state_order.append(map_state_name)

            if prev_state:
                states[prev_state]["Next"] = map_state_name

            prev_state = map_state_name

        elif isinstance(entry, MapCloseEntry):
            state_name = to_pascal(entry.agg_step.name)
            job_type = getattr(entry.agg_step, "job_type", "lambda") or "lambda"
            if job_type == "batch":
                state = _batch_task_state_from_node(entry.agg_step, config, graph.name)
            else:
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

    # Connect InitFlow to first state
    assert first_state, "No first state found"
    states["InitFlow"]["Next"] = first_state

    return {
        "StartAt": "InitFlow",
        "States": states,
    }


def _task_state(step_node: Any, config: LokkiConfig, flow_name: str) -> dict[str, Any]:
    """Generate a Task state for a Lambda step."""
    state: dict[str, Any] = {
        "Type": "Task",
        "Resource": _lambda_arn(config, step_node.name, flow_name),
        "InputPath": "$",
        "ResultPath": "$.input",
        "Next": None,
    }

    retry_config = getattr(step_node, "retry", None)
    if retry_config and retry_config.retries > 0:
        state["Retry"] = _build_retry_field(retry_config)

    return state


def _batch_task_state(
    entry: Any, config: LokkiConfig, flow_name: str
) -> dict[str, Any]:
    """Generate a Task state for a Batch step."""
    vcpu = entry.vcpu if entry.vcpu is not None else config.batch_cfg.vcpu
    memory_mb = (
        entry.memory_mb if entry.memory_mb is not None else config.batch_cfg.memory_mb
    )

    state: dict[str, Any] = {
        "Type": "Task",
        "Resource": "arn:aws:states:::batch:submitJob.sync",
        "Parameters": {
            "JobDefinition": {"Ref": "BatchJobDefinition"},
            "JobName.$": f"States.Format('{flow_name}-{{}}', $.step_name)",
            "JobQueue": {"Ref": "BatchJobQueue"},
            "ContainerOverrides": {
                "Vcpus": vcpu,
                "Memory": memory_mb,
            },
            "Environment": [
                {"Name": "LOKKI_ARTIFACT_BUCKET", "Value": config.artifact_bucket},
                {"Name": "LOKKI_FLOW_NAME", "Value": flow_name},
                {"Name": "LOKKI_STEP_NAME", "Value.$": "$.step_name"},
                {"Name": "LOKKI_INPUT_URL", "Value.$": "$.input"},
            ],
        },
        "ResultPath": "$.input",
        "Next": None,
    }

    retry_config = getattr(entry, "retry", None)
    if retry_config and retry_config.retries > 0:
        state["Retry"] = _build_retry_field(retry_config)

    return state


def _batch_task_state_from_node(
    step_node: Any, config: LokkiConfig, flow_name: str
) -> dict[str, Any]:
    """Generate a Task state for a Batch step from a StepNode."""
    vcpu = step_node.vcpu if step_node.vcpu is not None else config.batch_cfg.vcpu
    memory_mb = (
        step_node.memory_mb
        if step_node.memory_mb is not None
        else config.batch_cfg.memory_mb
    )

    state: dict[str, Any] = {
        "Type": "Task",
        "Resource": "arn:aws:states:::batch:submitJob.sync",
        "Parameters": {
            "JobDefinition": {"Ref": "BatchJobDefinition"},
            "JobName.$": f"States.Format('{flow_name}-{{}}', $.step_name)",
            "JobQueue": {"Ref": "BatchJobQueue"},
            "ContainerOverrides": {
                "Vcpus": vcpu,
                "Memory": memory_mb,
            },
            "Environment": [
                {"Name": "LOKKI_ARTIFACT_BUCKET", "Value": config.artifact_bucket},
                {"Name": "LOKKI_FLOW_NAME", "Value": flow_name},
                {"Name": "LOKKI_STEP_NAME", "Value.$": "$.step_name"},
                {"Name": "LOKKI_INPUT_URL", "Value.$": "$.input"},
            ],
        },
        "ResultPath": "$.input",
        "Next": None,
    }

    retry_config = getattr(step_node, "retry", None)
    if retry_config and retry_config.retries > 0:
        state["Retry"] = _build_retry_field(retry_config)

    return state


def _build_retry_field(retry_config: RetryConfig) -> list[dict[str, Any]]:
    """Build Step Functions Retry field from RetryConfig."""
    error_equals = [
        _exception_to_error_equals(exc_type) for exc_type in retry_config.exceptions
    ]

    return [
        {
            "ErrorEquals": error_equals,
            "IntervalSeconds": int(retry_config.delay),
            "MaxAttempts": retry_config.retries + 1,
            "BackoffRate": retry_config.backoff,
        }
    ]


def _lambda_arn(config: LokkiConfig, step_name: str, flow_name: str) -> str:
    """Construct Lambda ARN."""
    return (
        f"arn:aws:lambda:${{AWS::Region}}:${{AWS::AccountId}}:"
        f"function:{flow_name}-{step_name}"
    )
