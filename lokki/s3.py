"""S3 read/write utilities with gzip pickle serialization."""

from __future__ import annotations

import gzip
import pickle
from typing import Any

import boto3


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
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=data)
    return f"s3://{bucket}/{key}"


def read(url: str) -> Any:
    """Download from S3 URL and deserialize."""
    bucket, key = _parse_url(url)
    data = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return pickle.loads(gzip.decompress(data))
