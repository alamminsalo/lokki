"""Unit tests for sam_template module."""

import json
import tempfile
from pathlib import Path

import yaml

from lokki._utils import get_step_names, to_pascal
from lokki.builder.sam_template import build_sam_template
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph


class TestSamTemplateHelpers:
    """Tests for helper functions."""

    def testto_pascal(self) -> None:
        assert to_pascal("get_items") == "GetItems"

    def testget_step_names_single(self) -> None:
        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        names = get_step_names(graph)
        assert names == {"step1"}


class TestBuildSamTemplateSimple:
    """Tests for build_sam_template with simple flows."""

    def test_template_structure(self) -> None:
        """Test basic SAM template structure."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            assert "AWSTemplateFormatVersion" in template
            assert "Resources" in template

    def test_zip_package_type(self) -> None:
        """Test ZIP package type generates correct resources."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.package_type = "zip"

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            func = resources["Step1Function"]
            # ZIP package type uses CodeUri instead of ImageUri
            assert "CodeUri" in func["Properties"]

    def test_image_package_type(self) -> None:
        """Test image package type generates correct resources."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.package_type = "image"

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            func = resources["Step1Function"]
            assert func["Properties"]["PackageType"] == "Image"

    def test_environment_variables(self) -> None:
        """Test environment variables are set correctly."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            env = resources["Step1Function"]["Properties"]["Environment"]["Variables"]
            assert env["LOKKI_S3_BUCKET"] == {"Ref": "S3Bucket"}
            assert env["LOKKI_FLOW_NAME"] == "test-flow"
            assert "LOKKI_AWS_ENDPOINT" in env
            assert env["LOKKI_STEP_NAME"] == "step1"

            params = template.get("Parameters", {})
            assert "S3Bucket" in params

    def test_custom_environment_variables(self) -> None:
        """Test custom environment variables are included."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.env = {"MY_VAR": "my-value"}

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            env = resources["Step1Function"]["Properties"]["Environment"]["Variables"]
            assert env["MY_VAR"] == "my-value"


class TestBuildSamTemplateMultiple:
    """Tests for build_sam_template with multiple steps."""

    def test_multiple_steps(self) -> None:
        """Test multiple lambda functions are created."""

        @step
        def step1() -> None:
            pass

        @step
        def step2() -> None:
            pass

        step1().next(step2)
        graph = FlowGraph(name="test-flow", head=step2)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            assert "Step1Function" in resources
            assert "Step2Function" in resources


class TestBuildSamTemplateStateMachine:
    """Tests for build_sam_template with state machine."""

    def test_state_machine_included(self) -> None:
        """Test state machine resource is created when statemachine.json exists."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()

        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()

            # Create statemachine.json
            sm_path = build_dir / "statemachine.json"
            sm_path.write_text(json.dumps({"StartAt": "Step1", "States": {}}))

            template_str = build_sam_template(graph, config, build_dir, "test_module")

            template = yaml.safe_load(template_str)
            resources = template["Resources"]

            # Should have a StateMachine resource
            assert any("StateMachine" in key for key in resources.keys())
