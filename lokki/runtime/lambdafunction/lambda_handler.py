"""Lambda runtime handler for lokki flows."""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lokki.logging import LoggingConfig, get_logger
from lokki.runtime.event import FlowContext, LambdaEvent
from lokki.runtime.runtime import Runtime
from lokki.store import LocalStore, S3Store

if TYPE_CHECKING:
    from lokki.decorators import RetryConfig


def _get_store() -> S3Store | LocalStore:
    """Get the store based on LOKKI_STORE_TYPE environment variable."""
    store_type = os.environ.get("LOKKI_STORE_TYPE", "s3").lower()
    if store_type == "local":
        store_path = os.environ.get("LOKKI_STORE_PATH", None)
        return LocalStore(store_path)
    return S3Store()


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
        cache_enabled = lambda_event.flow.cache_enabled
        flow_params = lambda_event.flow.params
        input_data = lambda_event.input

        # If run_id is not provided, use a unique placeholder for this execution
        # This ensures S3 writes work, but cache won't match across runs
        if run_id is None:
            import uuid

            run_id = f"nocache-{uuid.uuid4().hex[:8]}"

        is_first_step = input_data is None
        if is_first_step:
            input_data = {}

        store = _get_store()

        start_time = datetime.now()

        # Compute input hash for cache validation
        from lokki.store.utils import _hash_input

        input_hash = _hash_input(input_data)

        # Cache: check if enabled and output exists with matching input hash
        stored_input_hash = None
        if cache_enabled and store.exists(flow_name, run_id, step_name):
            stored_input_hash = store.get_input_hash(flow_name, run_id, step_name)
            if stored_input_hash == input_hash:
                logger.info(
                    f"Cache hit for step '{step_name}', returning cached result",
                    extra={"event": "cache_skip", "step": step_name},
                )
                cached_result = store.read_cached(flow_name, run_id, step_name)
                return {
                    "input": cached_result,
                    "flow": lambda_event.flow.to_dict(),
                }

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

            # Call step function using Runtime.call_step
            if is_first_step:
                result = Runtime.call_step(fn, None, flow_params)
            else:
                result = Runtime.call_step(fn, input_data, flow_params)

            # Handle None result (side-effect only step)
            if result is None:
                logger.info(
                    f"Step completed: {step_name} in "
                    f"{(datetime.now() - start_time).total_seconds():.3f}s (no output)",
                    extra={
                        "event": "step_complete",
                        "step": step_name,
                        "duration": (datetime.now() - start_time).total_seconds(),
                        "status": "success",
                    },
                )
                return {"input": None, "flow": lambda_event.flow.to_dict()}

            # Write output to S3 (always with input_hash for cache validation)
            output_url = store.write(
                flow_name, run_id, step_name, result, input_hash=input_hash
            )

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
