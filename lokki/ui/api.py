"""API functions for UI console."""

from __future__ import annotations

from typing import Any

from lokki._aws import get_dynamodb_client, get_logs_client, get_sfn_client


def list_flows(
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> list[str]:
    """List all deployed lokki flows from DynamoDB."""
    dynamodb_client = get_dynamodb_client(region, endpoint)

    try:
        response = dynamodb_client.scan(TableName="lokki-flows")
        flows = [item["flow_name"]["S"] for item in response.get("Items", [])]
        return sorted(flows)
    except Exception:
        # Fallback to Step Functions if DynamoDB table doesn't exist
        return _list_flows_from_sfn(region, endpoint)


def _list_flows_from_sfn(
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> list[str]:
    """Fallback: List flows from Step Functions API."""
    sfn_client = get_sfn_client(region, endpoint)

    response = sfn_client.list_state_machines(maxResults=100)

    flows = []
    for sm in response.get("stateMachines", []):
        if _is_lokki_flow(sm):
            flows.append(sm.get("name", ""))

    return sorted(flows)


def _is_lokki_flow(state_machine: dict[str, Any]) -> bool:
    """Check if state machine is a lokki flow (by tag or prefix)."""
    tags = state_machine.get("tags", {}) or {}
    if tags.get("lokki:managed") == "true":
        return True

    name = state_machine.get("name", "")
    if name.startswith("lokki-"):
        return True

    # For local development, accept all flows
    # In production with real AWS, tags would be required
    return True


def list_runs(
    flow_name: str,
    region: str = "us-east-1",
    endpoint: str | None = None,
    max_count: int = 10,
) -> list[dict[str, Any]]:
    """List runs for a flow."""
    from lokki.cli.show import show_executions

    return show_executions(
        flow_name=flow_name,
        region=region,
        endpoint=endpoint,
        max_count=max_count,
    )


def get_logs(
    flow_name: str,
    run_id: str,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> list[str]:
    """Get logs for a specific run."""
    logs_client = get_logs_client(region, endpoint)

    step_names = _get_step_names(flow_name, region, endpoint)

    all_logs: list[str] = []

    for step_name in step_names:
        log_group = f"/aws/lambda/{flow_name}-{step_name}"

        try:
            response = logs_client.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=run_id,
                limit=1,
            )

            log_streams = response.get("logStreams", [])
            if not log_streams:
                continue

            log_stream_name = log_streams[0].get("logStreamName", "")

            response = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream_name,
                startFromHeadTime=True,
            )

            for event in response.get("events", []):
                timestamp = event.get("timestamp", 0)
                message = event.get("message", "")

                from datetime import datetime

                dt = datetime.fromtimestamp(timestamp / 1000)
                ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                all_logs.append(f"[{ts_str}] [{step_name}] {message}")

        except Exception:
            continue

    return all_logs


def _get_step_names(
    flow_name: str,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> list[str]:
    """Get step names for a flow by describing the state machine."""
    sfn_client = get_sfn_client(region, endpoint)

    try:
        response = sfn_client.describe_state_machine(
            stateMachineArn=f"arn:aws:states:{region}:000000000000:stateMachine:{flow_name}"
        )

        import json

        definition = json.loads(response.get("definitionString", "{}"))

        step_names: set[str] = set()
        _collect_step_names(definition, step_names)

        return sorted(step_names)

    except Exception:
        return []


def _collect_step_names(definition: Any, step_names: set[str]) -> None:
    """Recursively collect step names from state machine definition."""
    if isinstance(definition, dict):
        if definition.get("Type") == "Task":
            resource = definition.get("Resource", "")
            if resource.startswith("arn:aws:lambda"):
                step_name = resource.split(":")[-1]
                if flow_name := step_name.rsplit("-", 1)[0]:
                    step_names.add(step_name.replace(flow_name + "-", "", 1))

        for value in definition.values():
            _collect_step_names(value, step_names)

    elif isinstance(definition, list):
        for item in definition:
            _collect_step_names(item, step_names)
