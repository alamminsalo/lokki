"""Logging utilities for lokki."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class LogFormat(Enum):
    HUMAN = "human"
    JSON = "json"


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "human"
    progress_interval: int = 10
    show_timestamps: bool = True


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
        }

        for key in (
            "step",
            "duration",
            "status",
            "run_id",
            "total",
            "completed",
            "failed",
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

    def __init__(self, step_name: str, logger: logging.Logger) -> None:
        self.step_name = step_name
        self.logger = logger
        self.start_time: datetime | None = None

    def start(self) -> None:
        """Log step start."""
        self.start_time = datetime.now()
        extra = {"event": "step_start", "step": self.step_name}
        self.logger.info(f"Step '{self.step_name}' started", extra=extra)

    def complete(self, duration: float) -> None:
        """Log step completion."""
        extra = {
            "event": "step_complete",
            "step": self.step_name,
            "duration": duration,
            "status": "success",
        }
        self.logger.info(
            f"Step '{self.step_name}' completed in {duration:.3f}s (status=success)",
            extra=extra,
        )

    def fail(self, duration: float, error: Exception) -> None:
        """Log step failure."""
        extra = {
            "event": "step_fail",
            "step": self.step_name,
            "duration": duration,
            "status": "failed",
        }
        self.logger.error(
            f"Step '{self.step_name}' failed after {duration:.3f}s: {error}",
            extra=extra,
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

    def start(self) -> None:
        """Log map start."""
        self.start_time = datetime.now()
        extra = {
            "event": "map_start",
            "step": self.step_name,
            "total": self.total_items,
        }
        self.logger.info(
            f"Map '{self.step_name}' started ({self.total_items} items)", extra=extra
        )

    def update(self, status: str) -> None:
        """Update progress when an item completes."""
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

        extra = {
            "event": "map_progress",
            "step": self.step_name,
            "total": self.total_items,
            "completed": self.completed,
            "failed": self.failed,
        }
        self.logger.info(
            f"  [{bar}] {self.completed}/{self.total_items} ({pct}%)", extra=extra
        )

    def complete(self) -> None:
        """Log map completion."""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
        else:
            duration = 0.0

        extra = {
            "event": "map_complete",
            "step": self.step_name,
            "duration": duration,
            "total": self.total_items,
            "completed": self.completed,
            "failed": self.failed,
        }
        self.logger.info(
            f"Map '{self.step_name}' completed in {duration:.3f}s", extra=extra
        )


def get_logging_config(
    level: str | None = None,
    format: str | None = None,
    progress_interval: int | None = None,
    show_timestamps: bool | None = None,
) -> LoggingConfig:
    """Create LoggingConfig with optional overrides."""
    return LoggingConfig(
        level=level or "INFO",
        format=format or "human",
        progress_interval=progress_interval or 10,
        show_timestamps=show_timestamps if show_timestamps is not None else True,
    )
