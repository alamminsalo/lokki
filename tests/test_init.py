"""Unit tests for lokki public API exports."""


from lokki.decorators import StepNode
from lokki.graph import FlowGraph


def test_step_export() -> None:
    """Test that step decorator is exported from lokki package."""
    from lokki import step

    assert step is not None
    assert callable(step)


def test_flow_export() -> None:
    """Test that flow decorator is exported from lokki package."""
    from lokki import flow

    assert flow is not None
    assert callable(flow)


def test_step_decorator_wraps_function() -> None:
    """Test that step decorator returns a StepNode."""
    from lokki import step
    from lokki.decorators import StepNode

    @step
    def example_step() -> str:
        return "result"

    assert isinstance(example_step, StepNode)
    assert example_step.name == "example_step"


def test_flow_decorator_wraps_function() -> None:
    """Test that flow decorator returns a wrapper that produces FlowGraph."""
    from lokki import flow, step

    @step
    def first_step() -> list[str]:
        return ["item1", "item2"]

    @flow
    def example_flow() -> "StepNode":
        return first_step()

    graph = example_flow()

    assert isinstance(graph, FlowGraph)
    assert graph.name == "example-flow"
