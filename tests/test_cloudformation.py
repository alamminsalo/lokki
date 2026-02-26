"""Unit tests for cloudformation module."""

import yaml

from lokki._utils import get_step_names, to_pascal
from lokki.builder.cloudformation import build_template
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph
from tests.conftest import create_build_dir


class TestToPascal:
    """Tests for to_pascal helper."""

    def test_simple_name(self) -> None:
        assert to_pascal("get_items") == "GetItems"

    def test_single_word(self) -> None:
        assert to_pascal("process") == "Process"


class TestGetStepNames:
    """Tests for get_step_names helper."""

    def test_single_step(self) -> None:
        @step
        def get_items() -> list[str]:
            return ["a"]

        graph = FlowGraph(name="test-flow", head=get_items)
        names = get_step_names(graph)
        assert names == {"get_items"}

    def test_two_steps(self) -> None:
        @step
        def step1() -> None:
            pass

        @step
        def step2() -> None:
            pass

        step1().next(step2)
        graph = FlowGraph(name="test-flow", head=step2)
        names = get_step_names(graph)
        assert names == {"step1", "step2"}

    def test_map_block(self) -> None:
        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(items: list[str]) -> str:
            return ",".join(items)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        names = get_step_names(graph)
        assert names == {"get_items", "process", "aggregate"}


class TestBuildTemplateSimple:
    """Tests for build_template with simple flows."""

    def test_template_structure(self) -> None:
        """Test basic template structure."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        graph = FlowGraph(name="test-flow", head=get_items)
        config = LokkiConfig()
        template_str = build_template(graph, config, "test_module", create_build_dir())

        template = yaml.safe_load(template_str)
        assert "AWSTemplateFormatVersion" in template
        assert "Parameters" in template
        assert "Resources" in template

    def test_parameters(self) -> None:
        """Test CloudFormation parameters."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        params = template["Parameters"]

        assert "FlowName" in params
        assert "S3Bucket" in params
        assert "ImageTag" in params
        assert "PackageType" in params

    def test_lambda_execution_role(self) -> None:
        """Test Lambda execution role is created."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "LambdaExecutionRole" in resources
        assert resources["LambdaExecutionRole"]["Type"] == "AWS::IAM::Role"

    def test_stepfunctions_execution_role(self) -> None:
        """Test Step Functions execution role is created."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "StepFunctionsExecutionRole" in resources


class TestBuildTemplateZipPackage:
    """Tests for build_template with ZIP package type."""

    def test_zip_package_type(self) -> None:
        """Test ZIP package type generates correct resources."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.package_type = "zip"
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        func = resources["Step1Function"]
        assert func["Properties"]["PackageType"] == "Zip"
        assert "S3Bucket" in func["Properties"]["Code"]
        assert "S3Key" in func["Properties"]["Code"]

    def test_zip_package_environment(self) -> None:
        """Test ZIP package includes environment variables."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.package_type = "zip"
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        env_vars = resources["Step1Function"]["Properties"]["Environment"]["Variables"]
        assert "LOKKI_S3_BUCKET" in env_vars
        assert "LOKKI_FLOW_NAME" in env_vars
        assert "LOKKI_STEP_NAME" in env_vars


class TestBuildTemplateImagePackage:
    """Tests for build_template with image package type."""

    def test_image_package_type(self) -> None:
        """Test image package type generates correct resources."""

        @step
        def step1() -> None:
            pass

        graph = FlowGraph(name="test-flow", head=step1)
        config = LokkiConfig()
        config.lambda_cfg.package_type = "image"
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        func = resources["Step1Function"]
        assert func["Properties"]["PackageType"] == "Image"
        assert "ImageUri" in func["Properties"]["Code"]


class TestBuildTemplateMultipleSteps:
    """Tests for build_template with multiple steps."""

    def test_multiple_lambda_functions(self) -> None:
        """Test multiple lambda functions are created."""

        @step
        def step1() -> None:
            pass

        @step
        def step2() -> None:
            pass

        @step
        def step3() -> None:
            pass

        step1().next(step2).next(step3)
        graph = FlowGraph(name="test-flow", head=step3)
        config = LokkiConfig()
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "Step1Function" in resources
        assert "Step2Function" in resources
        assert "Step3Function" in resources


class TestBuildTemplateMapBlock:
    """Tests for build_template with Map blocks."""

    def test_map_block_includes_all_steps(self) -> None:
        """Test Map block includes source and inner steps."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(items: list[str]) -> str:
            return ",".join(items)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig()
        build_dir = create_build_dir()
        template_str = build_template(graph, config, "test_module", build_dir)

        template = yaml.safe_load(template_str)
        resources = template["Resources"]

        assert "GetItemsFunction" in resources
        assert "ProcessFunction" in resources
        assert "AggregateFunction" in resources
