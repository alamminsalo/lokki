"""Tests for runtime/batch module."""

import os
from unittest.mock import MagicMock, patch

from lokki.runtime.batch import make_batch_handler


class TestMakeBatchHandler:
    @patch.dict(os.environ, {"LOKKI_FLOW_NAME": "test-flow"})
    @patch("lokki.runtime.batch.load_config")
    @patch("lokki.runtime.batch.S3Store")
    def test_step_with_flow_params(
        self, mock_store_class: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.write.return_value = "s3://test-bucket/test"

        def my_step(input_data, name: str = "world") -> str:
            return f"hello {name}"

        handler = make_batch_handler(my_step)
        event = {
            "flow": {"run_id": "test-run", "params": {"name": "test"}},
            "input": None,
        }
        result = handler(event)

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result

    @patch.dict(os.environ, {"LOKKI_FLOW_NAME": "test-flow"})
    @patch("lokki.runtime.batch.load_config")
    @patch("lokki.runtime.batch.S3Store")
    def test_single_input_reads_from_s3(
        self, mock_store_class: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.return_value = {"key": "value"}
        mock_store.write.return_value = "s3://test-bucket/test"

        def process(input_data) -> str:
            return input_data["key"]

        handler = make_batch_handler(process)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": "s3://bucket/key",
        }
        result = handler(event)

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        mock_store.read.assert_called_once_with("s3://bucket/key")

    @patch.dict(os.environ, {"LOKKI_FLOW_NAME": "test-flow"})
    @patch("lokki.runtime.batch.load_config")
    @patch("lokki.runtime.batch.S3Store")
    def test_multiple_inputs(
        self, mock_store_class: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.read.side_effect = [{"a": 1}, {"b": 2}]
        mock_store.write.return_value = "s3://test-bucket/test"

        def process(input_data: list) -> list:
            return input_data

        handler = make_batch_handler(process)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": ["s3://bucket/key1", "s3://bucket/key2"],
        }
        result = handler(event)

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        assert mock_store.read.call_count == 2

    @patch.dict(os.environ, {"LOKKI_FLOW_NAME": "test-flow"})
    @patch("lokki.runtime.batch.load_config")
    @patch("lokki.runtime.batch.S3Store")
    def test_step_returns_list_writes_manifest(
        self, mock_store_class: MagicMock, mock_config: MagicMock
    ) -> None:
        mock_cfg = MagicMock()
        mock_cfg.artifact_bucket = "test-bucket"
        mock_cfg.flow_name = "test-flow"
        mock_config.return_value = mock_cfg

        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.write.return_value = "s3://test-bucket/test"
        mock_store.write_manifest.return_value = "s3://test-bucket/manifest"

        def get_items(input_data) -> list:
            return [{"id": 1}, {"id": 2}]

        handler = make_batch_handler(get_items)
        event = {
            "flow": {"run_id": "test-run", "params": {}},
            "input": None,
        }
        result = handler(event)

        assert result["flow"]["run_id"] == "test-run"
        assert "input" in result
        mock_store.write_manifest.assert_called_once()
