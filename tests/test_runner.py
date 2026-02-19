"""Unit tests for lokki runner module."""

import json
from pathlib import Path
from typing import Any

from lokki.decorators import flow, step
from lokki.runner import LocalRunner


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
        assert result == 12

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
        from lokki.runner import LocalStore

        store = LocalStore(tmp_path)
        store.write("flow", "run1", "step1", {"key": "value"})

        result = store.read(str(tmp_path / "flow" / "run1" / "step1" / "output.pkl.gz"))
        assert result == {"key": "value"}

    def test_store_write_manifest(self, tmp_path: Path) -> None:
        from lokki.runner import LocalStore

        store = LocalStore(tmp_path)
        items = [{"item": "a", "index": 0}, {"item": "b", "index": 1}]
        store.write_manifest("flow", "run1", "step1", items)

        manifest_path = tmp_path / "flow" / "run1" / "step1" / "map_manifest.json"
        assert manifest_path.exists()
        assert json.loads(manifest_path.read_text()) == items
