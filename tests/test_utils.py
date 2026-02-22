"""Unit tests for _utils module."""

import pytest

from lokki._utils import get_step_names, to_kebab, to_pascal
from lokki.decorators import step
from lokki.graph import FlowGraph


class TestToPascal:
    """Tests for to_pascal function."""

    def test_simple_name(self) -> None:
        assert to_pascal("get_items") == "GetItems"

    def test_single_word(self) -> None:
        assert to_pascal("process") == "Process"

    def test_multiple_words(self) -> None:
        assert to_pascal("get_items_from_s3") == "GetItemsFromS3"

    def test_already_pascal(self) -> None:
        assert to_pascal("GetItems") == "Getitems"


class TestToKebab:
    """Tests for to_kebab function."""

    def test_simple_name(self) -> None:
        assert to_kebab("get_items") == "get-items"

    def test_single_word(self) -> None:
        assert to_kebab("process") == "process"

    def test_multiple_words(self) -> None:
        assert to_kebab("get_items_from_s3") == "get-items-from-s3"

    def test_already_kebab(self) -> None:
        assert to_kebab("get-items") == "get-items"


class TestGetStepNames:
    """Tests for get_step_names function."""

    def test_single_step(self) -> None:
        @step
        def step1():
            return 1

        graph = FlowGraph(name="test-flow", head=step1)
        names = get_step_names(graph)
        assert names == {"step1"}

    def test_two_steps(self) -> None:
        @step
        def step1():
            return 1

        @step
        def step2(x):
            return x * 2

        step1().next(step2)
        graph = FlowGraph(name="test-flow", head=step2)
        names = get_step_names(graph)
        assert names == {"step1", "step2"}

    def test_map_block(self) -> None:
        @step
        def get_items():
            return [1, 2, 3]

        @step
        def process(item):
            return item * 2

        @step
        def aggregate(items):
            return sum(items)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        names = get_step_names(graph)
        assert names == {"get_items", "process", "aggregate"}

    def test_map_with_next(self) -> None:
        @step
        def get_data():
            return [1, 2, 3]

        @step
        def process(item):
            return item * 2

        @step
        def save(item):
            return {"result": item}

        # Note: with .next() after .map(), the source step is reached differently
        get_data().map(process).next(save)
        graph = FlowGraph(name="test-flow", head=save)
        names = get_step_names(graph)
        # .next() after .map() doesn't include source in traversal from head
        assert names == {"process", "save"}
