"""AWS client factory functions for lokki."""

from typing import Any

import boto3


def get_s3_client(endpoint: str = "") -> Any:
    """Get S3 client with optional endpoint URL."""
    kwargs: dict[str, str] = {}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **kwargs)


def get_sfn_client(endpoint: str = "", region: str = "us-east-1") -> Any:
    """Get Step Functions client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("stepfunctions", **kwargs)


def get_cf_client(endpoint: str = "", region: str = "us-east-1") -> Any:
    """Get CloudFormation client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("cloudformation", **kwargs)


def get_logs_client(endpoint: str = "", region: str = "us-east-1") -> Any:
    """Get CloudWatch Logs client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("logs", **kwargs)


def get_ecr_client(endpoint: str = "", region: str = "us-east-1") -> Any:
    """Get ECR client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("ecr", **kwargs)


def get_sts_client(endpoint: str = "") -> Any:
    """Get STS client with optional endpoint URL."""
    kwargs: dict[str, str] = {}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("sts", **kwargs)
