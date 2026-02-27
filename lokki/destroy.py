"""Destroy command for deleting CloudFormation stacks."""

from __future__ import annotations

import sys

from botocore.exceptions import ClientError

from lokki._aws import get_cf_client
from lokki._errors import DestroyError


def destroy_stack(
    stack_name: str,
    region: str = "us-east-1",
    endpoint: str | None = None,
    confirm: bool = False,
) -> None:
    """Destroy a CloudFormation stack.

    Args:
        stack_name: Name of the stack to destroy
        region: AWS region
        endpoint: Optional AWS endpoint (for LocalStack)
        confirm: Skip confirmation prompt

    Raises:
        DestroyError: If operations fail
    """
    cf_client = get_cf_client(region)

    if not confirm:
        response = input(
            f"This will delete the CloudFormation stack '{stack_name}' and "
            f"all associated resources.\n"
            f"Are you sure you want to continue? (y/N): "
        )
        if response.lower() not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    try:
        cf_client.describe_stacks(StackName=stack_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationError":
            raise DestroyError(f"Stack '{stack_name}' does not exist") from e
        raise

    print(f"Deleting stack '{stack_name}'...")

    try:
        cf_client.delete_stack(StackName=stack_name)
    except ClientError as e:
        raise DestroyError(f"Failed to delete stack: {e}") from e

    try:
        waiter = cf_client.get_waiter("stack_delete_complete")
        waiter.wait(StackName=stack_name)
        print(f"Stack '{stack_name}' has been deleted successfully.")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("WaiterFailure", "WaiterMaxAttemptsExceeded"):
            msg = (
                "Stack deletion failed or timed out. "
                "Check the stack status in the AWS console."
            )
            raise DestroyError(msg) from e
        raise


def destroy(
    stack_name: str,
    region: str = "us-east-1",
    endpoint: str | None = None,
    confirm: bool = False,
) -> None:
    """Destroy a flow's CloudFormation stack."""
    try:
        destroy_stack(
            stack_name=stack_name,
            region=region,
            endpoint=endpoint,
            confirm=confirm,
        )
    except DestroyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
