"""AWS client factory functions for lokki."""

import os
from typing import Any

import boto3


def get_s3_client() -> Any:
    """Get S3 client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **kwargs)


def get_sfn_client(region: str = "us-east-1") -> Any:
    """Get Step Functions client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("stepfunctions", **kwargs)


def get_cf_client(region: str = "us-east-1") -> Any:
    """Get CloudFormation client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("cloudformation", **kwargs)


def get_logs_client(region: str = "us-east-1") -> Any:
    """Get CloudWatch Logs client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("logs", **kwargs)


def get_ecr_client(region: str = "us-east-1") -> Any:
    """Get ECR client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("ecr", **kwargs)


def get_sts_client() -> Any:
    """Get STS client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("sts", **kwargs)


def get_batch_client(region: str = "us-east-1") -> Any:
    """Get AWS Batch client with endpoint from AWS_ENDPOINT_URL env var."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint := os.environ.get("AWS_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint
    return boto3.client("batch", **kwargs)
