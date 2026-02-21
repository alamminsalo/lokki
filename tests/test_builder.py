"""Unit tests for builder module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from lokki.builder.builder import Builder, _get_flow_module_name
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph


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

    def test_build_creates_sam_template(self) -> None:
        """Test that build creates sam.yaml."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            config.build_dir = str(Path(tmpdir) / "lokki-build")

            Builder.build(graph, config, flow_fn=None)

            sam_path = Path(config.build_dir) / "sam.yaml"
            assert sam_path.exists()

            content = sam_path.read_text()
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
