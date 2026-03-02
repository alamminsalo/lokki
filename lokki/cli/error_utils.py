"""CLI error handling utilities.

This module provides utilities for consistent error handling across CLI commands.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from lokki.config import LokkiConfig
    from lokki.graph import FlowGraph

logger = logging.getLogger(__name__)


def print_error(message: str) -> None:
    """Print an error message to stderr via logging."""
    logger.error(message)


def exit_on_error(message: str, code: int = 1) -> None:
    """Log an error message and exit with the given code."""
    logger.error(message)
    sys.exit(code)


@contextmanager
def cli_context(
    flow_fn: Callable[[], FlowGraph],
    require_bucket: bool = True,
) -> Iterator[tuple[FlowGraph, LokkiConfig]]:
    """Context manager for CLI command handlers.

    Handles common error patterns:
    - Flow graph creation failures
    - Configuration loading failures
    - Missing artifact bucket validation

    Args:
        flow_fn: The flow function to call
        require_bucket: Whether to require artifact_bucket in config

    Yields:
        Tuple of (FlowGraph, LokkiConfig)

    Example:
        with cli_context(flow_fn) as (graph, config):
            # ... command logic ...
    """
    from lokki.config import load_config

    try:
        graph = flow_fn()
    except Exception as e:
        exit_on_error(f"Failed to create flow graph: {e}")

    try:
        config = load_config()
    except Exception as e:
        exit_on_error(f"Failed to load configuration: {e}")

    if require_bucket and not config.artifact_bucket:
        logger.error("'artifact_bucket' is not configured.")
        logger.error(
            "Please set it in lokki.toml or via LOKKI_ARTIFACT_BUCKET env var."
        )
        sys.exit(1)

    yield graph, config
