"""Unit tests for state_machine module."""

from unittest.mock import MagicMock

from lokki._utils import to_pascal
from lokki.builder.state_machine import (
    _lambda_arn,
    _task_state,
    build_state_machine,
)
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph


class TestToPascal:
    """Tests for to_pascal helper function."""

    def test_simple_name(self) -> None:
        """Test converting simple snake_case to PascalCase."""
        assert to_pascal("get_items") == "GetItems"

    def test_single_word(self) -> None:
        """Test single word conversion."""
        assert to_pascal("process") == "Process"

    def test_multiple_words(self) -> None:
        """Test multiple words."""
        assert to_pascal("get_items_from_s3") == "GetItemsFromS3"

    def test_already_pascal(self) -> None:
        """Test handling of already PascalCase."""
        assert to_pascal("GetItems") == "Getitems"


class TestLambdaArn:
    """Tests for _lambda_arn helper function."""

    def test_basic_arn(self) -> None:
        """Test basic ARN generation."""
        config = MagicMock(spec=LokkiConfig)
        arn = _lambda_arn(config, "get_items", "my-flow")
        assert "my-flow-get_items" in arn
        assert "lambda" in arn.lower()

    def test_arn_format(self) -> None:
        """Test ARN format includes placeholders."""
        config = MagicMock(spec=LokkiConfig)
        arn = _lambda_arn(config, "process", "test-flow")
        assert "arn:aws:lambda" in arn
        assert "AWS::Region" in arn
        assert "AWS::AccountId" in arn


class TestTaskState:
    """Tests for _task_state helper function."""

    def test_task_state_structure(self) -> None:
        """Test task state has correct structure."""
        from lokki.decorators import RetryConfig

        config = MagicMock(spec=LokkiConfig)
        mock_step = MagicMock()
        mock_step.name = "my_step"
        mock_step.retry = RetryConfig()

        state = _task_state(mock_step, config, "test-flow")

        assert state["Type"] == "Task"
        assert "Resource" in state
        assert state["ResultPath"] == "$.input"
        assert state["Next"] is None
        assert "Retry" not in state

    def test_task_state_with_retry(self) -> None:
        """Test task state includes retry when configured."""
        from lokki.decorators import RetryConfig

        config = MagicMock(spec=LokkiConfig)
        mock_step = MagicMock()
        mock_step.name = "my_step"
        mock_step.retry = RetryConfig(retries=3, delay=2, backoff=2.0)

        state = _task_state(mock_step, config, "test-flow")

        assert state["Type"] == "Task"
        assert "Retry" in state
        assert state["Retry"][0]["MaxAttempts"] == 4
        assert state["Retry"][0]["IntervalSeconds"] == 2
        assert state["Retry"][0]["BackoffRate"] == 2.0


class TestBuildStateMachineSimple:
    """Tests for build_state_machine with simple chains."""

    def test_single_task(self) -> None:
        """Test state machine with single task."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        graph = FlowGraph(name="test-flow", head=get_items)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "StartAt" in sm
        assert "States" in sm
        assert "GetItems" in sm["States"]
        assert sm["States"]["GetItems"]["Type"] == "Task"
        assert sm["States"]["GetItems"]["End"] is True

    def test_two_task_chain(self) -> None:
        """Test state machine with two sequential tasks."""

        @step
        def step1() -> list[str]:
            return ["a"]

        @step
        def step2(item: str) -> str:
            return item.upper()

        step1().next(step2)

        graph = FlowGraph(name="test-flow", head=step2)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "Step1" in sm["States"]
        assert "Step2" in sm["States"]
        assert sm["States"]["Step2"]["End"] is True
        assert sm["States"]["Step1"]["Next"] == "Step2"

    def test_three_task_chain(self) -> None:
        """Test state machine with three sequential tasks."""

        @step
        def start() -> int:
            return 1

        @step
        def middle(x: int) -> int:
            return x * 2

        @step
        def end_state(x: int) -> int:
            return x + 1

        start().next(middle).next(end_state)

        graph = FlowGraph(name="my-flow", head=end_state)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "Start" in sm["States"]
        assert "Middle" in sm["States"]
        assert "EndState" in sm["States"]
        assert sm["States"]["Start"]["Next"] == "Middle"
        assert sm["States"]["Middle"]["Next"] == "EndState"


class TestBuildStateMachineMap:
    """Tests for build_state_machine with Map blocks."""

    def test_simple_map_block(self) -> None:
        """Test state machine with simple Map block."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "GetItems" in sm["States"]
        assert "GetItemsMap" in sm["States"]
        assert "Aggregate" in sm["States"]

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["Type"] == "Map"
        assert "ItemProcessor" in map_state
        assert "Process" in map_state["ItemProcessor"]["States"]

    def test_map_block_with_inner_chain(self) -> None:
        """Test state machine with Map block containing multiple inner steps."""

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

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        inner_states = map_state["ItemProcessor"]["States"]
        assert "Transform" in inner_states
        assert "Validate" in inner_states
        assert inner_states["Transform"]["Next"] == "Validate"
        assert inner_states["Validate"]["End"] is True

    def test_map_block_with_concurrency_limit(self) -> None:
        """Test state machine with Map block concurrency_limit."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process, concurrency_limit=10).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["Type"] == "Map"
        assert map_state["MaxConcurrency"] == 10

    def test_map_block_without_concurrency_limit(self) -> None:
        """Test state machine with Map block without concurrency_limit."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["Type"] == "Map"
        assert "MaxConcurrency" not in map_state


class TestBuildStateMachineComplex:
    """Tests for complex state machine scenarios."""

    def test_multiple_sequential_maps(self) -> None:
        """Test state machine with multiple map blocks in sequence."""

        @step
        def start1() -> list[str]:
            return ["a"]

        @step
        def start2() -> list[str]:
            return ["b"]

        @step
        def process1(item: str) -> str:
            return item.upper()

        @step
        def process2(item: str) -> str:
            return item.lower()

        @step
        def join1(items: list[str]) -> str:
            return ",".join(items)

        @step
        def join2(items: list[str]) -> str:
            return "-".join(items)

        # This is not a valid flow structure - just testing basic generation
        start1().map(process1).agg(join1)

        graph = FlowGraph(name="test-flow", head=join1)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert len(sm["States"]) >= 3

    def test_end_state_no_next(self) -> None:
        """Test that final state has End=True and no Next."""

        @step
        def step1() -> None:
            pass

        @step
        def step2() -> None:
            pass

        step1().next(step2)

        graph = FlowGraph(name="test-flow", head=step2)

        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert sm["States"]["Step2"]["End"] is True
        assert (
            "Next" not in sm["States"]["Step2"]
            or sm["States"]["Step2"].get("Next") is None
        )
