"""Invoke command for starting Step Functions executions."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from botocore.exceptions import ClientError

from lokki._aws import get_sfn_client
from lokki._errors import InvokeError

logger = logging.getLogger(__name__)


def invoke(
    flow_name: str,
    input_data: dict[str, Any],
    region: str = "us-east-1",
    endpoint: str | None = None,
    wait: bool = True,
) -> dict[str, Any]:
    """Invoke a Step Functions execution for a flow.

    Args:
        flow_name: Name of the flow
        input_data: Input data to pass to the flow
        region: AWS region
        endpoint: Optional AWS endpoint (for LocalStack)
        wait: Whether to wait for execution to complete

    Returns:
        Dict with execution_arn, status, and output/error if completed

    Raises:
        InvokeError: If invocation fails
    """
    state_machine_name = flow_name

    sfn_client = get_sfn_client(region)

    state_machine_arn = (
        f"arn:aws:states:{region}:000000000000:stateMachine:{state_machine_name}"
    )

    try:
        response = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(input_data)
            if isinstance(input_data, dict)
            else input_data,
        )
        execution_arn = response["executionArn"]
        print(f"Started execution: {execution_arn}")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = str(e)

        if error_code == "ExecutionNotFound":
            raise InvokeError(f"State machine '{state_machine_name}' not found") from e
        if error_code == "StateMachineNotFound":
            raise InvokeError(
                f"State machine '{state_machine_name}' not found. "
                "Has the flow been deployed?"
            ) from e
        if "is not enabled" in error_msg.lower():
            if endpoint:
                raise InvokeError(
                    "Step Functions is not enabled in LocalStack. "
                    "Check LocalStack SERVICES configuration."
                ) from e
            raise InvokeError(f"AWS error: {e}") from e
        raise InvokeError(f"Failed to start execution: {e}") from e

    if not wait:
        return {
            "execution_arn": execution_arn,
            "status": "RUNNING",
        }

    while True:
        try:
            desc_response = sfn_client.describe_execution(executionArn=execution_arn)
            status = desc_response["status"]

            print(f"Status: {status}")

            if status == "SUCCEEDED":
                output = desc_response.get("output")
                if output:
                    try:
                        parsed_output = json.loads(output)
                        print(f"Output: {parsed_output}")
                    except json.JSONDecodeError:
                        print(f"Output: {output}")
                return {
                    "execution_arn": execution_arn,
                    "status": status,
                    "output": output,
                }

            elif status in ("FAILED", "TIMED_OUT", "ABORTED"):
                failure_output = desc_response.get("output")
                if failure_output:
                    try:
                        parsed = json.loads(failure_output)
                        print(f"Error output: {parsed}")
                    except json.JSONDecodeError:
                        print(f"Error output: {failure_output}")
                    cause = None
                else:
                    cause = desc_response.get("cause", "Unknown error")
                    print(f"Cause: {cause}")

                return {
                    "execution_arn": execution_arn,
                    "status": status,
                    "error": failure_output or cause or "Unknown error",
                }

        except ClientError as e:
            raise InvokeError(f"Failed to describe execution: {e}") from e

        time.sleep(2)
