"""Decorators and DAG tracking for Lokki pipeline library."""

from collections.abc import Callable
from functools import wraps
from typing import Any, Optional

from .models import StepNode


class StepTracker:
    """Context manager to track step function calls during flow execution."""

    _instance: Optional["StepTracker"] = None

    def __init__(self) -> None:
        self.steps: dict[str, StepNode] = {}
        self.call_stack: list[str] = []

    def __enter__(self) -> "StepTracker":
        StepTracker._instance = self
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        StepTracker._instance = None

    def register_step_call(self, step_name: str, func: Callable) -> str:
        """Register a step function call."""
        dependencies = self.call_stack.copy()

        self.steps[step_name] = StepNode(
            name=step_name,
            function=func,
            dependencies=dependencies,
            outputs=[step_name],
        )

        self.call_stack.append(step_name)
        return step_name

    @classmethod
    def get_instance(cls) -> Optional["StepTracker"]:
        """Get the current tracker instance."""
        return cls._instance


_global_step_functions: dict[str, Callable] = {}


def step(func: Callable) -> Callable:
    """Decorator to mark a function as a pipeline step."""
    step_name = func.__name__
    _global_step_functions[step_name] = func

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracker = StepTracker.get_instance()
        if tracker is not None:
            tracker.register_step_call(step_name, func)
            return f"result_of_{step_name}"
        return func(*args, **kwargs)

    return wrapper


def flow(func: Callable) -> Callable:
    """Decorator to mark a function as a pipeline flow.

    When called without arguments, returns a Pipeline instance.
    When called with arguments, executes the flow function directly.
    """
    from .data_store import DataStore

    flow_name = func.__name__

    @wraps(func)
    def wrapper(
        *args: Any, datastore: DataStore | None = None, **kwargs: Any
    ) -> Any:
        if args or kwargs:
            return func(*args, **kwargs)
        from .pipeline import Pipeline

        return Pipeline(func, flow_name, datastore)

    return wrapper
