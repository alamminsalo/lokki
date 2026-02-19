"""Lambda runtime handler for lokki flows."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import boto3

from lokki import s3
from lokki.config import load_config


def make_handler(
    fn: Callable[..., Any],
) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    """Create a Lambda handler for a step function.

    Args:
        fn: The step function to wrap

    Returns:
        A lambda_handler function compatible with AWS Lambda
    """

    def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        cfg = load_config()
        flow_name = (
            cfg.flow_name
            if hasattr(cfg, "flow_name")
            else os.environ.get("LOKKI_FLOW_NAME", "unknown")
        )
        bucket = cfg.artifact_bucket or os.environ.get("LOKKI_S3_BUCKET", "")
        run_id = event.get("run_id", "unknown")
        step_name = fn.__name__

        result_url: str | None = None
        result_urls: list[str] | None = None
        map_manifest_key: str | None = None

        if "result_url" in event:
            result_url = event["result_url"]
        elif "result_urls" in event:
            result_urls = event["result_urls"]

        if result_url:
            input_data = s3.read(result_url)
            result = fn(input_data)
        elif result_urls:
            inputs = [s3.read(url) for url in result_urls]
            result = fn(inputs)
        else:
            import inspect

            sig = inspect.signature(fn)
            kwargs = {k: event[k] for k in event if k in sig.parameters}
            result = fn(**kwargs)

        key = f"lokki/{flow_name}/{run_id}/{step_name}/output.pkl.gz"
        output_url = s3.write(bucket, key, result)

        if isinstance(result, list):
            item_urls = []
            for i, item in enumerate(result):
                item_key = f"lokki/{flow_name}/{run_id}/{step_name}/{i}/output.pkl.gz"
                item_url = s3.write(bucket, item_key, item)
                item_urls.append(item_url)

            manifest = [
                {"item_url": item_url, "index": i}
                for i, item_url in enumerate(item_urls)
            ]
            map_manifest_key = (
                f"lokki/{flow_name}/{run_id}/{step_name}/map_manifest.json"
            )

            boto3.client("s3").put_object(
                Bucket=bucket,
                Key=map_manifest_key,
                Body=json.dumps(manifest),
                ContentType="application/json",
            )
            return {"map_manifest_key": map_manifest_key, "run_id": run_id}

        return {"result_url": output_url, "run_id": run_id}

    return lambda_handler
