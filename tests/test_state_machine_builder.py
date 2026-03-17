"""Unit tests for state_machine builder module - additional coverage."""

from lokki.builder.state_machine import (
    _build_retry_field,
    _exception_to_error_equals,
    build_state_machine,
)
from lokki.config import LokkiConfig
from lokki.decorators import RetryConfig, step
from lokki.graph import FlowGraph


class TestExceptionToErrorEquals:
    """Tests for _exception_to_error_equals helper function."""

    def test_connection_error(self) -> None:
        """Test ConnectionError mapping."""
        result = _exception_to_error_equals(ConnectionError)
        assert result == "Lambda.SdkClientException"

    def test_timeout_error(self) -> None:
        """Test TimeoutError mapping."""
        result = _exception_to_error_equals(TimeoutError)
        assert result == "Lambda.AWSException"

    def test_os_error(self) -> None:
        """Test OSError mapping."""
        result = _exception_to_error_equals(OSError)
        assert result == "Lambda.SdkClientException"

    def test_io_error(self) -> None:
        """Test IOError mapping."""
        result = _exception_to_error_equals(IOError)
        assert result == "Lambda.SdkClientException"

    def test_generic_exception(self) -> None:
        """Test generic Exception mapping."""
        result = _exception_to_error_equals(Exception)
        assert result == "Lambda.ServiceException"

    def test_custom_exception(self) -> None:
        """Test custom exception mapping."""

        class CustomError(Exception):
            pass

        result = _exception_to_error_equals(CustomError)
        assert result == "java.lang.RuntimeException.CustomError"

    def test_value_error(self) -> None:
        """Test ValueError mapping."""
        result = _exception_to_error_equals(ValueError)
        assert result == "java.lang.RuntimeException.ValueError"


class TestBuildRetryField:
    """Tests for _build_retry_field helper function."""

    def test_retry_field_structure(self) -> None:
        """Test retry field has correct structure."""
        retry_config = RetryConfig(retries=3, delay=2, backoff=2.0)

        result = _build_retry_field(retry_config)

        assert len(result) == 1
        assert "ErrorEquals" in result[0]
        assert "IntervalSeconds" in result[0]
        assert "MaxAttempts" in result[0]
        assert "BackoffRate" in result[0]

    def test_retry_max_attempts(self) -> None:
        """Test MaxAttempts is retries + 1."""
        retry_config = RetryConfig(retries=5)

        result = _build_retry_field(retry_config)

        assert result[0]["MaxAttempts"] == 6

    def test_retry_interval_seconds(self) -> None:
        """Test IntervalSeconds matches delay."""
        retry_config = RetryConfig(delay=5)

        result = _build_retry_field(retry_config)

        assert result[0]["IntervalSeconds"] == 5

    def test_retry_backoff_rate(self) -> None:
        """Test BackoffRate matches backoff."""
        retry_config = RetryConfig(backoff=1.5)

        result = _build_retry_field(retry_config)

        assert result[0]["BackoffRate"] == 1.5

    def test_retry_error_equals(self) -> None:
        """Test ErrorEquals includes mapped exceptions."""
        retry_config = RetryConfig(
            retries=2,
            exceptions=(ConnectionError, TimeoutError, ValueError),
        )

        result = _build_retry_field(retry_config)

        error_equals = result[0]["ErrorEquals"]
        assert "Lambda.SdkClientException" in error_equals
        assert "Lambda.AWSException" in error_equals
        assert "java.lang.RuntimeException.ValueError" in error_equals

    def test_retry_default_exceptions(self) -> None:
        """Test retry with default exceptions."""
        retry_config = RetryConfig(retries=2)

        result = _build_retry_field(retry_config)

        error_equals = result[0]["ErrorEquals"]
        assert "Lambda.ServiceException" in error_equals


class TestStateMachineSequentialSteps:
    """Tests for sequential step chains in state machine."""

    def test_four_sequential_steps(self) -> None:
        """Test state machine with four sequential steps."""

        @step
        def step1() -> int:
            return 1

        @step
        def step2(x: int) -> int:
            return x + 1

        @step
        def step3(x: int) -> int:
            return x * 2

        @step
        def step4(x: int) -> int:
            return x - 1

        step1().next(step2).next(step3).next(step4)

        graph = FlowGraph(name="test-flow", head=step4)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "Step1" in sm["States"]
        assert "Step2" in sm["States"]
        assert "Step3" in sm["States"]
        assert "Step4" in sm["States"]

        assert sm["States"]["Step1"]["Next"] == "Step2"
        assert sm["States"]["Step2"]["Next"] == "Step3"
        assert sm["States"]["Step3"]["Next"] == "Step4"
        assert sm["States"]["Step4"]["End"] is True

    def test_five_sequential_steps(self) -> None:
        """Test state machine with five sequential steps."""

        @step
        def s1() -> None:
            pass

        @step
        def s2() -> None:
            pass

        @step
        def s3() -> None:
            pass

        @step
        def s4() -> None:
            pass

        @step
        def s5() -> None:
            pass

        s1().next(s2).next(s3).next(s4).next(s5)

        graph = FlowGraph(name="chain-flow", head=s5)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert len([s for s in sm["States"] if not s == "InitFlow"]) == 5


class TestStateMachineMapBlocks:
    """Tests for map blocks in state machine."""

    def test_map_with_three_inner_steps(self) -> None:
        """Test map block with three inner steps in sequence."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def transform1(item: str) -> str:
            return item.upper()

        @step
        def transform2(item: str) -> str:
            return item + "_processed"

        @step
        def transform3(item: str) -> str:
            return item + "_final"

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(transform1).next(transform2).next(transform3).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        inner_states = map_state["ItemProcessor"]["States"]

        assert "Transform1" in inner_states
        assert "Transform2" in inner_states
        assert "Transform3" in inner_states

        assert inner_states["Transform1"]["Next"] == "Transform2"
        assert inner_states["Transform2"]["Next"] == "Transform3"
        assert inner_states["Transform3"]["End"] is True

    def test_map_result_writer_configuration(self) -> None:
        """Test map block ResultWriter configuration."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item

        @step
        def aggregate(results: list[str]) -> list[str]:
            return results

        get_items().map(process).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        config.artifact_bucket = "my-bucket"
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        result_writer = map_state["ResultWriter"]

        assert result_writer["Resource"] == "arn:aws:states:::s3:putObject"
        assert result_writer["Parameters"]["Bucket"] == "my-bucket"

    def test_map_item_reader_configuration(self) -> None:
        """Test map block ItemReader configuration."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item

        @step
        def aggregate(results: list[str]) -> list[str]:
            return results

        get_items().map(process).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        config.artifact_bucket = "my-bucket"
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_reader = map_state["ItemReader"]

        assert item_reader["Resource"] == "arn:aws:states:::s3:getObject"
        assert item_reader["ReaderConfig"]["InputType"] == "JSON"
        assert item_reader["ReaderConfig"]["MaxItems"] == 100000
        assert item_reader["Parameters"]["Bucket"] == "my-bucket"


class TestStateMachineRetryConfiguration:
    """Tests for retry configuration in state machine."""

    def test_step_with_retry_config(self) -> None:
        """Test step with retry configuration."""

        @step(retry=RetryConfig(retries=3, delay=2, backoff=2.0))
        def retry_step() -> None:
            pass

        graph = FlowGraph(name="retry-flow", head=retry_step)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        state = sm["States"]["RetryStep"]
        assert "Retry" in state
        assert len(state["Retry"]) == 1

        retry_config = state["Retry"][0]
        assert retry_config["IntervalSeconds"] == 2
        assert retry_config["MaxAttempts"] == 4
        assert retry_config["BackoffRate"] == 2.0

    def test_step_with_custom_retry_exceptions(self) -> None:
        """Test step with custom retry exceptions."""

        @step(
            retry=RetryConfig(
                retries=2,
                exceptions=(ConnectionError, TimeoutError),
            )
        )
        def retry_step() -> None:
            pass

        graph = FlowGraph(name="retry-flow", head=retry_step)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        state = sm["States"]["RetryStep"]
        error_equals = state["Retry"][0]["ErrorEquals"]

        assert "Lambda.SdkClientException" in error_equals
        assert "Lambda.AWSException" in error_equals

    def test_step_without_retry(self) -> None:
        """Test step without retry configuration."""

        @step
        def no_retry_step() -> None:
            pass

        graph = FlowGraph(name="no-retry-flow", head=no_retry_step)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        state = sm["States"]["NoRetryStep"]
        assert "Retry" not in state


class TestStateMachineInitFlow:
    """Tests for InitFlow state in state machine."""

    def test_init_flow_structure(self) -> None:
        """Test InitFlow state has correct structure."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        init_flow = sm["States"]["InitFlow"]

        assert init_flow["Type"] == "Pass"
        assert "Assign" in init_flow
        assert "Parameters" in init_flow
        assert "Next" in init_flow

    def test_init_flow_assign(self) -> None:
        """Test InitFlow Assign field."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        init_flow = sm["States"]["InitFlow"]
        assign = init_flow["Assign"]

        assert "run_id" in assign
        assert "cache_enabled" in assign

    def test_init_flow_parameters(self) -> None:
        """Test InitFlow Parameters field."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        init_flow = sm["States"]["InitFlow"]
        params = init_flow["Parameters"]

        assert "flow" in params
        assert "input" in params
        assert "step_name" in params

    def test_init_flow_next(self) -> None:
        """Test InitFlow transitions to first step."""

        @step
        def first_step() -> None:
            pass

        @step
        def second_step() -> None:
            pass

        first_step().next(second_step)

        graph = FlowGraph(name="test-flow", head=second_step)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        init_flow = sm["States"]["InitFlow"]
        assert init_flow["Next"] == "FirstStep"


class TestStateMachineEdgeCases:
    """Tests for edge cases in state machine generation."""

    def test_empty_map_inner_steps(self) -> None:
        """Test map with no inner steps (edge case)."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def aggregate(results: list[str]) -> list[str]:
            return results

        get_items().map(get_items).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "GetItemsMap" in sm["States"]

    def test_map_with_high_concurrency(self) -> None:
        """Test map with high concurrency limit."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item

        @step
        def aggregate(results: list[str]) -> list[str]:
            return results

        get_items().map(process, concurrency_limit=1000).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["MaxConcurrency"] == 1000

    def test_map_with_zero_concurrency(self) -> None:
        """Test map with zero concurrency limit."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item

        @step
        def aggregate(results: list[str]) -> list[str]:
            return results

        get_items().map(process, concurrency_limit=0).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["MaxConcurrency"] == 0

    def test_long_step_name(self) -> None:
        """Test step with long name."""

        @step
        def very_long_step_name_with_many_words() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=very_long_step_name_with_many_words)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "VeryLongStepNameWithManyWords" in sm["States"]

    def test_step_name_with_numbers(self) -> None:
        """Test step name with numbers."""

        @step
        def process_123_items() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=process_123_items)
        config = LokkiConfig()
        sm = build_state_machine(graph, config)

        assert "Process123Items" in sm["States"]
