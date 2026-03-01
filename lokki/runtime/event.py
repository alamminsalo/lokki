"""Lambda event dataclasses for lokki flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FlowContext:
    """Flow context passed to all Lambda/Batch invocations.

    Contains execution metadata and flow parameters.
    """

    run_id: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlowContext:
        """Create FlowContext from dictionary."""
        return cls(
            run_id=data.get("run_id", "unknown"),
            params=data.get("params", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "params": self.params,
        }


@dataclass
class LambdaEvent:
    """Event passed to Lambda/Batch handlers.

    Standardized format for all step function invocations.
    """

    flow: FlowContext
    input: Any = None  # Data or S3 URL string

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LambdaEvent:
        """Create LambdaEvent from dictionary."""
        flow_data = data.get("flow", {})
        if isinstance(flow_data, FlowContext):
            flow = flow_data
        elif isinstance(flow_data, dict):
            flow = FlowContext.from_dict(flow_data)
        else:
            flow = FlowContext(run_id="unknown", params={})

        return cls(
            flow=flow,
            input=data.get("input", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "flow": self.flow.to_dict(),
            "input": self.input,
        }
