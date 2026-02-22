"""Show command for displaying flow execution status."""

from __future__ import annotations

import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

from lokki._aws import get_sfn_client
from lokki._errors import ShowError

# Backward compatibility
boto3 = boto3


def show_executions(
    flow_name: str,
    state_machine_name: str | None = None,
    max_count: int = 10,
    run_id: str | None = None,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> list[dict[str, Any]]:
    """Show executions for a flow.

    Args:
        flow_name: Name of the flow
        state_machine_name: Optional state machine name
            (defaults to flow-name-state-machine)
        max_count: Maximum number of executions to show
        run_id: Specific run ID to show
        region: AWS region
        endpoint: Optional AWS endpoint (for LocalStack)

    Returns:
        List of execution info dicts

    Raises:
        ShowError: If operations fail
    """
    if state_machine_name is None:
        state_machine_name = f"{flow_name}-state-machine"

    client_kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint

    sf_client = get_sfn_client(endpoint or "", region)

    try:
        if run_id:
            response = sf_client.describe_execution(
                executionArn=f"arn:aws:states:{region}::execution:{state_machine_name}:{run_id}"
            )
            executions = [_format_execution(response)]
        else:
            response = sf_client.list_executions(
                stateMachineArn=f"arn:aws:states:{region}::stateMachine:{state_machine_name}",
                maxResults=max_count,
            )
            executions = [_format_execution(e) for e in response["executions"]]

        return executions

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = str(e)

        if error_code == "ExecutionNotFound":
            raise ShowError(f"Execution '{run_id}' not found") from e
        if error_code == "StateMachineNotFound":
            raise ShowError(
                f"State machine '{state_machine_name}' not found. "
                "Has the flow been deployed?"
            ) from e
        if error_code == "InvalidArn":
            if endpoint:
                raise ShowError(
                    "Step Functions is not available in LocalStack. "
                    "To test the full flow, deploy to real AWS."
                ) from e
            raise ShowError(f"Invalid state machine ARN: {e}") from e
        if "is not enabled" in error_msg.lower():
            if endpoint:
                raise ShowError(
                    "Step Functions is not enabled in LocalStack. "
                    "Check LocalStack SERVICES configuration."
                ) from e
            raise ShowError(f"AWS error: {e}") from e
        raise ShowError(f"AWS error: {e}") from e


def _format_execution(execution: dict[str, Any]) -> dict[str, Any]:
    """Format execution data for display."""
    start_date = execution.get("startDate")
    stop_date = execution.get("stopDate")

    duration = "-"
    if start_date and stop_date:
        delta = stop_date - start_date
        total_seconds = delta.total_seconds()
        if total_seconds >= 60:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            duration = f"{minutes}m {seconds}s"
        else:
            duration = f"{total_seconds:.1f}s"

    return {
        "run_id": execution.get(
            "name", execution.get("executionArn", "").split(":")[-1]
        ),
        "status": execution.get("status", "UNKNOWN"),
        "start_time": start_date.isoformat() if start_date else "-",
        "stop_time": stop_date.isoformat() if stop_date else "-",
        "duration": duration,
    }


def print_executions(executions: list[dict[str, Any]]) -> None:
    """Print executions in a formatted table."""
    if not executions:
        print("No executions found.")
        return

    print(f"{'Run ID':<30} {'Status':<12} {'Start Time':<25} {'Duration':<10}")
    print("-" * 80)

    for exec in executions:
        status_color = _get_status_color(exec["status"])
        print(
            f"{exec['run_id']:<30} "
            f"{status_color}{exec['status']:<12}\033[0m "
            f"{exec['start_time']:<25} "
            f"{exec['duration']:<10}"
        )


def _get_status_color(status: str) -> str:
    """Get ANSI color code for status."""
    if status == "SUCCEEDED":
        return "\033[92m"  # Green
    if status == "FAILED":
        return "\033[91m"  # Red
    if status == "RUNNING":
        return "\033[93m"  # Yellow
    if status == "ABORTED":
        return "\033[90m"  # Gray
    return ""


def show(
    flow_name: str,
    max_count: int = 10,
    run_id: str | None = None,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> None:
    """Show flow executions."""
    try:
        executions = show_executions(
            flow_name=flow_name,
            max_count=max_count,
            run_id=run_id,
            region=region,
            endpoint=endpoint,
        )
        print_executions(executions)
    except ShowError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
