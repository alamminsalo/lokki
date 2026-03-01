"""Unit tests for lokki runtime handler module."""

import os
from unittest.mock import MagicMock, patch

from lokki.runtime.handler import make_handler


class TestMakeHandler:
    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_first_step_with_flow_params(self, mock_store_class: MagicMock) -> None:
        """Test first step receives only flow params as kwargs (no input_data)."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.write.return_value = "s3://test-bucket/test"

        def my_step(param1: str = "default") -> str:
            return f"hello {param1}"

        handler = make_handler(my_step)
        event = {
            "flow": {"run_id": "test-run", "params": {"param1": "test"}},
            "input": None,
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_single_input_reads_from_s3(self, mock_store_class: MagicMock) -> None:
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.return_value = {"key": "value"}
        mock_store.write.return_value = "s3://test-bucket/test"

        def process(input_data) -> str:
            return input_data["key"]

        handler = make_handler(process)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": "s3://bucket/key",
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        mock_store.read.assert_called_once_with("s3://bucket/key")

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_multiple_inputs_read_from_s3(self, mock_store_class: MagicMock) -> None:
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.side_effect = [{"a": 1}, {"b": 2}]
        mock_store.write.return_value = "s3://test-bucket/test"

        def process(input_data: list) -> list:
            return input_data

        handler = make_handler(process)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": ["s3://bucket/key1", "s3://bucket/key2"],
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        assert mock_store.read.call_count == 2

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_step_returns_list_writes_manifest(
        self, mock_store_class: MagicMock
    ) -> None:
        """Test first step that returns a list writes manifest."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.write.return_value = "s3://test-bucket/test"
        mock_store.write_manifest.return_value = "test-bucket/key/manifest.json"

        def get_items() -> list:
            return [{"id": 1}, {"id": 2}]

        handler = make_handler(get_items)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": None,
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        mock_store.write_manifest.assert_called_once()

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_flow_params_merged_into_dict_input(
        self, mock_store_class: MagicMock
    ) -> None:
        """Test that flow.params are merged into input when input is a dict."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.return_value = {"value": 5}
        mock_store.write.return_value = "s3://test-bucket/test"

        def process_item(item: dict, multiplier: int) -> dict:
            return {"result": item["value"] * multiplier}

        handler = make_handler(process_item)
        event = {
            "flow": {"run_id": "test-run", "params": {"multiplier": 2}},
            "input": "s3://bucket/key",
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        mock_store.write.assert_called_once()
        call_args = mock_store.write.call_args
        written_data = call_args[0][3]
        assert written_data == {"result": 10}

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_flow_params_passed_as_kwargs_to_non_dict_input(
        self, mock_store_class: MagicMock
    ) -> None:
        """Test that flow.params are passed as kwargs when input is not a dict."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.return_value = "hello"
        mock_store.write.return_value = "s3://test-bucket/test"

        def process_item(item: str, multiplier: int) -> str:
            return f"{item}x{multiplier}"

        handler = make_handler(process_item)
        event = {
            "flow": {"run_id": "test-run", "params": {"multiplier": 3}},
            "input": "s3://bucket/key",
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        mock_store.write.assert_called_once()
        call_args = mock_store.write.call_args
        written_data = call_args[0][3]
        assert written_data == "hellox3"

    @patch.dict(
        os.environ,
        {"LOKKI_FLOW_NAME": "test-flow", "LOKKI_ARTIFACT_BUCKET": "test-bucket"},
    )
    @patch("lokki.runtime.handler.S3Store")
    def test_flow_params_not_passed_when_empty(
        self, mock_store_class: MagicMock
    ) -> None:
        """Test that flow.params are not passed when empty."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.return_value = "hello"
        mock_store.write.return_value = "s3://test-bucket/test"

        def simple_step(input_data: str) -> str:
            return input_data.upper()

        handler = make_handler(simple_step)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": "s3://bucket/key",
        }
        result = handler(event, MagicMock())

        assert result["flow"]["run_id"] == "test-run"
        mock_store.write.assert_called_once()
        call_args = mock_store.write.call_args
        written_data = call_args[0][3]
        assert written_data == "HELLO"
