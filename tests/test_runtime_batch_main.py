"""Tests for runtime/batch_main module."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


class TestBatchMain:
    def test_main_missing_step_name(self, monkeypatch):
        """Test error when LOKKI_STEP_NAME is not set."""
        monkeypatch.delenv("LOKKI_STEP_NAME", raising=False)
        monkeypatch.setenv("LOKKI_MODULE_NAME", "test_module")

        from lokki.runtime import batch_main

        with pytest.raises(
            ValueError, match="LOKKI_STEP_NAME environment variable not set"
        ):
            batch_main.main()

    def test_main_missing_module_name(self, monkeypatch):
        """Test error when LOKKI_MODULE_NAME is not set."""
        monkeypatch.setenv("LOKKI_STEP_NAME", "test_step")
        monkeypatch.delenv("LOKKI_MODULE_NAME", raising=False)

        from lokki.runtime import batch_main

        with pytest.raises(
            ValueError, match="LOKKI_MODULE_NAME environment variable not set"
        ):
            batch_main.main()

    def test_main_step_not_found(self, monkeypatch):
        """Test error when step function not found in module."""
        monkeypatch.setenv("LOKKI_STEP_NAME", "nonexistent_step")
        monkeypatch.setenv("LOKKI_MODULE_NAME", "nonexistent_module")

        mock_module = MagicMock()
        mock_module.__dict__ = {}
        sys.modules["nonexistent_module"] = mock_module

        from lokki.runtime import batch_main

        try:
            with pytest.raises(ValueError, match="Step function.*not found"):
                batch_main.main()
        finally:
            if "nonexistent_module" in sys.modules:
                del sys.modules["nonexistent_module"]

    def test_main_with_input_data_json(self, monkeypatch):
        """Test main with JSON input data."""
        monkeypatch.setenv("LOKKI_STEP_NAME", "test_step")
        monkeypatch.setenv("LOKKI_MODULE_NAME", "test_module")
        monkeypatch.setenv("LOKKI_INPUT_DATA", '{"key": "value"}')

        mock_step = MagicMock(return_value="result")
        mock_module = MagicMock()
        mock_module.test_step = mock_step
        sys.modules["test_module"] = mock_module

        mock_handler_instance = MagicMock(
            return_value={"result_url": "s3://bucket/result", "run_id": "run-123"}
        )

        with patch(
            "lokki.runtime.batch.make_batch_handler",
            return_value=mock_handler_instance,
            create=True,
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                from lokki.runtime.batch_main import main

                main()
                output = mock_stdout.getvalue()
                assert "result_url" in output

        if "test_module" in sys.modules:
            del sys.modules["test_module"]

    def test_main_with_input_data_string(self, monkeypatch):
        """Test main with string input data (not JSON)."""
        monkeypatch.setenv("LOKKI_STEP_NAME", "test_step")
        monkeypatch.setenv("LOKKI_MODULE_NAME", "test_module")
        monkeypatch.setenv("LOKKI_INPUT_DATA", "plain_string_data")

        mock_step = MagicMock(return_value="result")
        mock_module = MagicMock()
        mock_module.test_step = mock_step
        sys.modules["test_module"] = mock_module

        mock_handler_instance = MagicMock(
            return_value={"result_url": "s3://bucket/result", "run_id": "run-123"}
        )

        with patch(
            "lokki.runtime.batch.make_batch_handler",
            return_value=mock_handler_instance,
            create=True,
        ):
            from lokki.runtime.batch_main import main

            main()

        if "test_module" in sys.modules:
            del sys.modules["test_module"]

    def test_main_extracts_fn_from_wrapper(self, monkeypatch):
        """Test main extracts fn attribute from wrapped step function."""
        monkeypatch.setenv("LOKKI_STEP_NAME", "wrapped_step")
        monkeypatch.setenv("LOKKI_MODULE_NAME", "test_module")
        monkeypatch.delenv("LOKKI_INPUT_DATA", raising=False)

        actual_fn = MagicMock(return_value="actual_result")
        wrapped_step = MagicMock()
        wrapped_step.fn = actual_fn

        mock_module = MagicMock()
        mock_module.wrapped_step = wrapped_step
        sys.modules["test_module"] = mock_module

        captured_fn = []

        def capture_handler(fn):
            captured_fn.append(fn)
            return lambda event: {
                "result_url": "s3://bucket/result",
                "run_id": "run-123",
            }

        with patch(
            "lokki.runtime.batch.make_batch_handler",
            side_effect=capture_handler,
            create=True,
        ):
            from lokki.runtime.batch_main import main

            main()

            assert len(captured_fn) == 1
            assert captured_fn[0] == actual_fn

        if "test_module" in sys.modules:
            del sys.modules["test_module"]
