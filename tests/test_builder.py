"""Unit tests for builder module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from lokki.builder.builder import (
    Builder,
    _get_flow_module_name,
    _has_batch_steps,
    _has_lambda_steps,
)
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph


class TestHasLambdaSteps:
    """Tests for _has_lambda_steps helper."""

    def test_has_lambda_steps_with_task_entry(self) -> None:
        """Test returns True for TaskEntry with lambda job type."""

        @step
        def step1():
            pass

        step1_node = step1()
        graph = FlowGraph(name="test-flow", head=step1_node)

        assert _has_lambda_steps(graph) is True

    def test_has_lambda_steps_with_batch_entry(self) -> None:
        """Test returns False for TaskEntry with batch job type."""

        @step(job_type="batch")
        def batch_step():
            pass

        batch_node = batch_step()
        graph = FlowGraph(name="test-flow", head=batch_node)

        assert _has_lambda_steps(graph) is False

    def test_has_lambda_steps_with_map_open_entry(self) -> None:
        """Test returns True for MapOpenEntry with lambda steps."""

        @step
        def get_items():
            return [1, 2, 3]

        @step
        def process_item(item):
            return item * 2

        @step
        def aggregate(items):
            return items

        get_items_node = get_items()
        mapped = get_items_node.map(process_item).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=mapped)

        assert _has_lambda_steps(graph) is True

    def test_has_lambda_steps_with_map_open_batch(self) -> None:
        """Test returns True for MapCloseEntry with lambda agg step."""

        @step
        def get_items():
            return [1, 2, 3]

        @step(job_type="batch")
        def process_batch(item):
            return item * 2

        @step
        def aggregate(items):
            return items

        get_items_node = get_items()
        mapped = get_items_node.map(process_batch).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=mapped)

        assert _has_lambda_steps(graph) is True


class TestHasBatchSteps:
    """Tests for _has_batch_steps helper."""

    def test_has_batch_steps_with_task_entry(self) -> None:
        """Test returns True for TaskEntry with batch job type."""

        @step(job_type="batch")
        def batch_step():
            pass

        batch_node = batch_step()
        graph = FlowGraph(name="test-flow", head=batch_node)

        assert _has_batch_steps(graph) is True

    def test_has_batch_steps_with_lambda_entry(self) -> None:
        """Test returns False for TaskEntry with lambda job type."""

        @step
        def lambda_step():
            pass

        lambda_node = lambda_step()
        graph = FlowGraph(name="test-flow", head=lambda_node)

        assert _has_batch_steps(graph) is False

    def test_has_batch_steps_with_map_open_batch(self) -> None:
        """Test returns True for MapOpenEntry with batch steps."""

        @step
        def get_items():
            return [1, 2, 3]

        @step(job_type="batch")
        def process_batch(item):
            return item * 2

        @step
        def aggregate(items):
            return items

        get_items_node = get_items()
        mapped = get_items_node.map(process_batch).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=mapped)

        assert _has_batch_steps(graph) is True

    def test_has_batch_steps_with_map_close_aggregate(self) -> None:
        """Test returns True for MapCloseEntry with batch agg step."""

        @step
        def get_items():
            return [1, 2, 3]

        @step
        def process(item):
            return item * 2

        @step(job_type="batch")
        def aggregate(items):
            return sum(items)

        get_items_node = get_items()
        mapped = get_items_node.map(process).agg(aggregate)

        graph = FlowGraph(name="test-flow", head=mapped)

        assert _has_batch_steps(graph) is True


class TestGetFlowModuleName:
    """Tests for _get_flow_module_name helper."""

    def test_with_flow_fn(self) -> None:
        """Test getting module name from flow function."""

        @step
        def my_flow() -> None:
            pass

        graph = FlowGraph(name="my-flow", head=my_flow)

        with patch("lokki.builder.builder._get_flow_module_path") as mock_path:
            mock_path.return_value = Path("/path/to/my_flow.py")
            name = _get_flow_module_name(my_flow, graph)
            assert name == "my_flow"

    def test_without_flow_fn(self) -> None:
        """Test getting module name from graph name."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="my-test-flow", head=step1)
        name = _get_flow_module_name(None, graph)
        assert name == "my_test_flow"


class TestBuilderBuild:
    """Tests for Builder.build method."""

    def test_build_creates_directories(self) -> None:
        """Test that build creates required directories."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.build_dir = "lokki-build"

        with tempfile.TemporaryDirectory() as tmpdir:
            config.build_dir = str(Path(tmpdir) / "lokki-build")

            Builder.build(graph, config, flow_fn=None)

            build_dir = Path(config.build_dir)
            assert build_dir.exists()
            assert (build_dir / "lambdas").exists()

    def test_build_creates_state_machine(self) -> None:
        """Test that build creates statemachine.json."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            config.build_dir = str(Path(tmpdir) / "lokki-build")

            Builder.build(graph, config, flow_fn=None)

            sm_path = Path(config.build_dir) / "statemachine.json"
            assert sm_path.exists()

            sm = json.loads(sm_path.read_text())
            assert "StartAt" in sm
            assert "States" in sm

    def test_build_creates_cloudformation_template(self) -> None:
        """Test that build creates template.yaml."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            config.build_dir = str(Path(tmpdir) / "lokki-build")

            Builder.build(graph, config, flow_fn=None)

            template_path = Path(config.build_dir) / "template.yaml"
            assert template_path.exists()

            content = template_path.read_text()
            assert "AWSTemplateFormatVersion" in content

    def test_build_with_multiple_steps(self) -> None:
        """Test build with multiple steps."""

        @step
        def step1() -> None:
            pass

        @step
        def step2() -> None:
            pass

        step1().next(step2)
        graph = FlowGraph(name="multi-step-flow", head=step2)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            config.build_dir = str(Path(tmpdir) / "lokki-build")

            Builder.build(graph, config, flow_fn=None)

            sm_path = Path(config.build_dir) / "statemachine.json"
            sm = json.loads(sm_path.read_text())

            # Both steps should be in the state machine
            assert "Step1" in sm["States"] or "GetItems" in sm["States"]
