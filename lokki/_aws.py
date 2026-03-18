"""AWS client factory functions for lokki."""

import os
from typing import Literal

import boto3
from botocore.client import BaseClient

AWS_SERVICE = Literal[
    "s3",
    "stepfunctions",
    "cloudformation",
    "logs",
    "ecr",
    "sts",
    "batch",
    "dynamodb",
]


def _get_aws_client(
    service: AWS_SERVICE,
    region: str = "us-east-1",
    endpoint: str | None = None,
) -> BaseClient:
    """Create an AWS client for the specified service.

    Args:
        service: AWS service name (e.g., "s3", "stepfunctions").
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured AWS client for the service.
    """
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint or (endpoint := os.environ.get("AWS_ENDPOINT_URL")):
        kwargs["endpoint_url"] = endpoint
    return boto3.client(service, **kwargs)


def get_s3_client(endpoint: str | None = None) -> BaseClient:
    """Get S3 client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured S3 client.
    """
    return _get_aws_client("s3", endpoint=endpoint)


def get_sfn_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get Step Functions client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured Step Functions client.
    """
    return _get_aws_client("stepfunctions", region=region, endpoint=endpoint)


def get_cf_client(region: str = "us-east-1", endpoint: str | None = None) -> BaseClient:
    """Get CloudFormation client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured CloudFormation client.
    """
    return _get_aws_client("cloudformation", region=region, endpoint=endpoint)


def get_logs_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get CloudWatch Logs client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured CloudWatch Logs client.
    """
    return _get_aws_client("logs", region=region, endpoint=endpoint)


def get_ecr_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get ECR client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured ECR client.
    """
    return _get_aws_client("ecr", region=region, endpoint=endpoint)


def get_sts_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get STS client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured STS client.
    """
    return _get_aws_client("sts", region=region, endpoint=endpoint)


def get_batch_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get AWS Batch client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured AWS Batch client.
    """
    return _get_aws_client("batch", region=region, endpoint=endpoint)


def get_dynamodb_client(
    region: str = "us-east-1", endpoint: str | None = None
) -> BaseClient:
    """Get DynamoDB client with endpoint from AWS_ENDPOINT_URL env var.

    Args:
        region: AWS region (default: "us-east-1").
        endpoint: Optional endpoint URL (overrides AWS_ENDPOINT_URL env var).

    Returns:
        botocore.client.BaseClient: Configured DynamoDB client.
    """
    return _get_aws_client("dynamodb", region=region, endpoint=endpoint)
