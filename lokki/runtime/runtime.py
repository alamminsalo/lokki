"""Shared runtime interface for calling step functions."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class Runtime:
    """Shared runtime interface for calling step functions.

    Provides static methods for executing step functions consistently
    across different runtime environments (Lambda, Batch, Local).
    """

    @staticmethod
    def accepts_kwargs(fn: Callable[..., Any]) -> bool:
        """Check if function accepts **kwargs.

        Args:
            fn: The function to check

        Returns:
            True if fn accepts **kwargs, False otherwise
        """
        sig = inspect.signature(fn)
        return any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

    @staticmethod
    def filter_flow_params(
        fn: Callable[..., Any], flow_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter flow params based on function signature.

        If the function accepts **kwargs, pass all flow params.
        Otherwise, filter to only explicitly accepted params.

        Args:
            fn: The function to check
            flow_params: Flow parameters from execution context

        Returns:
            Filtered dict with only params that fn accepts
        """
        if not flow_params:
            return {}

        # If function accepts **kwargs, pass all flow params
        if Runtime.accepts_kwargs(fn):
            return flow_params

        # Otherwise, filter to only explicitly accepted params
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        return {k: v for k, v in flow_params.items() if k in accepted}

    @staticmethod
    def call_step(
        fn: Callable[..., Any],
        input_data: Any = None,
        flow_params: dict[str, Any] | None = None,
    ) -> Any:
        """Call a step function with input and flow params.

        Args:
            fn: The step function to call
            input_data: Output from previous step (or None for first step)
            flow_params: Flow-level parameters from execution context

        Returns:
            Result of calling fn with appropriate arguments
        """
        flow_params = flow_params or {}

        if input_data is None:
            # First step - no input from previous step
            filtered_params = Runtime.filter_flow_params(fn, flow_params)
            if filtered_params:
                return fn(**filtered_params)
            return fn()
        else:
            # Subsequent step - has input from previous step
            filtered_params = Runtime.filter_flow_params(fn, flow_params)
            if filtered_params:
                return fn(input_data, **filtered_params)
            return fn(input_data)
