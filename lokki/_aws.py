"""AWS client factory functions for lokki."""

import boto3
from botocore.client import BaseClient


def get_s3_client(endpoint: str = "") -> BaseClient:
    """Get S3 client with optional endpoint URL."""
    kwargs: dict[str, str] = {}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **kwargs)


def get_sfn_client(endpoint: str = "", region: str = "us-east-1") -> BaseClient:
    """Get Step Functions client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("stepfunctions", **kwargs)


def get_cf_client(endpoint: str = "", region: str = "us-east-1") -> BaseClient:
    """Get CloudFormation client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("cloudformation", **kwargs)


def get_logs_client(endpoint: str = "", region: str = "us-east-1") -> BaseClient:
    """Get CloudWatch Logs client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("logs", **kwargs)


def get_ecr_client(endpoint: str = "", region: str = "us-east-1") -> BaseClient:
    """Get ECR client with optional endpoint URL."""
    kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("ecr", **kwargs)


def get_sts_client(endpoint: str = "") -> BaseClient:
    """Get STS client with optional endpoint URL."""
    kwargs: dict[str, str] = {}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("sts", **kwargs)
