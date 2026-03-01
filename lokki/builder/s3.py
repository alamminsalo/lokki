"""S3 utilities for builder (Lambda package uploads)."""

from __future__ import annotations

import os


def upload_lambda_zip(flow_name: str, zip_data: bytes, bucket: str = "") -> str:
    """Upload a Lambda function ZIP package to S3.

    Args:
        flow_name: The flow name
        zip_data: The ZIP package bytes
        bucket: The S3 bucket (falls back to LOKKI_ARTIFACT_BUCKET env var)

    Returns:
        The S3 URI of the uploaded package
    """
    from lokki._aws import get_s3_client

    if not bucket:
        bucket = os.environ.get("LOKKI_ARTIFACT_BUCKET", "")
    if not bucket:
        raise ValueError(
            "LOKKI_ARTIFACT_BUCKET environment variable not set. "
            "This should be set in the deployment environment."
        )

    key = f"{flow_name}/artifacts/lambdas/function.zip"
    client = get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=zip_data)
    return f"s3://{bucket}/{key}"
