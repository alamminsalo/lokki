"""Runtime module exports."""

from typing import Any

from lokki.runtime.batch import make_batch_handler as batch
from lokki.runtime.lambda_handler import make_handler as make_lambda_handler
from lokki.runtime.local import LocalRunner
from lokki.runtime.runtime import Runtime


def lambda_fn(fn: Any, retry_config: Any = None) -> Any:
    """Create a Lambda handler for a step function."""
    return make_lambda_handler(fn, retry_config)


__all__ = ["Runtime", "lambda_fn", "batch", "LocalRunner"]
