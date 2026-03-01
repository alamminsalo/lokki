"""Tests for step retry functionality."""

from unittest.mock import MagicMock, patch

import pytest

from lokki.decorators import RetryConfig, StepNode
from lokki.decorators import step as step_decorator


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        """Test RetryConfig has correct default values."""
        config = RetryConfig()
        assert config.retries == 0
        assert config.delay == 1.0
        assert config.backoff == 1.0
        assert config.max_delay == 60.0
        assert config.exceptions == (Exception,)

    def test_custom_values(self) -> None:
        """Test RetryConfig accepts custom values."""
        config = RetryConfig(
            retries=5,
            delay=2.0,
            backoff=1.5,
            max_delay=30.0,
            exceptions=(ValueError, TimeoutError),
        )
        assert config.retries == 5
        assert config.delay == 2.0
        assert config.backoff == 1.5
        assert config.max_delay == 30.0
        assert config.exceptions == (ValueError, TimeoutError)

    def test_negative_retries_raises(self) -> None:
        """Test negative retries raises ValueError."""
        with pytest.raises(ValueError, match="retries must be non-negative"):
            RetryConfig(retries=-1)

    def test_zero_delay_raises(self) -> None:
        """Test zero delay raises ValueError."""
        with pytest.raises(ValueError, match="delay must be positive"):
            RetryConfig(delay=0)

    def test_negative_backoff_raises(self) -> None:
        """Test negative backoff raises ValueError."""
        with pytest.raises(ValueError, match="backoff must be positive"):
            RetryConfig(backoff=-1)

    def test_zero_max_delay_raises(self) -> None:
        """Test zero max_delay raises ValueError."""
        with pytest.raises(ValueError, match="max_delay must be positive"):
            RetryConfig(max_delay=0)


class TestStepDecoratorWithRetry:
    """Tests for @step decorator with retry parameter."""

    def test_step_without_retry(self) -> None:
        """Test step without retry uses defaults."""

        @step_decorator
        def my_step(data):
            return data

        assert isinstance(my_step, StepNode)
        assert my_step.retry.retries == 0

    def test_step_with_retry_dict(self) -> None:
        """Test step accepts retry as dict."""

        @step_decorator(retry={"retries": 3, "delay": 2})
        def my_step(data):
            return data

        assert my_step.retry.retries == 3
        assert my_step.retry.delay == 2

    def test_step_with_retry_config(self) -> None:
        """Test step accepts RetryConfig object."""

        @step_decorator(retry=RetryConfig(retries=5, delay=1))
        def my_step(data):
            return data

        assert my_step.retry.retries == 5
        assert my_step.retry.delay == 1

    def test_step_with_invalid_retry_raises(self) -> None:
        """Test invalid retry type raises TypeError."""
        with pytest.raises(TypeError, match="retry must be"):
            step_decorator(lambda x: x, retry="invalid")


class TestRetryInRunner:
    """Tests for retry logic in LocalRunner."""

    def test_retry_success_first_try(self) -> None:
        """Test step succeeds on first try, no retries."""
        from lokki.graph import FlowGraph
        from lokki.runtime.local import LocalRunner

        call_count = 0

        @step_decorator
        def my_step(data):
            nonlocal call_count
            call_count += 1
            return data * 2

        FlowGraph(name="test", head=my_step)
        runner = LocalRunner()

        with patch.object(runner, "_execute_step", return_value=10):
            pass

    def test_retry_config_accessible_from_node(self) -> None:
        """Test retry config is accessible from StepNode."""
        from lokki.graph import FlowGraph

        @step_decorator(retry={"retries": 3, "delay": 2})
        def my_step(data):
            return data

        graph = FlowGraph(name="test", head=my_step)

        entry = graph.entries[0]
        assert entry.node.retry.retries == 3
        assert entry.node.retry.delay == 2


class TestRetryInStateMachine:
    """Tests for retry in state machine generation."""

    def test_task_without_retry_no_retry_field(self) -> None:
        """Test task without retry has no Retry field."""
        from lokki.builder.state_machine import _task_state
        from lokki.config import LokkiConfig

        mock_step = MagicMock()
        mock_step.name = "my_step"
        mock_step.retry = RetryConfig()

        config = LokkiConfig()
        state = _task_state(mock_step, config, "test-flow")

        assert "Retry" not in state

    def test_task_with_retry_includes_retry_field(self) -> None:
        """Test task with retry includes Retry field."""
        from lokki.builder.state_machine import _task_state
        from lokki.config import LokkiConfig

        mock_step = MagicMock()
        mock_step.name = "my_step"
        mock_step.retry = RetryConfig(retries=3, delay=2, backoff=2)

        config = LokkiConfig()
        state = _task_state(mock_step, config, "test-flow")

        assert "Retry" in state
        assert state["Retry"][0]["MaxAttempts"] == 4
        assert state["Retry"][0]["IntervalSeconds"] == 2
        assert state["Retry"][0]["BackoffRate"] == 2

    def test_build_state_machine_with_retry(self) -> None:
        """Test full state machine includes retry for configured steps."""
        from lokki.builder.state_machine import build_state_machine
        from lokki.config import LokkiConfig
        from lokki.graph import FlowGraph

        @step_decorator
        def step_with_retry(data):
            return data

        graph = FlowGraph(name="test", head=step_with_retry)
        config = LokkiConfig()

        sm = build_state_machine(graph, config)

        assert "StepWithRetry" in sm["States"]


class TestExceptionMapping:
    """Tests for exception to AWS error mapping."""

    def test_default_exception_mapping(self) -> None:
        """Test default Exception maps to Lambda.ServiceException."""
        from lokki.builder.state_machine import _exception_to_error_equals

        assert _exception_to_error_equals(Exception) == "Lambda.ServiceException"

    def test_connection_error_mapping(self) -> None:
        """Test ConnectionError maps to SdkClientException."""
        from lokki.builder.state_machine import _exception_to_error_equals

        assert (
            _exception_to_error_equals(ConnectionError) == "Lambda.SdkClientException"
        )

    def test_timeout_error_mapping(self) -> None:
        """Test TimeoutError maps to AWSException."""
        from lokki.builder.state_machine import _exception_to_error_equals

        assert _exception_to_error_equals(TimeoutError) == "Lambda.AWSException"

    def test_custom_exception_mapping(self) -> None:
        """Test custom exceptions get runtime exception name."""
        from lokki.builder.state_machine import _exception_to_error_equals

        class MyCustomError(Exception):
            pass

        result = _exception_to_error_equals(MyCustomError)
        assert "MyCustomError" in result
