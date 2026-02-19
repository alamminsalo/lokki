"""Lambda runtime handler for lokki flows."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

import boto3

from lokki import s3
from lokki.config import load_config
from lokki.logging import LoggingConfig, get_logger


def make_handler(
    fn: Callable[..., Any],
) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    """Create a Lambda handler for a step function.

    Args:
        fn: The step function to wrap

    Returns:
        A lambda_handler function compatible with AWS Lambda
    """
    logger = get_logger("lokki.runtime", LoggingConfig())

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

        logger.info(
            f"Lambda invoked: flow={flow_name}, step={step_name}, run_id={run_id}",
            extra={
                "event": "lambda_invoke",
                "flow": flow_name,
                "step": step_name,
                "run_id": run_id,
            },
        )

        start_time = datetime.now()
        result_url: str | None = None
        result_urls: list[str] | None = None
        map_manifest_key: str | None = None

        try:
            if "result_url" in event:
                result_url = event["result_url"]
                logger.info(
                    f"Reading input from {result_url}",
                    extra={"event": "input_read", "step": step_name},
                )
                input_data = s3.read(result_url)
                result = fn(input_data)
            elif "result_urls" in event:
                result_urls = event["result_urls"]
                logger.info(
                    f"Reading {len(result_urls)} inputs",
                    extra={
                        "event": "input_read",
                        "step": step_name,
                        "count": len(result_urls),
                    },
                )
                inputs = [s3.read(url) for url in result_urls]
                result = fn(inputs)
            else:
                import inspect

                sig = inspect.signature(fn)
                kwargs = {k: event[k] for k in event if k in sig.parameters}
                logger.info(
                    "No upstream input, using event kwargs",
                    extra={"event": "input_read", "step": step_name},
                )
                result = fn(**kwargs)

            key = f"lokki/{flow_name}/{run_id}/{step_name}/output.pkl.gz"
            output_url = s3.write(bucket, key, result)

            if isinstance(result, list):
                item_urls = []
                for i, item in enumerate(result):
                    item_key = (
                        f"lokki/{flow_name}/{run_id}/{step_name}/{i}/output.pkl.gz"
                    )
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
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"Step completed: {step_name} in {duration:.3f}s",
                    extra={
                        "event": "step_complete",
                        "step": step_name,
                        "duration": duration,
                        "status": "success",
                    },
                )
                return {"map_manifest_key": map_manifest_key, "run_id": run_id}

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Step completed: {step_name} in {duration:.3f}s",
                extra={
                    "event": "step_complete",
                    "step": step_name,
                    "duration": duration,
                    "status": "success",
                },
            )
            return {"result_url": output_url, "run_id": run_id}

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"Step failed: {step_name} after {duration:.3f}s: {e}",
                extra={
                    "event": "step_fail",
                    "step": step_name,
                    "duration": duration,
                    "status": "failed",
                },
            )
            raise

    return lambda_handler
