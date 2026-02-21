"""Step and flow decorators for defining pipelines."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lokki.graph import FlowGraph


class StepNode:
    """Represents a single step in the pipeline."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self.name = fn.__name__
        self._default_args: tuple[Any, ...] = ()
        self._default_kwargs: dict[str, Any] = {}
        self._next: StepNode | None = None
        self._prev: StepNode | None = None
        self._map_block: MapBlock | None = None
        self._closes_map_block: bool = False

    def __call__(self, *args: Any, **kwargs: Any) -> StepNode:
        """Record default args and return self for chaining."""
        self._default_args = args
        self._default_kwargs = kwargs
        return self

    def map(self, step_node: StepNode) -> MapBlock:
        """Start a Map block that runs the next step in parallel for each item."""
        block = MapBlock(source=self, inner_head=step_node)
        self._map_block = block
        return block

    def next(self, step_node: StepNode) -> StepNode:
        """Chain a step after the current one sequentially."""
        step_node._prev = self
        self._next = step_node
        return step_node

    def agg(self, step_node: StepNode) -> StepNode:
        """Raises TypeError - agg() must be called on MapBlock."""
        raise TypeError(
            ".agg() must be called on the result of .map(), not directly on a step"
        )


class MapBlock:
    """Represents a Map block opened by .map()."""

    def __init__(self, source: StepNode, inner_head: StepNode) -> None:
        self.source = source
        self.inner_head = inner_head
        self.inner_tail = inner_head
        self._next: StepNode | None = None

    @property
    def inner_steps(self) -> list[StepNode]:
        """Get all inner steps as a list."""
        steps = []
        current: StepNode | None = self.inner_head
        while current is not None:
            steps.append(current)
            if current is self.inner_tail:
                break
            current = current._next
        return steps

    def map(self, step_node: StepNode) -> MapBlock:
        """Add another step to the inner chain of the Map block."""
        step_node._prev = self.inner_tail
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def next(self, step_node: StepNode) -> MapBlock:
        """Add a step to the inner chain of the Map block (before agg)."""
        step_node._prev = self.inner_tail
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def agg(self, step_node: StepNode) -> StepNode:
        """Close the Map block and attach an aggregation step."""
        step_node._closes_map_block = True
        step_node._map_block = self
        self._next = step_node
        return step_node


def step(fn: Callable[..., Any]) -> StepNode:
    """Decorate a function as a pipeline step."""
    return StepNode(fn)


def flow(fn: Callable[..., Any]) -> Callable[..., FlowGraph]:
    """Decorate a function as a pipeline flow."""

    def wrapper(*args: Any, **kwargs: Any) -> FlowGraph:
        from lokki.graph import FlowGraph

        head = fn(*args, **kwargs)

        if head is None:
            raise ValueError(
                f"@flow function '{fn.__name__}' returned None. "
                "Did you forget to return the chain? "
                "Example: return step1().map(step2)"
            )

        if not isinstance(head, StepNode | MapBlock):
            raise ValueError(
                f"@flow function '{fn.__name__}' must return a step chain "
                "(e.g., step1().map(step2)), but returned {type(head).__name__}"
            )

        return FlowGraph(name=fn.__name__.replace("_", "-").lower(), head=head)

    wrapper._is_flow = True  # type: ignore[attr-defined]
    wrapper._fn = fn  # type: ignore[attr-defined]
    return wrapper
