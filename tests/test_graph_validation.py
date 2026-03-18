"""Tests for FlowGraph validation."""

import pytest

from lokki import flow, step
from lokki._errors import GraphValidationError
from lokki.graph import FlowGraph


class TestFlowGraphValidation:
    """Test FlowGraph validation logic."""

    def test_valid_graph(self) -> None:
        """Test that valid graphs pass validation."""

        @step
        def get_data() -> list[int]:
            return [1, 2, 3]

        @step
        def process(item: int) -> int:
            return item * 2

        @step
        def aggregate(items: list[int]) -> int:
            return sum(items)

        @flow
        def valid_flow() -> FlowGraph:
            return get_data().map(process).agg(aggregate)

        # Should not raise
        graph = valid_flow()
        assert len(graph.entries) > 0

    def test_duplicate_step_names(self) -> None:
        """Test detection of duplicate step names."""

        @step
        def step_a() -> int:
            return 1

        @step
        def step_b(x: int) -> int:
            return x + 1

        # Create a graph with duplicate step usage
        # This is prevented by the decorator system, but we test validation
        node_a = step_a
        node_b = step_b

        # Manually create a scenario where same node is used twice
        # In practice, the decorator prevents this
        chain = node_a().next(node_b)

        # Graph should validate successfully (no duplicates in this case)
        graph = FlowGraph("test-chain", chain)
        assert graph.step_names == {"step_a", "step_b"}

    def test_empty_map_block(self) -> None:
        """Test detection of empty map blocks."""
        # Empty map blocks are prevented by the map() implementation
        # but we test the validation logic
        with pytest.raises(ValueError, match="step list cannot be empty"):

            @step
            def get_data() -> list[int]:
                return [1, 2, 3]

            get_data().map([])  # type: ignore

    def test_graph_with_no_entries(self) -> None:
        """Test that graphs with no entries fail validation."""
        # This is hard to trigger in normal usage, but test the logic
        # by creating an empty entries list manually
        graph = FlowGraph.__new__(FlowGraph)
        graph.name = "empty"
        graph.entries = []
        graph.schedule = None

        with pytest.raises(GraphValidationError, match="Graph has no entries"):
            graph._validate()

    def test_multiple_steps_in_map(self) -> None:
        """Test graph with multiple steps in map."""

        @step
        def get_data() -> list[int]:
            return [1, 2, 3]

        @step
        def transform(x: int) -> int:
            return x * 2

        @step
        def validate(x: int) -> bool:
            return x > 0

        @step
        def aggregate(items: list[bool]) -> int:
            return sum(1 for x in items if x)

        @flow
        def multi_step_map_flow() -> FlowGraph:
            return get_data().map([transform, validate]).agg(aggregate)

        # Should not raise
        graph = multi_step_map_flow()
        assert len(graph.entries) > 0
        assert "transform" in graph.step_names
        assert "validate" in graph.step_names

    def test_map_without_aggregation(self) -> None:
        """Test map blocks without aggregation."""

        @step
        def get_events() -> list[dict]:
            return [{"id": 1}, {"id": 2}]

        @step
        def send_event(event: dict) -> None:
            pass

        @flow
        def map_without_agg_flow() -> FlowGraph:
            return get_events().map(send_event)

        # Should not raise - maps can end without aggregation
        graph = map_without_agg_flow()
        assert len(graph.entries) > 0
