"""Tests for scheduling functionality."""

import pytest

from lokki.decorators import flow, step


class TestScheduleValidation:
    """Tests for schedule expression validation."""

    def test_valid_cron_expression(self) -> None:
        """Test that valid cron expressions are accepted."""

        @step
        def mystep() -> str:
            return "hello"

        @flow(schedule="cron(0 9 * * ? *)")
        def my_flow():
            return mystep()

        graph = my_flow()
        assert graph.schedule == "cron(0 9 * * ? *)"

    def test_valid_rate_expression(self) -> None:
        """Test that valid rate expressions are accepted."""

        @step
        def mystep() -> str:
            return "hello"

        @flow(schedule="rate(1 hour)")
        def my_flow():
            return mystep()

        graph = my_flow()
        assert graph.schedule == "rate(1 hour)"

    def test_valid_rate_minutes(self) -> None:
        """Test that rate with minutes is accepted."""

        @step
        def mystep() -> str:
            return "hello"

        @flow(schedule="rate(30 minutes)")
        def my_flow():
            return mystep()

        graph = my_flow()
        assert graph.schedule == "rate(30 minutes)"

    def test_valid_rate_days(self) -> None:
        """Test that rate with days is accepted."""

        @step
        def mystep() -> str:
            return "hello"

        @flow(schedule="rate(1 day)")
        def my_flow():
            return mystep()

        graph = my_flow()
        assert graph.schedule == "rate(1 day)"

    def test_invalid_schedule_raises(self) -> None:
        """Test that invalid schedule expressions raise ValueError."""
        with pytest.raises(ValueError, match="Invalid schedule expression"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="invalid")
            def my_flow():
                return mystep()

            my_flow()

    def test_empty_schedule_raises(self) -> None:
        """Test that empty schedule raises ValueError."""
        with pytest.raises(ValueError, match="Invalid schedule expression"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="")
            def my_flow():
                return mystep()

            my_flow()

    def test_invalid_cron_raises(self) -> None:
        """Test that invalid cron expression raises ValueError."""
        with pytest.raises(ValueError, match="Invalid cron expression"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="cron(too many fields here)")
            def my_flow():
                return mystep()

            my_flow()

    def test_invalid_rate_raises(self) -> None:
        """Test that invalid rate expression raises ValueError."""
        with pytest.raises(ValueError, match="Invalid rate expression"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="rate(invalid unit)")
            def my_flow():
                return mystep()

            my_flow()

    def test_rate_negative_value_raises(self) -> None:
        """Test that negative rate value raises ValueError."""
        with pytest.raises(ValueError, match="Value must be a positive integer"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="rate(-1 hour)")
            def my_flow():
                return mystep()

            my_flow()

    def test_rate_invalid_unit_raises(self) -> None:
        """Test that invalid rate unit raises ValueError."""
        with pytest.raises(ValueError, match="Unit must be one of"):

            @step
            def mystep() -> str:
                return "hello"

            @flow(schedule="rate(1 week)")
            def my_flow():
                return mystep()

            my_flow()

    def test_no_schedule(self) -> None:
        """Test that flow without schedule has None."""

        @step
        def mystep() -> str:
            return "hello"

        @flow
        def my_flow():
            return mystep()

        graph = my_flow()
        assert graph.schedule is None

    def test_schedule_with_map_agg(self) -> None:
        """Test schedule with map/agg pattern."""

        @step
        def get_items() -> list:
            return [1, 2, 3]

        @step
        def process(item: int) -> int:
            return item * 2

        @step
        def aggregate(items: list) -> int:
            return sum(items)

        @flow(schedule="cron(0 0 * * ? *)")
        def my_flow():
            return get_items().map(process).agg(aggregate)

        graph = my_flow()
        assert graph.schedule == "cron(0 0 * * ? *)"

    def test_schedule_with_next(self) -> None:
        """Test schedule with .next() chaining."""

        @step
        def step_a() -> int:
            return 1

        @step
        def step_b(x: int) -> int:
            return x + 1

        @step
        def step_c(x: int) -> int:
            return x + 2

        @flow(schedule="rate(1 hour)")
        def my_flow():
            return step_a().next(step_b).next(step_c)

        graph = my_flow()
        assert graph.schedule == "rate(1 hour)"


class TestFlowGraphSchedule:
    """Tests for FlowGraph schedule attribute."""

    def test_flowgraph_stores_schedule(self) -> None:
        """Test that FlowGraph stores schedule from decorator."""

        @step
        def mystep() -> str:
            return "hello"

        @flow(schedule="cron(0 12 * * ? *)")
        def daily_flow():
            return mystep()

        graph = daily_flow()
        assert hasattr(graph, "schedule")
        assert graph.schedule == "cron(0 12 * * ? *)"

    def test_flowgraph_schedule_none_by_default(self) -> None:
        """Test that schedule is None when not specified."""

        @step
        def mystep() -> str:
            return "hello"

        @flow
        def no_schedule_flow():
            return mystep()

        graph = no_schedule_flow()
        assert graph.schedule is None
