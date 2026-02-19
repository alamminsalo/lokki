"""Unit tests for lokki decorators and graph modules."""

import pytest

from lokki.decorators import MapBlock, StepNode, flow, step
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


class TestStepNode:
    """Tests for StepNode class."""

    def test_step_node_creation(self) -> None:
        """Test creating a StepNode via decorator."""

        @step
        def my_step() -> str:
            return "result"

        assert isinstance(my_step, StepNode)
        assert my_step.name == "my_step"
        assert my_step._default_args == ()
        assert my_step._default_kwargs == {}

    def test_step_node_call_records_args(self) -> None:
        """Test that calling a StepNode records default args."""

        @step
        def my_step(x: int, y: int = 10) -> int:
            return x + y

        node = my_step(5, y=20)

        assert isinstance(node, StepNode)
        assert node._default_args == (5,)
        assert node._default_kwargs == {"y": 20}

    def test_step_node_call_returns_self(self) -> None:
        """Test that calling a StepNode returns self for chaining."""

        @step
        def my_step() -> str:
            return "result"

        node = my_step(1, 2, 3)
        assert node is my_step

    def test_step_node_map_creates_map_block(self) -> None:
        """Test that .map() creates a MapBlock."""

        @step
        def first() -> list[str]:
            return ["a", "b"]

        @step
        def second(item: str) -> str:
            return item.upper()

        map_block = first.map(second)

        assert isinstance(map_block, MapBlock)
        assert map_block.source is first
        assert map_block.inner_head is second
        assert first._map_block is map_block

    def test_step_node_agg_raises_type_error(self) -> None:
        """Test that calling .agg() directly on StepNode raises TypeError."""

        @step
        def my_step() -> str:
            return "result"

        @step
        def other_step() -> str:
            return "other"

        with pytest.raises(TypeError) as exc_info:
            my_step.agg(other_step)

        assert ".agg() must be called on the result of .map()" in str(exc_info.value)


class TestMapBlock:
    """Tests for MapBlock class."""

    def test_map_block_creation(self) -> None:
        """Test creating a MapBlock via .map()."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner(item: str) -> str:
            return item.upper()

        block = source.map(inner)

        assert isinstance(block, MapBlock)
        assert block.source is source
        assert block.inner_head is inner
        assert block.inner_tail is inner

    def test_map_block_map_chains_inner_steps(self) -> None:
        """Test that .map() on MapBlock chains inner steps."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def step1(item: str) -> str:
            return item.upper()

        @step
        def step2(item: str) -> str:
            return item + "!"

        block = source.map(step1).map(step2)

        assert block.inner_head is step1
        assert block.inner_tail is step2
        assert step1._next is step2

    def test_map_block_agg_closes_block(self) -> None:
        """Test that .agg() closes the MapBlock."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner(item: str) -> str:
            return item.upper()

        @step
        def agg(items: list[str]) -> str:
            return ", ".join(items)

        map_block = source.map(inner)
        agg_node = map_block.agg(agg)

        assert isinstance(agg_node, StepNode)
        assert agg_node._closes_map_block is True
        assert map_block._next is agg

    def test_map_block_returns_step_node_for_chaining(self) -> None:
        """Test that .agg() returns a StepNode allowing further chaining."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner(item: str) -> str:
            return item.upper()

        @step
        def agg(items: list[str]) -> str:
            return ", ".join(items)

        @step
        def final(result: str) -> str:
            return result + "!"

        result_node = source.map(inner).agg(agg)

        assert isinstance(result_node, StepNode)
        assert result_node is agg


class TestFlowDecorator:
    """Tests for @flow decorator."""

    def test_flow_decorator_creates_flow_graph(self) -> None:
        """Test that @flow decorator returns a FlowGraph when called."""

        @step
        def first() -> list[str]:
            return ["a", "b"]

        @flow
        def my_flow():
            return first()

        graph = my_flow()

        assert isinstance(graph, FlowGraph)
        assert graph.name == "my-flow"

    def test_flow_name_derivation(self) -> None:
        """Test that flow name is derived from function name."""

        @step
        def first() -> list[str]:
            return ["a"]

        @flow
        def birds_flow_example():
            return first()

        graph = birds_flow_example()
        assert graph.name == "birds-flow-example"

    def test_flow_preserves_is_flow_attribute(self) -> None:
        """Test that @flow sets _is_flow attribute on wrapper."""

        @step
        def first() -> list[str]:
            return ["a"]

        @flow
        def my_flow():
            return first()

        assert hasattr(my_flow, "_is_flow")
        assert my_flow._is_flow is True  # type: ignore[attr-defined]


class TestFlowGraph:
    """Tests for FlowGraph class."""

    def test_flow_graph_single_task(self) -> None:
        """Test FlowGraph with a single task."""

        @step
        def single_step() -> str:
            return "result"

        @flow
        def single_flow():
            return single_step()

        graph = single_flow()

        assert len(graph.entries) == 1
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "single_step"

    def test_flow_graph_linear_chain(self) -> None:
        """Test FlowGraph with a linear chain of tasks."""

        @step
        def first() -> str:
            return "a"

        @step
        def second(x: str) -> str:
            return x + "b"

        @step
        def third(x: str) -> str:
            return x + "c"

        @flow
        def chain_flow():
            return first().map(second).agg(third)

        graph = chain_flow()

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[0], TaskEntry)
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert isinstance(graph.entries[2], MapCloseEntry)

    def test_flow_graph_map_agg(self) -> None:
        """Test FlowGraph with .map().agg() pattern."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def join(items: list[str]) -> str:
            return ", ".join(items)

        @flow
        def map_agg_flow():
            return get_items().map(process).agg(join)

        graph = map_agg_flow()

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "get_items"

        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].source.name == "get_items"
        assert len(graph.entries[1].inner_steps) == 1
        assert graph.entries[1].inner_steps[0].name == "process"

        assert isinstance(graph.entries[2], MapCloseEntry)
        assert graph.entries[2].agg_step.name == "join"

    def test_flow_graph_chaining_after_agg(self) -> None:
        """Test FlowGraph with chaining after .agg()."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def join(items: list[str]) -> str:
            return ", ".join(items)

        @step
        def finalize(result: str) -> str:
            return result + "!"

        @flow
        def chain_after_agg_flow():
            return get_items().map(process).agg(join).map(finalize).agg(finalize)

        graph = chain_after_agg_flow()

        assert len(graph.entries) >= 3

    def test_flow_graph_head_is_map_block(self) -> None:
        """Test FlowGraph where head is a MapBlock (edge case)."""

        @step
        def first() -> list[str]:
            return ["a", "b"]

        @step
        def second(item: str) -> str:
            return item.upper()

        @flow
        def flow_with_map_head():
            return first().map(second)

        graph = flow_with_map_head()

        assert len(graph.entries) >= 1
