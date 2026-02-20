"""S3 read/write utilities with gzip pickle serialization."""

from __future__ import annotations

import gzip
import json
import pickle
from typing import Any

import boto3

_endpoint: str = ""


def set_endpoint(endpoint: str) -> None:
    """Set the S3 endpoint URL for all subsequent operations."""
    global _endpoint
    _endpoint = endpoint


def _get_s3_client():
    """Get S3 client with optional endpoint URL."""
    kwargs = {}
    if _endpoint:
        kwargs["endpoint_url"] = _endpoint
    return boto3.client("s3", **kwargs)


def _parse_url(url: str) -> tuple[str, str]:
    """Parse an s3:// URL into bucket and key components."""
    if not url.startswith("s3://"):
        raise ValueError(f"Invalid S3 URL: {url}. Must start with 's3://'")
    parts = url[5:].split("/", 1)
    bucket = parts[0]
    if not bucket:
        raise ValueError(f"Invalid S3 URL: {url}. Missing bucket")
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def write(bucket: str, key: str, obj: Any) -> str:
    """Serialize obj, upload to s3://bucket/key, return the S3 URL."""
    data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
    _get_s3_client().put_object(Bucket=bucket, Key=key, Body=data)
    return f"s3://{bucket}/{key}"


def read(url: str) -> Any:
    """Download from S3 URL and deserialize."""
    bucket, key = _parse_url(url)
    data = _get_s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    return pickle.loads(gzip.decompress(data))


def write_manifest(bucket: str, key: str, manifest: list[dict[str, Any]]) -> None:
    """Write map manifest JSON to S3."""
    _get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest),
        ContentType="application/json",
    )
