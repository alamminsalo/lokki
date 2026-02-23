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

    def test_step_node_next_chains_sequentially(self) -> None:
        """Test that .next() chains a step sequentially."""

        @step
        def first() -> str:
            return "a"

        @step
        def second(x: str) -> str:
            return x + "b"

        result = first.next(second)

        assert isinstance(result, StepNode)
        assert result is second
        assert first._next is second

    def test_step_node_next_allows_further_chaining(self) -> None:
        """Test that .next() returns StepNode allowing further chaining."""

        @step
        def first() -> str:
            return "a"

        @step
        def second(x: str) -> str:
            return x + "b"

        @step
        def third(x: str) -> str:
            return x + "c"

        chain = first.next(second).next(third)

        assert isinstance(chain, StepNode)
        assert chain is third
        assert first._next is second
        assert second._next is third


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

    def test_map_block_next_adds_to_inner_chain(self) -> None:
        """Test that .next() adds a step to the inner chain."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def step1(item: str) -> str:
            return item.upper()

        @step
        def step2(item: str) -> str:
            return item + "!"

        block = source.map(step1).next(step2)

        assert isinstance(block, MapBlock)
        assert step1._next is step2

    def test_map_block_next_multiple_steps(self) -> None:
        """Test chaining multiple steps via .next() inside Map block."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def step1(item: str) -> str:
            return item.upper()

        @step
        def step2(item: str) -> str:
            return item + "1"

        @step
        def step3(item: str) -> str:
            return item + "2"

        chain = source.map(step1).next(step2).next(step3)

        assert isinstance(chain, MapBlock)
        assert step1._next is step2
        assert step2._next is step3

    def test_map_block_concurrency_limit(self) -> None:
        """Test that .map() accepts concurrency_limit parameter."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner(item: str) -> str:
            return item.upper()

        block = source.map(inner, concurrency_limit=10)

        assert isinstance(block, MapBlock)
        assert block.concurrency_limit == 10

    def test_map_block_concurrency_limit_none_by_default(self) -> None:
        """Test that concurrency_limit defaults to None."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner(item: str) -> str:
            return item.upper()

        block = source.map(inner)

        assert block.concurrency_limit is None


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

        @step
        def agg(items: list[str]) -> str:
            return ", ".join(items)

        @flow
        def flow_with_map_head():
            return first().map(second).agg(agg)

        graph = flow_with_map_head()

        assert len(graph.entries) >= 1

    def test_flow_graph_linear_chain_with_next(self) -> None:
        """Test FlowGraph with .next() linear chaining."""

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
        def linear_flow():
            return first().next(second).next(third)

        graph = linear_flow()

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "first"
        assert isinstance(graph.entries[1], TaskEntry)
        assert graph.entries[1].node.name == "second"
        assert isinstance(graph.entries[2], TaskEntry)
        assert graph.entries[2].node.name == "third"

    def test_flow_graph_open_map_block_raises(self) -> None:
        """Test that flow ending with open Map block raises ValueError."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @flow
        def open_map_flow():
            return get_items().map(process)

        with pytest.raises(ValueError) as exc_info:
            open_map_flow()

        assert "open Map block" in str(exc_info.value)

    def test_flow_graph_nested_map_raises(self) -> None:
        """Test that nested .map() calls raise ValueError."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def inner1(item: str) -> str:
            return item.upper()

        @step
        def inner2(item: str) -> str:
            return item + "!"

        @flow
        def nested_map_flow():
            return get_items().map(inner1).map(inner2)

        with pytest.raises(ValueError) as exc_info:
            nested_map_flow()

        assert "Nested .map()" in str(exc_info.value) or "open Map block" in str(
            exc_info.value
        )
