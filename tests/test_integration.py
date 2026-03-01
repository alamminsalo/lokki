"""Integration tests for local flow execution."""

from lokki import flow, step
from lokki.runtime.local import LocalRunner


class TestFlowExecution:
    """Integration tests for flow execution."""

    def test_simple_flow(self) -> None:
        @step
        def get_values():
            return [1, 2, 3]

        @step
        def double(x):
            return x * 2

        @step
        def sum_values(values):
            return sum(values)

        @flow
        def test_flow():
            return get_values().map(double).agg(sum_values)

        runner = LocalRunner()
        result = runner.run(test_flow(), {})
        assert result == 12

    def test_flow_with_params(self) -> None:
        @step
        def get_values():
            return [1, 2, 3]

        @step
        def multiply(x):
            return x * 2

        @step
        def sum_values(values):
            return sum(values)

        @flow
        def test_flow():
            return get_values().map(multiply).agg(sum_values)

        runner = LocalRunner()
        result = runner.run(test_flow(), {})
        assert result == 12

    def test_sequential_steps(self) -> None:
        @step
        def step_a():
            return "a"

        @step
        def step_b(prev):
            return prev + "b"

        @step
        def step_c(prev):
            return prev + "c"

        @flow
        def test_flow():
            return step_a().next(step_b).next(step_c)

        runner = LocalRunner()
        result = runner.run(test_flow(), {})
        assert result == "abc"

    def test_map_with_inner_chain(self) -> None:
        @step
        def get_items():
            return [1, 2, 3]

        @step
        def add_one(x):
            return x + 1

        @step
        def double(x):
            return x * 2

        @step
        def sum_items(items):
            return sum(items)

        @flow
        def test_flow():
            return get_items().map(add_one).next(double).agg(sum_items)

        runner = LocalRunner()
        result = runner.run(test_flow(), {})
        assert result == 18

    def test_flow_with_retry_success(self) -> None:
        call_count = 0

        @step(retry={"retries": 3, "delay": 0.01})
        def unreliable_step(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return x * 2

        @flow
        def test_flow():
            return unreliable_step()

        runner = LocalRunner()
        result = runner.run(test_flow(), {"x": 5})
        assert result == 10
        assert call_count == 2
