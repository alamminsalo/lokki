"""Logs command for fetching CloudWatch logs."""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from lokki._aws import get_logs_client
from lokki._errors import LogsError

# Backward compatibility
boto3 = boto3


def fetch_logs(
    flow_name: str,
    step_names: list[str],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    run_id: str | None = None,
    region: str = "us-east-1",
    endpoint: str | None = None,
    tail: bool = False,
) -> None:
    """Fetch CloudWatch logs for flow Lambda functions.

    Args:
        flow_name: Name of the flow
        step_names: List of step names in the flow
        start_time: Start time for logs (default: 1 hour ago)
        end_time: End time for logs (default: now)
        run_id: Specific run ID to filter logs
        region: AWS region
        endpoint: Optional AWS endpoint (for LocalStack)
        tail: Whether to tail logs in real-time
    """
    if start_time is None:
        start_time = datetime.now(UTC) - timedelta(hours=1)
    if end_time is None:
        end_time = datetime.now(UTC)

    client_kwargs: dict[str, str] = {"region_name": region}
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint

    logs_client = get_logs_client(endpoint or "", region)

    try:
        _fetch_and_print_logs(
            logs_client,
            flow_name,
            step_names,
            start_time,
            end_time,
            run_id,
            tail,
        )
    except LogsError:
        raise
    except ClientError as e:
        error_msg = str(e)
        if "is not enabled" in error_msg.lower():
            if endpoint:
                raise LogsError(
                    "CloudWatch Logs is not enabled in LocalStack. "
                    "Check LocalStack SERVICES configuration."
                ) from e
        raise LogsError(f"AWS error: {e}") from e


def _fetch_and_print_logs(
    logs_client: Any,
    flow_name: str,
    step_names: list[str],
    start_time: datetime,
    end_time: datetime,
    run_id: str | None,
    tail: bool,
) -> None:
    """Fetch and print logs for all step functions."""
    if tail:
        _tail_logs(logs_client, flow_name, step_names, run_id)
    else:
        _print_logs(logs_client, flow_name, step_names, start_time, end_time, run_id)


def _print_logs(
    logs_client: Any,
    flow_name: str,
    step_names: list[str],
    start_time: datetime,
    end_time: datetime,
    run_id: str | None,
) -> None:
    """Print logs for a time range."""
    all_events: list[dict[str, Any]] = []

    for step_name in step_names:
        log_group = f"/aws/lambda/{flow_name}-{step_name}"
        events = _fetch_log_events(logs_client, log_group, start_time, end_time, run_id)
        all_events.extend(events)

    if not all_events:
        print("No log events found.")
        return

    all_events.sort(key=lambda e: (e["timestamp"], e["logStreamName"]))

    for event in all_events:
        timestamp = datetime.fromtimestamp(event["timestamp"] / 1000, tz=UTC)
        step = event["logStreamName"].replace(f"{flow_name}-", "")
        message = event["message"].strip()
        print(f"{timestamp.isoformat()} [{step}] {message}")


def _fetch_log_events(
    logs_client: Any,
    log_group: str,
    start_time: datetime,
    end_time: datetime,
    run_id: str | None,
) -> list[dict[str, Any]]:
    """Fetch log events from a log group."""
    try:
        filter_pattern = f'"{run_id}"' if run_id else None

        kwargs: dict[str, Any] = {
            "logGroupName": log_group,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": 10000,
        }
        if filter_pattern:
            kwargs["filterPattern"] = filter_pattern

        response = logs_client.filter_log_events(**kwargs)
        events: list[dict[str, Any]] = response.get("events", [])
        return events

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise


def _tail_logs(
    logs_client: Any,
    flow_name: str,
    step_names: list[str],
    run_id: str | None,
) -> None:
    """Tail logs in real-time."""
    print("Tailing logs... (Ctrl+C to stop)")

    last_timestamps: dict[str, int] = {}

    while True:
        for step_name in step_names:
            log_group = f"/aws/lambda/{flow_name}-{step_name}"
            events = _tail_log_events(logs_client, log_group, run_id, last_timestamps)

            for event in events:
                timestamp = datetime.fromtimestamp(event["timestamp"] / 1000, tz=UTC)
                message = event["message"].strip()
                print(f"{timestamp.isoformat()} [{step_name}] {message}")

                last_timestamps[log_group] = event["timestamp"]

        time.sleep(2)


def _tail_log_events(
    logs_client: Any,
    log_group: str,
    run_id: str | None,
    last_timestamps: dict[str, int],
) -> list[dict[str, Any]]:
    """Fetch new log events since last check."""
    try:
        kwargs: dict[str, Any] = {
            "logGroupName": log_group,
            "limit": 100,
            "startTime": int(
                (datetime.now(UTC) - timedelta(seconds=5)).timestamp() * 1000
            ),
        }
        if run_id:
            kwargs["filterPattern"] = f'"{run_id}"'

        response = logs_client.filter_log_events(**kwargs)
        events = response.get("events", [])
        result: list[dict[str, Any]] = events

        if last_timestamps:
            last_ts = last_timestamps.get(log_group, 0)
            result = [e for e in result if e["timestamp"] > last_ts]

        return result

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise


def logs(
    flow_name: str,
    step_names: list[str],
    start_time: str | None = None,
    end_time: str | None = None,
    run_id: str | None = None,
    region: str = "us-east-1",
    endpoint: str | None = None,
    tail: bool = False,
) -> None:
    """Fetch CloudWatch logs for a flow."""
    try:
        start_dt = _parse_datetime(start_time) if start_time else None
        end_dt = _parse_datetime(end_time) if end_time else None

        fetch_logs(
            flow_name=flow_name,
            step_names=step_names,
            start_time=start_dt,
            end_time=end_dt,
            run_id=run_id,
            region=region,
            endpoint=endpoint,
            tail=tail,
        )
    except LogsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped tailing logs.")
        sys.exit(0)


def _parse_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt
    except ValueError as e:
        msg = (
            f"Invalid datetime format: {dt_str}. "
            "Use ISO 8601 format (e.g., 2024-01-15T10:00:00Z)"
        )
        raise LogsError(msg) from e
