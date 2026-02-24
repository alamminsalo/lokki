"""Tests for runtime/batch module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lokki.runtime.batch import make_batch_handler


class TestMakeBatchHandler:
    def test_handler_with_input_url(self):
        step_fn = MagicMock(return_value={"result": "success"})
        step_fn.__name__ = "test_step"

        mock_store = MagicMock()
        mock_store.read.return_value = {"input": "data"}
        mock_store.write.return_value = "s3://bucket/path/to/result"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    handler = make_batch_handler(step_fn)

                    event = {
                        "input_url": "s3://bucket/input.json",
                        "run_id": "test-run-123",
                    }
                    result = handler(event)

                    mock_store.read.assert_called_once_with("s3://bucket/input.json")
                    step_fn.assert_called_once_with({"input": "data"})
                    assert "result_url" in result
                    assert result["run_id"] == "test-run-123"

    def test_handler_with_result_url(self):
        step_fn = MagicMock(return_value={"result": "processed"})
        step_fn.__name__ = "result_step"

        mock_store = MagicMock()
        mock_store.read.return_value = {"previous": "data"}
        mock_store.write.return_value = "s3://bucket/output.json"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    handler = make_batch_handler(step_fn)

                    event = {
                        "result_url": "s3://bucket/previous.json",
                        "run_id": "run-456",
                    }
                    result = handler(event)

                    mock_store.read.assert_called_once_with("s3://bucket/previous.json")
                    assert "result_url" in result

    def test_handler_with_result_urls(self):
        step_fn = MagicMock(return_value=["item1", "item2", "item3"])
        step_fn.__name__ = "map_step"

        mock_store = MagicMock()
        mock_store.read.side_effect = [{"data": 1}, {"data": 2}, {"data": 3}]
        mock_store.write.return_value = "s3://bucket/manifest.json"
        mock_store.write_manifest.return_value = "s3://bucket/manifest.json"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    handler = make_batch_handler(step_fn)

                    event = {
                        "result_urls": [
                            "s3://bucket/input/0.json",
                            "s3://bucket/input/1.json",
                            "s3://bucket/input/2.json",
                        ],
                        "run_id": "run-789",
                    }
                    result = handler(event)

                    assert mock_store.read.call_count == 3
                    assert "map_manifest_key" in result

    def test_handler_with_direct_kwargs(self):
        step_fn = MagicMock(return_value="direct_result")
        step_fn.__name__ = "direct_step"

        def create_signature(*params):
            from inspect import Parameter, Signature

            sig = Signature()
            return sig.replace(
                parameters=[
                    Parameter(p, Parameter.POSITIONAL_OR_KEYWORD) for p in params
                ]
            )

        step_fn.__signature__ = create_signature("param1", "param2")

        mock_store = MagicMock()
        mock_store.write.return_value = "s3://bucket/result.json"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    handler = make_batch_handler(step_fn)

                    event = {
                        "param1": "value1",
                        "param2": "value2",
                        "run_id": "run-000",
                    }
                    handler(event)

                    step_fn.assert_called_once_with(param1="value1", param2="value2")

    def test_handler_error_handling(self):
        step_fn = MagicMock(side_effect=ValueError("Step failed"))
        step_fn.__name__ = "failing_step"

        mock_store = MagicMock()
        mock_store.write.return_value = "s3://bucket/result.json"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    handler = make_batch_handler(step_fn)

                    event = {
                        "run_id": "run-error",
                        "input_url": "s3://bucket/input.json",
                    }

                    with pytest.raises(ValueError, match="Step failed"):
                        handler(event)

    def test_handler_with_retry_config(self):
        step_fn = MagicMock(return_value="result")
        step_fn.__name__ = "retry_step"

        mock_store = MagicMock()
        mock_store.write.return_value = "s3://bucket/result.json"

        with patch("lokki.runtime.batch.load_config") as mock_load_config:
            mock_config = MagicMock()
            mock_config.flow_name = "test-flow"
            mock_config.artifact_bucket = "test-bucket"
            mock_load_config.return_value = mock_config

            with patch("lokki.runtime.batch.S3Store", return_value=mock_store):
                with patch("lokki.runtime.batch.get_logger") as mock_logger:
                    mock_logger.return_value = MagicMock()

                    retry_config = MagicMock()
                    handler = make_batch_handler(step_fn, retry_config=retry_config)

                    event = {"run_id": "run-retry"}
                    result = handler(event)

                    assert "result_url" in result
