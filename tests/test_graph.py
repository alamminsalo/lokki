"""Unit tests for lokki graph module."""

from lokki.decorators import step
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


class TestFlowGraphSimpleChain:
    """Tests for FlowGraph with simple sequential chains."""

    def test_single_step(self) -> None:
        """Test graph with a single step."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        graph = FlowGraph(name="test-flow", head=get_items)

        assert graph.name == "test-flow"
        assert len(graph.entries) == 1
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "get_items"

    def test_two_step_chain(self) -> None:
        """Test graph with two sequential steps."""

        @step
        def step1() -> list[str]:
            return ["a", "b"]

        @step
        def step2(item: str) -> str:
            return item.upper()

        step1().next(step2)

        graph = FlowGraph(name="test-flow", head=step2)

        assert len(graph.entries) == 2
        assert graph.entries[0].node.name == "step1"
        assert graph.entries[1].node.name == "step2"

    def test_three_step_chain(self) -> None:
        """Test graph with three sequential steps."""

        @step
        def start() -> int:
            return 1

        @step
        def middle(x: int) -> int:
            return x * 2

        @step
        def end(x: int) -> int:
            return x + 1

        start().next(middle).next(end)

        graph = FlowGraph(name="test-flow", head=end)

        assert len(graph.entries) == 3
        assert graph.entries[0].node.name == "start"
        assert graph.entries[1].node.name == "middle"
        assert graph.entries[2].node.name == "end"


class TestFlowGraphMapBlock:
    """Tests for FlowGraph with Map blocks."""

    def test_simple_map_block(self) -> None:
        """Test graph with a simple .map().agg() block."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        @step
        def process_item(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process_item).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "get_items"
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].source.name == "get_items"
        assert len(graph.entries[1].inner_steps) == 1
        assert graph.entries[1].inner_steps[0].name == "process_item"
        assert isinstance(graph.entries[2], MapCloseEntry)
        assert graph.entries[2].agg_step.name == "aggregate"

    def test_map_block_with_multiple_inner_steps(self) -> None:
        """Test graph with Map block containing multiple inner steps."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def transform(item: str) -> str:
            return item.upper()

        @step
        def validate(item: str) -> bool:
            return len(item) > 0

        @step
        def aggregate(results: list[bool]) -> int:
            return sum(results)

        get_items().map(transform).next(validate).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert len(graph.entries[1].inner_steps) == 2
        assert graph.entries[1].inner_steps[0].name == "transform"
        assert graph.entries[1].inner_steps[1].name == "validate"

    def test_map_block_concurrency_limit(self) -> None:
        """Test that concurrency_limit is preserved in MapOpenEntry."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        @step
        def process_item(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process_item, concurrency_limit=10).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].concurrency_limit == 10

    def test_map_block_concurrency_limit_none_by_default(self) -> None:
        """Test that concurrency_limit defaults to None."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process_item(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process_item).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].concurrency_limit is None


class TestFlowGraphValidation:
    """Tests for FlowGraph validation."""

    def test_closed_map_block_valid(self) -> None:
        """Test that a closed Map block is valid."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process_item(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        # Properly close the map block
        get_items().map(process_item).agg(aggregate)

        # This should not raise
        graph = FlowGraph(name="test-flow", head=aggregate)
        assert len(graph.entries) == 3


class TestGraphEntryTypes:
    """Tests for graph entry types."""

    def test_task_entry(self) -> None:
        """Test TaskEntry creation."""

        @step
        def my_step() -> None:
            pass

        entry = TaskEntry(node=my_step)
        assert entry.node.name == "my_step"

    def test_map_open_entry(self) -> None:
        """Test MapOpenEntry creation."""

        @step
        def source() -> list[str]:
            return ["a", "b"]

        @step
        def inner1(item: str) -> str:
            return item

        @step
        def inner2(item: str) -> str:
            return item

        entry = MapOpenEntry(source=source, inner_steps=[inner1, inner2])
        assert entry.source.name == "source"
        assert len(entry.inner_steps) == 2

    def test_map_close_entry(self) -> None:
        """Test MapCloseEntry creation."""

        @step
        def agg_step() -> None:
            pass

        entry = MapCloseEntry(agg_step=agg_step)
        assert entry.agg_step.name == "agg_step"


class TestMapWithoutAggregation:
    """Tests for map blocks without aggregation."""

    def test_map_without_agg_valid(self) -> None:
        """Test that map without .agg() is valid and doesn't raise."""

        @step
        def get_events() -> list[dict]:
            return [{"id": 1}, {"id": 2}]

        @step
        def send_webhook(event: dict) -> dict:
            return {"sent": event["id"]}

        head = get_events().map(send_webhook)
        graph = FlowGraph(name="test", head=head)

        assert len(graph.entries) == 2
        assert isinstance(graph.entries[0], TaskEntry)
        assert graph.entries[0].node.name == "get_events"
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].source.name == "get_events"
        assert graph.entries[1].has_aggregation is False

    def test_map_with_agg_still_works(self) -> None:
        """Test that map with .agg() still works."""

        @step
        def get_items() -> list[int]:
            return [1, 2, 3]

        @step
        def double(item: int) -> int:
            return item * 2

        @step
        def sum_items(items: list[int]) -> int:
            return sum(items)

        head = get_items().map(double).agg(sum_items)
        graph = FlowGraph(name="test", head=head)

        assert len(graph.entries) == 3
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert graph.entries[1].has_aggregation is True
        assert isinstance(graph.entries[2], MapCloseEntry)

    def test_map_without_agg_multiple_inner_steps(self) -> None:
        """Test map without agg with multiple inner steps."""

        @step
        def get_events() -> list[dict]:
            return [{"id": 1}]

        @step
        def validate(event: dict) -> dict:
            return event

        @step
        def send(event: dict) -> dict:
            return {"sent": event["id"]}

        head = get_events().map(validate).map(send)
        graph = FlowGraph(name="test", head=head)

        assert len(graph.entries) == 2
        assert isinstance(graph.entries[1], MapOpenEntry)
        assert len(graph.entries[1].inner_steps) == 2
        assert graph.entries[1].has_aggregation is False
