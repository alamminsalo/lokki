"""Unit tests for invoke module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from lokki._errors import InvokeError
from lokki.cli.invoke import invoke


class TestInvoke:
    """Tests for invoke function."""

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_successful_execution(self, mock_sleep, mock_get_sfn) -> None:
        """Test successful execution with wait."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "SUCCEEDED",
            "output": '{"result": "success"}',
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "SUCCEEDED"
        assert (
            result["execution_arn"]
            == "arn:aws:states:us-east-1:123:execution:test:abc123"
        )
        mock_sfn.start_execution.assert_called_once()

    @patch("lokki.cli.invoke.get_sfn_client")
    def test_execution_not_found_error(self, mock_get_sfn) -> None:
        """Test ExecutionNotFound error handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        error_response = {"Error": {"Code": "ExecutionNotFound"}}
        mock_sfn.start_execution.side_effect = ClientError(
            error_response, "StartExecution"
        )

        with pytest.raises(InvokeError, match="State machine 'test-flow' not found"):
            invoke("test-flow", {})

    @patch("lokki.cli.invoke.get_sfn_client")
    def test_state_machine_not_found_error(self, mock_get_sfn) -> None:
        """Test StateMachineNotFound error handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        error_response = {"Error": {"Code": "StateMachineNotFound"}}
        mock_sfn.start_execution.side_effect = ClientError(
            error_response, "StartExecution"
        )

        with pytest.raises(InvokeError, match="State machine 'test-flow' not found"):
            invoke("test-flow", {})

    @patch("lokki.cli.invoke.get_sfn_client")
    def test_step_functions_not_enabled_error(self, mock_get_sfn) -> None:
        """Test Step Functions not enabled error with endpoint."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        error_response = {"Error": {"Code": "InvalidExecution"}}
        mock_sfn.start_execution.side_effect = ClientError(
            error_response, "StartExecution"
        )

        with pytest.raises(InvokeError, match="Failed to start execution"):
            invoke("test-flow", {}, endpoint="http://localhost:4566")

    @patch("lokki.cli.invoke.get_sfn_client")
    def test_generic_aws_error(self, mock_get_sfn) -> None:
        """Test generic AWS error handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        error_response = {"Error": {"Code": "ThrottlingException"}}
        mock_sfn.start_execution.side_effect = ClientError(
            error_response, "StartExecution"
        )

        with pytest.raises(InvokeError, match="Failed to start execution"):
            invoke("test-flow", {})

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_failed_execution(self, mock_sleep, mock_get_sfn) -> None:
        """Test failed execution status handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "FAILED",
            "output": None,
            "cause": "Some error cause",
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "FAILED"

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_timed_out_execution(self, mock_sleep, mock_get_sfn) -> None:
        """Test timed out execution status handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "TIMED_OUT",
            "output": None,
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "TIMED_OUT"

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_aborted_execution(self, mock_sleep, mock_get_sfn) -> None:
        """Test aborted execution status handling."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "ABORTED",
            "output": None,
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "ABORTED"

    @patch("lokki.cli.invoke.get_sfn_client")
    def test_no_wait_mode(self, mock_get_sfn) -> None:
        """Test no-wait mode returns immediately."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }

        result = invoke("test-flow", {"key": "value"}, wait=False)

        assert result["status"] == "RUNNING"
        assert (
            result["execution_arn"]
            == "arn:aws:states:us-east-1:123:execution:test:abc123"
        )
        mock_sfn.describe_execution.assert_not_called()

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_successful_execution_with_string_input(
        self, mock_sleep, mock_get_sfn
    ) -> None:
        """Test execution with string input instead of dict."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "SUCCEEDED",
            "output": '{"result": "success"}',
        }

        result = invoke("test-flow", '{"key": "value"}')  # type: ignore[arg-type]

        assert result["status"] == "SUCCEEDED"
        mock_sfn.start_execution.assert_called_once()

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_execution_with_json_parse_error(self, mock_sleep, mock_get_sfn) -> None:
        """Test handling of non-JSON output."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "SUCCEEDED",
            "output": "not json output",
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "SUCCEEDED"

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_failed_execution_with_json_error_output(
        self, mock_sleep, mock_get_sfn
    ) -> None:
        """Test failed execution with JSON error output."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        mock_sfn.describe_execution.return_value = {
            "status": "FAILED",
            "output": '{"error": "something failed"}',
        }

        result = invoke("test-flow", {"key": "value"})

        assert result["status"] == "FAILED"

    @patch("lokki.cli.invoke.get_sfn_client")
    @patch("lokki.cli.invoke.time.sleep")
    def test_describe_execution_client_error(self, mock_sleep, mock_get_sfn) -> None:
        """Test ClientError during describe_execution."""
        mock_sfn = MagicMock()
        mock_get_sfn.return_value = mock_sfn
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123:execution:test:abc123"
        }
        error_response = {"Error": {"Code": "ThrottlingException"}}
        mock_sfn.describe_execution.side_effect = ClientError(
            error_response, "DescribeExecution"
        )

        with pytest.raises(InvokeError, match="Failed to describe execution"):
            invoke("test-flow", {"key": "value"})
