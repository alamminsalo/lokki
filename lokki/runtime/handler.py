"""Lambda runtime handler for lokki flows."""

from __future__ import annotations

import inspect
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lokki.logging import LoggingConfig, get_logger
from lokki.runtime.event import FlowContext, LambdaEvent
from lokki.store import S3Store

if TYPE_CHECKING:
    from lokki.decorators import RetryConfig


def make_handler(
    fn: Any,
    retry_config: RetryConfig | None = None,
) -> Any:
    """Create a Lambda handler for a step function.

    Note: Retry logic for deployed flows is handled by AWS Step Functions,
    not by this handler. The retry_config is accepted for consistency.

    Args:
        fn: The step function to wrap
        retry_config: Retry config (unused in Lambda - Step Functions handles retries)

    Returns:
        A lambda_handler function compatible with AWS Lambda
    """
    logger = get_logger("lokki.runtime", LoggingConfig())

    def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        assert "LOKKI_FLOW_NAME" in os.environ

        flow_name = os.environ.get("LOKKI_FLOW_NAME", "unknown")
        step_name = fn.__name__

        logger.info(
            f"Lambda invoked: flow={flow_name}, step={step_name}",
            extra={
                "event": "lambda_invoke",
                "flow": flow_name,
                "step": step_name,
            },
        )

        # Parse event - try new format first, fall back to old format
        lambda_event = _parse_event(event)

        run_id = lambda_event.flow.run_id
        flow_params = lambda_event.flow.params
        input_data = lambda_event.input

        # If input_data is None (first step with no prior output), use empty marker
        is_first_step = input_data is None
        if is_first_step:
            input_data = {}

        store = S3Store()

        start_time = datetime.now()

        try:
            # Read input from S3 if it's a URL string or list of URLs
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

            # Call step function
            # First step: no input from prior step, pass flow_params as kwargs
            # Subsequent steps: pass input_data and flow_params as kwargs
            if is_first_step:
                result = fn(**flow_params) if flow_params else fn()
            elif flow_params:
                result = fn(input_data, **flow_params)
            else:
                result = fn(input_data)

            # Write output to S3
            output_url = store.write(flow_name, run_id, step_name, result)

            # Handle map results (list) - write manifest as list of URLs
            if isinstance(result, list):
                item_urls = []
                for i, item in enumerate(result):
                    item_url = store.write(flow_name, run_id, f"{step_name}/{i}", item)
                    item_urls.append(item_url)

                manifest_url = store.write_manifest(
                    flow_name, run_id, step_name, item_urls
                )

                logger.info(
                    f"Step completed: {step_name} in "
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
                f"Step completed: {step_name} in "
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
                f"Step failed: {step_name} after "
                f"{(datetime.now() - start_time).total_seconds():.3f}s: {e}",
                extra={
                    "event": "step_error",
                    "step": step_name,
                    "duration": (datetime.now() - start_time).total_seconds(),
                    "error": str(e),
                },
            )
            raise

    return lambda_handler


def _parse_event(event: dict[str, Any]) -> LambdaEvent:
    """Parse event into LambdaEvent dataclass.

    Supports:
    - {"flow": {...}, "input": ...} - new format
    - {"flow": [...]} - list from Map aggregation (extract flow from first item)
    """
    # Handle list input (from Map aggregation)
    if isinstance(event, list):
        # Extract flow from first item to preserve it
        run_id = "unknown"
        flow_params = {}
        input_items = event
        if event and isinstance(event[0], dict):
            first = event[0]
            if "flow" in first and isinstance(first["flow"], dict):
                flow = first["flow"]
                run_id = flow.get("run_id", "unknown")
                flow_params = flow.get("params", {})
        return LambdaEvent(
            flow=FlowContext(run_id=run_id, params=flow_params),
            input=input_items,
        )

    # Handle dict input - new format {"flow": {...}, "input": ...}
    if "flow" in event and isinstance(event["flow"], dict):
        flow_data = event["flow"]
        return LambdaEvent(
            flow=FlowContext.from_dict(flow_data),
            input=event.get("input"),
        )

    # Fallback - create default
    return LambdaEvent(
        flow=FlowContext(run_id="unknown", params={}),
        input=event,
    )
