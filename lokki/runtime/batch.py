"""AWS Batch runtime handler for lokki flows."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from lokki.config import load_config
from lokki.logging import LoggingConfig, get_logger
from lokki.runtime.event import FlowContext, LambdaEvent
from lokki.runtime.runtime import Runtime
from lokki.store import S3Store


def make_batch_handler(
    fn: Any,
    retry_config: Any = None,
) -> Any:
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
        step_name = fn.__name__

        logger.info(
            f"Batch job invoked: flow={flow_name}, step={step_name}",
            extra={
                "event": "batch_invoke",
                "flow": flow_name,
                "step": step_name,
            },
        )

        try:
            lambda_event = LambdaEvent.from_dict(event)
        except Exception:
            lambda_event = LambdaEvent(
                flow=FlowContext(run_id="unknown", params={}),
                input=event,
            )

        run_id = lambda_event.flow.run_id
        flow_params = lambda_event.flow.params
        input_data = lambda_event.input

        # If input_data is None (first step), use empty dict
        if input_data is None:
            input_data = {}

        store = S3Store()

        start_time = datetime.now()

        try:
            if isinstance(input_data, str):
                logger.info(
                    f"Reading input from {input_data}",
                    extra={"event": "input_read", "step": step_name},
                )
                input_data = store.read(input_data)
            elif isinstance(input_data, list) and all(
                isinstance(x, str) for x in input_data
            ):
                logger.info(
                    f"Reading {len(input_data)} inputs from S3",
                    extra={"event": "input_read", "step": step_name},
                )
                input_data = [store.read(url) for url in input_data]

            # Call step function using Runtime.call_step
            result = Runtime.call_step(fn, input_data, flow_params)

            output_url = store.write(flow_name, run_id, step_name, result)

            if isinstance(result, list):
                item_urls = []
                for i, item in enumerate(result):
                    item_url = store.write(flow_name, run_id, f"{step_name}/{i}", item)
                    item_urls.append(item_url)

                manifest_url = store.write_manifest(
                    flow_name, run_id, step_name, item_urls
                )

                logger.info(
                    f"Batch step completed: {step_name} in "
                    f"{(datetime.now() - start_time).total_seconds():.3f}s",
                    extra={
                        "event": "step_complete",
                        "step": step_name,
                        "duration": (datetime.now() - start_time).total_seconds(),
                        "status": "success",
                    },
                )
                return {"input": manifest_url, "flow": lambda_event.flow.to_dict()}

            logger.info(
                f"Batch step completed: {step_name} in "
                f"{(datetime.now() - start_time).total_seconds():.3f}s",
                extra={
                    "event": "step_complete",
                    "step": step_name,
                    "duration": (datetime.now() - start_time).total_seconds(),
                    "status": "success",
                },
            )
            return {"input": output_url, "flow": lambda_event.flow.to_dict()}

        except Exception as e:
            logger.error(
                f"Batch step failed: {step_name} after "
                f"{(datetime.now() - start_time).total_seconds():.3f}s: {e}",
                extra={
                    "event": "step_fail",
                    "step": step_name,
                    "duration": (datetime.now() - start_time).total_seconds(),
                    "status": "failed",
                },
            )
            raise

    return batch_handler
