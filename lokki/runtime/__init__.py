"""Runtime module exports."""

from lokki.runtime.runtime import Runtime
from lokki.runtime.lambda_handler import make_handler as make_lambda_handler
from lokki.runtime.batch import make_batch_handler as Batch
from lokki.runtime.local import LocalRunner


def Lambda(fn, retry_config=None):
    """Create a Lambda handler for a step function."""
    return make_lambda_handler(fn, retry_config)


__all__ = ["Runtime", "Lambda", "Batch", "LocalRunner"]
