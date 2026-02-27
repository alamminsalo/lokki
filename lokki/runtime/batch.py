"""AWS Batch runtime handler for lokki flows."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lokki.config import load_config
from lokki.logging import LoggingConfig, get_logger
from lokki.store import S3Store

if TYPE_CHECKING:
    from lokki.decorators import RetryConfig


def make_batch_handler(
    fn: Callable[..., Any],
    retry_config: RetryConfig | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Create a handler for AWS Batch jobs.

    Args:
        fn: The step function to wrap
        retry_config: Retry config (unused in Batch - handled by Batch job)

    Returns:
        A handler function compatible with AWS Batch container
    """
    logger = get_logger("lokki.runtime.batch", LoggingConfig())

    def batch_handler(event: dict[str, Any]) -> dict[str, Any]:
        cfg = load_config()
        flow_name = cfg.flow_name or os.environ.get("LOKKI_FLOW_NAME", "unknown")
        run_id = event.get("run_id", "unknown")
        step_name = fn.__name__

        store = S3Store()

        logger.info(
            f"Batch job invoked: flow={flow_name}, step={step_name}, run_id={run_id}",
            extra={
                "event": "batch_invoke",
                "flow": flow_name,
                "step": step_name,
                "run_id": run_id,
            },
        )

        start_time = datetime.now()

        try:
            if "input_url" in event:
                input_url = event["input_url"]
                logger.info(
                    f"Reading input from {input_url}",
                    extra={"event": "input_read", "step": step_name},
                )
                input_data = store.read(input_url)
                result = fn(input_data)
            elif "result_url" in event:
                result_url = event["result_url"]
                logger.info(
                    f"Reading input from {result_url}",
                    extra={"event": "input_read", "step": step_name},
                )
                input_data = store.read(result_url)
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
                inputs = [store.read(url) for url in result_urls]
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

            output_url = store.write(flow_name, run_id, step_name, result)

            if isinstance(result, list):
                item_urls = []
                for i, item in enumerate(result):
                    item_url = store.write(flow_name, run_id, f"{step_name}/{i}", item)
                    item_urls.append(item_url)

                manifest = [
                    {"item_url": item_url, "index": i}
                    for i, item_url in enumerate(item_urls)
                ]

                map_manifest_key = store.write_manifest(
                    flow_name, run_id, step_name, manifest
                )
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"Batch step completed: {step_name} in {duration:.3f}s",
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
                f"Batch step completed: {step_name} in {duration:.3f}s",
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
                f"Batch step failed: {step_name} after {duration:.3f}s: {e}",
                extra={
                    "event": "step_fail",
                    "step": step_name,
                    "duration": duration,
                    "status": "failed",
                },
            )
            raise

    return batch_handler
