"""Comprehensive unit tests for Distributed Map state machine generation.

These tests validate the structure of the generated Step Functions state machine
to ensure it uses Distributed Map (not Inline Map) with proper ItemSelector
and ResultWriter configuration.
"""

import pytest

from lokki.decorators import step
from lokki.graph import FlowGraph
from lokki.builder.state_machine import build_state_machine
from lokki.config import LokkiConfig


class TestDistributedMapBasicStructure:
    """Tests for basic Distributed Map state machine structure."""

    def test_map_has_startat(self) -> None:
        """Test that state machine has StartAt set to first state."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        assert "StartAt" in sm
        assert sm["StartAt"] == "InitFlow"

    def test_map_has_required_states(self) -> None:
        """Test that state machine has all required states."""

        @step
        def get_values() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_values().map(process).agg(aggregate)
        graph = FlowGraph(name="my-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        assert "InitFlow" in sm["States"]
        assert "GetValues" in sm["States"]
        assert "GetValuesMap" in sm["States"]
        assert "Aggregate" in sm["States"]

        # Process is inside the Map's ItemProcessor.States
        map_state = sm["States"]["GetValuesMap"]
        assert "Process" in map_state["ItemProcessor"]["States"]

    def test_map_type_is_map(self) -> None:
        """Test that Map state has Type 'Map'."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert map_state["Type"] == "Map"


class TestDistributedMapProcessorConfig:
    """Tests for Distributed Map ProcessorConfig validation."""

    def test_itemprocessor_exists(self) -> None:
        """Test that ItemProcessor exists in Map state."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "ItemProcessor" in map_state

    def test_processor_config_mode_distributed(self) -> None:
        """Test that ProcessorConfig.Mode is DISTRIBUTED."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        processor_config = map_state["ItemProcessor"]["ProcessorConfig"]
        assert processor_config["Mode"] == "DISTRIBUTED"

    def test_processor_config_execution_type_standard(self) -> None:
        """Test that ProcessorConfig.ExecutionType is STANDARD."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        processor_config = map_state["ItemProcessor"]["ProcessorConfig"]
        assert processor_config["ExecutionType"] == "STANDARD"

    def test_itemprocessor_has_startat(self) -> None:
        """Test that ItemProcessor has StartAt pointing to first inner step."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_processor = map_state["ItemProcessor"]
        assert "StartAt" in item_processor
        assert item_processor["StartAt"] == "Process"

    def test_itemprocessor_has_states(self) -> None:
        """Test that ItemProcessor has States dict with inner steps."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_processor = map_state["ItemProcessor"]
        assert "States" in item_processor
        assert "Process" in item_processor["States"]


class TestDistributedMapItemReader:
    """Tests for Distributed Map ItemReader validation."""

    def test_itemreader_exists(self) -> None:
        """Test that ItemReader exists in Map state."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="my-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "ItemReader" in map_state

    def test_itemreader_resource(self) -> None:
        """Test that ItemReader Resource is correct S3 Lambda ARN."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_reader = map_state["ItemReader"]
        assert item_reader["Resource"] == "arn:aws:states:::s3:getObject"

    def test_itemreader_bucket_from_config(self) -> None:
        """Test that ItemReader Bucket comes from config."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="custom-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_reader = map_state["ItemReader"]
        assert item_reader["Parameters"]["Bucket"] == "custom-bucket"

    def test_itemreader_key_from_input(self) -> None:
        """Test that ItemReader Key.$ extracts from $.input."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_reader = map_state["ItemReader"]
        assert item_reader["Parameters"]["Key.$"] == "$.input"

    def test_itemreader_reader_config(self) -> None:
        """Test that ItemReader has ReaderConfig with InputType and MaxItems."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_reader = map_state["ItemReader"]
        assert "ReaderConfig" in item_reader
        assert item_reader["ReaderConfig"]["InputType"] == "JSON"
        assert item_reader["ReaderConfig"]["MaxItems"] == 100000


class TestDistributedMapItemSelector:
    """Tests for Distributed Map ItemSelector validation."""

    def test_itemselector_exists(self) -> None:
        """Test that ItemSelector exists in Map state."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "ItemSelector" in map_state

    def test_itemselector_input_path(self) -> None:
        """Test that ItemSelector maps input from $."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_selector = map_state["ItemSelector"]
        assert item_selector["input.$"] == "$"

    def test_itemselector_flow_with_run_id(self) -> None:
        """Test that ItemSelector includes flow.run_id from Execution Context."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_selector = map_state["ItemSelector"]
        assert "flow" in item_selector
        assert item_selector["flow"]["run_id.$"] == "$$.Execution.Id"

    def test_itemselector_flow_with_params(self) -> None:
        """Test that ItemSelector includes flow.params from Execution Context."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        item_selector = map_state["ItemSelector"]
        assert "flow" in item_selector
        assert item_selector["flow"]["params.$"] == "$$.Execution.Input"


class TestDistributedMapResultWriter:
    """Tests for Distributed Map ResultWriter validation."""

    def test_resultwriter_exists(self) -> None:
        """Test that ResultWriter exists in Map state."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "ResultWriter" in map_state

    def test_resultwriter_resource(self) -> None:
        """Test that ResultWriter Resource is correct S3 putObject ARN."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        result_writer = map_state["ResultWriter"]
        assert result_writer["Resource"] == "arn:aws:states:::s3:putObject"

    def test_resultwriter_bucket_from_config(self) -> None:
        """Test that ResultWriter Bucket comes from config."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="my-custom-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        result_writer = map_state["ResultWriter"]
        assert result_writer["Parameters"]["Bucket"] == "my-custom-bucket"

    def test_resultwriter_key_contains_flow_name(self) -> None:
        """Test that ResultWriter Key contains flow name."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="my-workflow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        result_writer = map_state["ResultWriter"]
        key = result_writer["Parameters"]["Key.$"]
        assert "my-workflow" in key
        assert "runs" in key

    def test_resultwriter_body_from_input(self) -> None:
        """Test that ResultWriter Body.$ is $ (pass through results)."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        result_writer = map_state["ResultWriter"]
        assert result_writer["Parameters"]["Body.$"] == "$"


class TestDistributedMapFlowChaining:
    """Tests for Distributed Map flow chaining validation."""

    def test_initflow_exists(self) -> None:
        """Test that InitFlow Pass state exists."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        assert "InitFlow" in sm["States"]
        assert sm["States"]["InitFlow"]["Type"] == "Pass"

    def test_initflow_sets_flow_context(self) -> None:
        """Test that InitFlow sets flow context with execution ID and input."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        init_flow = sm["States"]["InitFlow"]
        assert "Parameters" in init_flow
        params = init_flow["Parameters"]
        assert "flow" in params
        assert params["flow"]["run_id.$"] == "$$.Execution.Id"
        assert params["flow"]["params.$"] == "$$.Execution.Input"

    def test_initflow_startat_points_to_source(self) -> None:
        """Test that StartAt points to InitFlow which then goes to source step."""

        @step
        def get_values() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_values().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        assert sm["StartAt"] == "InitFlow"
        init_flow = sm["States"]["InitFlow"]
        assert "Next" in init_flow
        assert init_flow["Next"] == "GetValues"

    def test_map_next_points_to_aggregate(self) -> None:
        """Test that Map state Next points to aggregate step."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "Next" in map_state
        assert map_state["Next"] == "Aggregate"

    def test_aggregate_has_end_true(self) -> None:
        """Test that aggregate step has End: True."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        agg_state = sm["States"]["Aggregate"]
        assert agg_state["End"] is True


class TestDistributedMapWithConcurrency:
    """Tests for Distributed Map with concurrency limit."""

    def test_concurrency_limit_preserved(self) -> None:
        """Test that MaxConcurrency is set when concurrency_limit specified."""

        @step
        def get_items() -> list[str]:
            return ["a", "b", "c", "d", "e"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process, concurrency_limit=5).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "MaxConcurrency" in map_state
        assert map_state["MaxConcurrency"] == 5

    def test_no_concurrency_by_default(self) -> None:
        """Test that MaxConcurrency is not set by default."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def process(item: str) -> str:
            return item.upper()

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(process).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        assert "MaxConcurrency" not in map_state


class TestDistributedMapWithInnerChaining:
    """Tests for Distributed Map with multiple inner steps."""

    def test_inner_steps_chained_correctly(self) -> None:
        """Test that multiple inner steps are chained with Next."""

        @step
        def get_items() -> list[str]:
            return ["a", "b"]

        @step
        def step_one(item: str) -> str:
            return item + "1"

        @step
        def step_two(item: str) -> str:
            return item + "2"

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(step_one).next(step_two).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        inner_states = map_state["ItemProcessor"]["States"]

        assert "StepOne" in inner_states
        assert "StepTwo" in inner_states
        assert inner_states["StepOne"]["Next"] == "StepTwo"
        assert inner_states["StepTwo"]["End"] is True

    def test_all_inner_steps_in_itemprocessor_states(self) -> None:
        """Test that all inner steps are in ItemProcessor.States."""

        @step
        def get_items() -> list[str]:
            return ["a"]

        @step
        def first(item: str) -> str:
            return item

        @step
        def second(item: str) -> str:
            return item

        @step
        def third(item: str) -> str:
            return item

        @step
        def aggregate(results: list[str]) -> str:
            return ",".join(results)

        get_items().map(first).next(second).next(third).agg(aggregate)
        graph = FlowGraph(name="test-flow", head=aggregate)
        config = LokkiConfig(artifact_bucket="test-bucket")

        sm = build_state_machine(graph, config)

        map_state = sm["States"]["GetItemsMap"]
        inner_states = map_state["ItemProcessor"]["States"]

        assert "First" in inner_states
        assert "Second" in inner_states
        assert "Third" in inner_states
