"""Logging utilities for lokki."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "LogFormat",
    "LoggingConfig",
    "HumanFormatter",
    "JsonFormatter",
    "StepLogger",
    "MapProgressLogger",
    "get_logger",
    "get_logging_config",
    "generate_correlation_id",
]


class LogFormat(Enum):
    HUMAN = "human"
    JSON = "json"


@dataclass(slots=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "human"
    progress_interval: int = 10
    show_timestamps: bool = True
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    flow_name: str = ""
    run_id: str = ""

    def __post_init__(self) -> None:
        valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if self.level.upper() not in valid_levels:
            raise ValueError(f"level must be one of {valid_levels}, got '{self.level}'")
        valid_formats = ("human", "json")
        if self.format not in valid_formats:
            raise ValueError(
                f"format must be one of {valid_formats}, got '{self.format}'"
            )
        if self.progress_interval < 1:
            raise ValueError(
                f"progress_interval must be at least 1, got {self.progress_interval}"
            )


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter."""

    def __init__(self, config: LoggingConfig) -> None:
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        timestamp = ""
        if self.config.show_timestamps:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            timestamp = f"{timestamp} - "

        level = record.levelname
        message = record.getMessage()

        return f"[{level}] {timestamp}{message}"


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for flow execution."""
    return str(uuid.uuid4())


class JsonFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def __init__(self, config: LoggingConfig) -> None:
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "level": record.levelname,
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
            "correlation_id": self.config.correlation_id,
            "flow_name": self.config.flow_name,
            "run_id": self.config.run_id,
        }

        # Add step_name (and keep step for backward compatibility)
        step_name = getattr(record, "step", None)
        if step_name:
            data["step"] = step_name
            data["step_name"] = step_name

        for key in (
            "duration",
            "status",
            "total",
            "completed",
            "failed",
            "duration_ms",
        ):
            val = getattr(record, key, None)
            if val is not None:
                data[key] = val

        return json.dumps(data)


def get_logger(name: str, config: LoggingConfig) -> logging.Logger:
    """Create a configured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.level, logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(config)
        if config.format == LogFormat.JSON.value
        else HumanFormatter(config)
    )
    logger.addHandler(handler)
    logger.propagate = False

    return logger


class StepLogger:
    """Logger for step lifecycle events."""

    def __init__(
        self,
        step_name: str,
        logger: logging.Logger,
        correlation_id: str | None = None,
        flow_name: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.step_name = step_name
        self.logger = logger
        self.start_time: datetime | None = None
        self.correlation_id = correlation_id
        self.flow_name = flow_name
        self.run_id = run_id

    def _get_base_extra(self, event: str) -> dict[str, Any]:
        """Get base extra fields for log records."""
        extra: dict[str, Any] = {
            "event": event,
            "step": self.step_name,
        }
        if self.correlation_id:
            extra["correlation_id"] = self.correlation_id
        if self.flow_name:
            extra["flow_name"] = self.flow_name
        if self.run_id:
            extra["run_id"] = self.run_id
        return extra

    def start(self) -> None:
        """Log step start."""
        self.start_time = datetime.now()
        extra = self._get_base_extra("step_start")
        self.logger.info(f"Step '{self.step_name}' started", extra=extra)

    def complete(
        self,
        duration: float,
        input_size: int | None = None,
        output_size: int | None = None,
    ) -> None:
        """Log step completion."""
        extra = self._get_base_extra("step_complete")
        extra["duration"] = duration
        extra["status"] = "success"
        if input_size is not None:
            extra["input_size"] = input_size
        if output_size is not None:
            extra["output_size"] = output_size
        self.logger.info(
            f"Step '{self.step_name}' completed in {duration:.3f}s (status=success)",
            extra=extra,
        )

    def fail(self, duration: float, error: Exception) -> None:
        """Log step failure."""
        extra = self._get_base_extra("step_fail")
        extra["duration"] = duration
        extra["status"] = "failed"
        extra["exception_type"] = type(error).__name__
        extra["exception_message"] = str(error)
        self.logger.error(
            f"Step '{self.step_name}' failed after {duration:.3f}s: {error}",
            extra=extra,
        )

    def retry(
        self, attempt: int, max_attempts: int, error: Exception, delay: float
    ) -> None:
        """Log retry attempt."""
        extra = self._get_base_extra("step_retry")
        extra["retry_attempt"] = attempt
        extra["max_attempts"] = max_attempts
        extra["exception_type"] = type(error).__name__
        extra["exception_message"] = str(error)
        extra["retry_delay"] = delay
        self.logger.warning(
            "Step '%s' retry %d/%d after %.2fs: %s",
            self.step_name,
            attempt,
            max_attempts,
            delay,
            error,
            extra={**extra, "error": str(error)},
        )


class MapProgressLogger:
    """Logger for map task progress."""

    def __init__(
        self,
        step_name: str,
        total_items: int,
        logger: logging.Logger,
        config: LoggingConfig,
    ) -> None:
        self.step_name = step_name
        self.total_items = total_items
        self.logger = logger
        self.config = config
        self.completed = 0
        self.failed = 0
        self._last_pct = -1
        self.start_time: datetime | None = None
        self._item_times: list[float] = []
        self._last_item_time: datetime | None = None

    def _get_base_extra(self, event: str) -> dict[str, Any]:
        """Get base extra fields for log records."""
        extra: dict[str, Any] = {
            "event": event,
            "step": self.step_name,
        }
        if self.config.correlation_id:
            extra["correlation_id"] = self.config.correlation_id
        if self.config.flow_name:
            extra["flow_name"] = self.config.flow_name
        if self.config.run_id:
            extra["run_id"] = self.config.run_id
        return extra

    def start(self) -> None:
        """Log map start."""
        self.start_time = datetime.now()
        self._last_item_time = self.start_time
        extra = self._get_base_extra("map_start")
        extra["total"] = self.total_items
        self.logger.info(
            f"Map '{self.step_name}' started ({self.total_items} items)", extra=extra
        )

    def update(self, status: str) -> None:
        """Update progress when an item completes."""
        now = datetime.now()
        if self._last_item_time:
            item_time = (now - self._last_item_time).total_seconds()
            self._item_times.append(item_time)
        self._last_item_time = now

        if status == "completed":
            self.completed += 1
        elif status == "failed":
            self.failed += 1

        pct = (
            int(100 * self.completed / self.total_items)
            if self.total_items > 0
            else 100
        )

        interval = self.config.progress_interval
        pct_interval = (
            max(10, 100 // (100 // interval)) if self.total_items > 0 else 100
        )

        if pct >= self._last_pct + pct_interval or self.completed == self.total_items:
            self._last_pct = pct
            self._log_progress()

    def _get_timing_stats(self) -> dict[str, float]:
        """Calculate timing statistics."""
        if not self._item_times:
            return {"avg_item_time": 0.0, "estimated_completion": 0.0}

        avg_item_time = sum(self._item_times) / len(self._item_times)
        remaining_items = self.total_items - self.completed - self.failed
        estimated_completion = avg_item_time * remaining_items

        return {
            "avg_item_time": avg_item_time,
            "estimated_completion": estimated_completion,
        }

    def _log_progress(self) -> None:
        pct = (
            int(100 * self.completed / self.total_items)
            if self.total_items > 0
            else 100
        )
        bar_len = 20
        filled = (
            int(bar_len * self.completed / self.total_items)
            if self.total_items > 0
            else bar_len
        )
        bar = "=" * filled + ">" + " " * (bar_len - filled)

        timing_stats = self._get_timing_stats()

        extra = self._get_base_extra("map_progress")
        extra["total"] = self.total_items
        extra["completed"] = self.completed
        extra["failed"] = self.failed
        extra["avg_item_time"] = timing_stats["avg_item_time"]
        extra["estimated_completion"] = timing_stats["estimated_completion"]

        msg = f"  [{bar}] {self.completed}/{self.total_items} ({pct}%)"
        if timing_stats["avg_item_time"] > 0:
            msg += f" avg={timing_stats['avg_item_time']:.2f}s/item"
        if timing_stats["estimated_completion"] > 0:
            msg += f" eta={timing_stats['estimated_completion']:.1f}s"

        self.logger.info(msg, extra=extra)

    def complete(self) -> None:
        """Log map completion."""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
        else:
            duration = 0.0

        timing_stats = self._get_timing_stats()

        extra = self._get_base_extra("map_complete")
        extra["duration"] = duration
        extra["total"] = self.total_items
        extra["completed"] = self.completed
        extra["failed"] = self.failed
        extra["avg_item_time"] = timing_stats["avg_item_time"]

        self.logger.info(
            "Map '%s' completed in %.3fs (avg=%.2fs/item)",
            self.step_name,
            duration,
            timing_stats["avg_item_time"],
            extra=extra,
        )


def get_logging_config(
    level: str | None = None,
    format: str | None = None,
    progress_interval: int | None = None,
    show_timestamps: bool | None = None,
    correlation_id: str | None = None,
    flow_name: str | None = None,
    run_id: str | None = None,
) -> LoggingConfig:
    """Create LoggingConfig with optional overrides."""
    return LoggingConfig(
        level=level or "INFO",
        format=format or "human",
        progress_interval=progress_interval or 10,
        show_timestamps=show_timestamps if show_timestamps is not None else True,
        correlation_id=correlation_id or generate_correlation_id(),
        flow_name=flow_name or "",
        run_id=run_id or "",
    )
