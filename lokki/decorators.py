"""Step and flow decorators for defining pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from lokki.graph import FlowGraph


class StepNode:
    """Represents a single step in the pipeline."""

    def __init__(self, fn: Callable) -> None:
        self.fn = fn
        self.name = fn.__name__
        self._default_args: tuple = ()
        self._default_kwargs: dict = {}
        self._next: StepNode | None = None
        self._map_block: MapBlock | None = None
        self._closes_map_block: bool = False

    def __call__(self, *args, **kwargs) -> StepNode:
        """Record default args and return self for chaining."""
        self._default_args = args
        self._default_kwargs = kwargs
        return self

    def map(self, step_node: StepNode) -> MapBlock:
        """Start a Map block that runs the next step in parallel for each item."""
        block = MapBlock(source=self, inner_head=step_node)
        self._map_block = block
        return block

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

    def map(self, step_node: StepNode) -> MapBlock:
        """Add another step to the inner chain of the Map block."""
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def agg(self, step_node: StepNode) -> StepNode:
        """Close the Map block and attach an aggregation step."""
        step_node._closes_map_block = True
        step_node._map_block = self
        self._next = step_node
        return step_node


def step(fn: Callable) -> StepNode:
    """Decorate a function as a pipeline step."""
    return StepNode(fn)


def flow(fn: Callable) -> Callable[..., FlowGraph]:
    """Decorate a function as a pipeline flow."""

    def wrapper(*args, **kwargs) -> FlowGraph:
        from lokki.graph import FlowGraph

        head = fn(*args, **kwargs)
        return FlowGraph(name=fn.__name__.replace("_", "-").lower(), head=head)

    wrapper._is_flow = True  # type: ignore[attr-defined]
    wrapper._fn = fn  # type: ignore[attr-defined]
    return wrapper
