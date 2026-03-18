"""Shared utility functions for lokki."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from lokki.graph import FlowGraph

T = TypeVar("T")

__all__ = [
    "to_pascal",
    "to_kebab",
    "get_step_names",
    "timed",
    "timing_context",
]


def to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def to_kebab(name: str) -> str:
    """Convert snake_case to kebab-case."""
    return name.replace("_", "-")


def get_step_names(graph: FlowGraph) -> set[str]:
    """Extract unique step names from graph.

    Note: This function is deprecated. Use graph.step_names property instead.
    """
    return graph.step_names


def timed[T](func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that logs function execution duration.

    Automatically logs duration and metrics for the decorated function.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()
            logger = logging.getLogger(func.__module__)
            logger.debug(
                f"Function '{func.__name__}' completed in {duration:.3f}s",
                extra={"duration": duration, "function": func.__name__},
            )
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger = logging.getLogger(func.__module__)
            logger.error(
                f"Function '{func.__name__}' failed after {duration:.3f}s: {e}",
                extra={
                    "duration": duration,
                    "function": func.__name__,
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                },
            )
            raise

    return wrapper


@contextmanager
def timing_context(
    context_name: str, logger: logging.Logger | None = None
) -> Generator[None]:
    """Context manager for timing code blocks.

    Automatically logs duration and metrics for the code block.

    Args:
        context_name: Name/description of the context being timed
        logger: Optional logger instance (uses default logger if None)

    Yields:
        None

    Example:
        with timing_context("data processing"):
            # code to time
            process_data()
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        duration_ms = duration * 1000

        if logger is None:
            logger = logging.getLogger("lokki")

        logger.debug(
            f"{context_name} completed in {duration:.3f}s ({duration_ms:.1f}ms)",
            extra={
                "context": context_name,
                "duration": duration,
                "duration_ms": duration_ms,
            },
        )
