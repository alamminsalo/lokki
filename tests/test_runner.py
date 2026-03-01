"""Unit tests for lokki runner module."""

import json
from pathlib import Path
from typing import Any

import pytest

from lokki.decorators import flow, step
from lokki.runtime.local import LocalRunner


class TestLocalRunner:
    def test_run_single_task(self) -> None:
        @step
        def hello() -> str:
            return "hello"

        @flow
        def test_flow() -> Any:
            return hello()

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == "hello"

    def test_run_simple_chain(self) -> None:
        @step
        def step1() -> int:
            return 5

        @flow
        def test_flow() -> Any:
            return step1()

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == 5

    def test_run_map_agg(self) -> None:
        @step
        def get_items() -> list[str]:
            return ["a", "b", "c"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def collect(items: list[str]) -> str:
            return ",".join(items)

        @flow
        def test_flow() -> Any:
            return get_items().map(process).agg(collect)

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == "A,B,C"

    def test_run_map_multiple_inner_steps(self) -> None:
        @step
        def get_items() -> list[int]:
            return [1, 2, 3]

        @step
        def add_one(x: int) -> int:
            return x + 1

        @step
        def double(x: int) -> int:
            return x * 2

        @step
        def sum_all(items: list[int]) -> int:
            return sum(items)

        @flow
        def test_flow() -> Any:
            return get_items().map(add_one).map(double).agg(sum_all)

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == 18

    def test_run_map_with_next(self) -> None:
        """Test running a flow with .map().next().agg() pattern."""

        @step
        def get_items() -> list[int]:
            return [1, 2, 3]

        @step
        def add_one(x: int) -> int:
            return x + 1

        @step
        def double(x: int) -> int:
            return x * 2

        @step
        def sum_all(items: list[int]) -> int:
            return sum(items)

        @flow
        def test_flow() -> Any:
            return get_items().map(add_one).next(double).agg(sum_all)

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == 18

    def test_run_linear_next_chain(self) -> None:
        """Test running a flow with .next() linear chaining."""

        @step
        def step_a() -> int:
            return 1

        @step
        def step_b(x: int) -> int:
            return x + 10

        @step
        def step_c(x: int) -> int:
            return x * 2

        @flow
        def test_flow() -> Any:
            return step_a().next(step_b).next(step_c)

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == 22

    def test_run_with_default_args(self) -> None:
        @step
        def greet(name: str = "world") -> str:
            return f"hello {name}"

        @flow
        def test_flow() -> Any:
            return greet()

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == "hello world"


class TestLocalStore:
    def test_store_write_read(self, tmp_path: Path) -> None:
        from lokki.runtime.local import LocalStore

        store = LocalStore(tmp_path)
        store.write("flow", "run1", "step1", {"key": "value"})

        result = store.read(str(tmp_path / "flow" / "run1" / "step1" / "output.pkl.gz"))
        assert result == {"key": "value"}

    def test_store_write_manifest(self, tmp_path: Path) -> None:
        from lokki.runtime.local import LocalStore

        store = LocalStore(tmp_path)
        items = [{"item": "a", "index": 0}, {"item": "b", "index": 1}]
        store.write_manifest("flow", "run1", "step1", items)

        manifest_path = tmp_path / "flow" / "run1" / "step1" / "map_manifest.json"
        assert manifest_path.exists()
        assert json.loads(manifest_path.read_text()) == items


class TestRetryLogic:
    def test_retry_on_failure(self) -> None:
        from lokki.decorators import RetryConfig

        call_count = 0

        @step(retry=RetryConfig(retries=2, delay=0.001))
        def unreliable() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        @flow
        def test_flow() -> Any:
            return unreliable()

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted_raises(self) -> None:
        from lokki.decorators import RetryConfig

        @step(retry=RetryConfig(retries=0))
        def always_fails() -> str:
            raise ValueError("Permanent failure")

        @flow
        def test_flow() -> Any:
            return always_fails()

        runner = LocalRunner()
        with pytest.raises(ValueError, match="Permanent failure"):
            runner.run(test_flow())

    def test_batch_job_type_logged(self) -> None:
        @step(job_type="batch")
        def batch_step(x: int) -> int:
            return x * 2

        @flow
        def test_flow() -> Any:
            return batch_step(5)

        runner = LocalRunner()
        result = runner.run(test_flow())
        assert result == 10
