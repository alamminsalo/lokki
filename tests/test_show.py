"""Unit tests for show command."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from lokki.show import (
    ShowError,
    _format_execution,
    print_executions,
    show_executions,
)


class TestFormatExecution:
    """Tests for _format_execution function."""

    def test_succeeded_execution(self) -> None:
        execution = {
            "name": "test-run-123",
            "status": "SUCCEEDED",
            "startDate": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            "stopDate": datetime(2024, 1, 15, 10, 2, 30, tzinfo=UTC),
        }
        result = _format_execution(execution)
        assert result["run_id"] == "test-run-123"
        assert result["status"] == "SUCCEEDED"
        assert result["duration"] == "2m 30s"

    def test_failed_execution(self) -> None:
        execution = {
            "name": "test-run-456",
            "status": "FAILED",
            "startDate": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            "stopDate": datetime(2024, 1, 15, 10, 1, 0, tzinfo=UTC),
        }
        result = _format_execution(execution)
        assert result["status"] == "FAILED"
        assert result["duration"] == "1m 0s"

    def test_running_execution(self) -> None:
        execution = {
            "name": "test-run-789",
            "status": "RUNNING",
            "startDate": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        }
        result = _format_execution(execution)
        assert result["status"] == "RUNNING"
        assert result["duration"] == "-"
        assert result["stop_time"] == "-"

    def test_short_duration(self) -> None:
        execution = {
            "name": "test-run",
            "status": "SUCCEEDED",
            "startDate": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            "stopDate": datetime(2024, 1, 15, 10, 0, 45, tzinfo=UTC),
        }
        result = _format_execution(execution)
        assert result["duration"] == "45.0s"


class TestShowExecutions:
    """Tests for show_executions function."""

    @patch("lokki.show.boto3.client")
    def test_list_executions(self, mock_boto_client) -> None:
        mock_sf = MagicMock()
        mock_boto_client.return_value = mock_sf
        mock_sf.list_executions.return_value = {
            "executions": [
                {
                    "name": "run-1",
                    "status": "SUCCEEDED",
                    "startDate": datetime(2024, 1, 15, tzinfo=UTC),
                    "stopDate": datetime(2024, 1, 15, tzinfo=UTC),
                },
                {
                    "name": "run-2",
                    "status": "FAILED",
                    "startDate": datetime(2024, 1, 14, tzinfo=UTC),
                    "stopDate": datetime(2024, 1, 14, tzinfo=UTC),
                },
            ]
        }

        result = show_executions(flow_name="test-flow", max_count=10)

        assert len(result) == 2
        assert result[0]["run_id"] == "run-1"
        assert result[0]["status"] == "SUCCEEDED"
        assert result[1]["run_id"] == "run-2"
        assert result[1]["status"] == "FAILED"
        mock_sf.list_executions.assert_called_once()

    @patch("lokki.show.boto3.client")
    def test_describe_execution(self, mock_boto_client) -> None:
        mock_sf = MagicMock()
        mock_boto_client.return_value = mock_sf
        mock_sf.describe_execution.return_value = {
            "name": "specific-run",
            "status": "SUCCEEDED",
            "startDate": datetime(2024, 1, 15, tzinfo=UTC),
            "stopDate": datetime(2024, 1, 15, tzinfo=UTC),
        }

        result = show_executions(flow_name="test-flow", run_id="specific-run")

        assert len(result) == 1
        assert result[0]["run_id"] == "specific-run"
        mock_sf.describe_execution.assert_called_once()

    @patch("lokki.show.boto3.client")
    def test_execution_not_found(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_sf = MagicMock()
        mock_boto_client.return_value = mock_sf
        mock_sf.describe_execution.side_effect = ClientError(
            {"Error": {"Code": "ExecutionNotFound"}}, "DescribeExecution"
        )

        with pytest.raises(ShowError, match="Execution"):
            show_executions(flow_name="test-flow", run_id="nonexistent")

    @patch("lokki.show.boto3.client")
    def test_state_machine_not_found(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_sf = MagicMock()
        mock_boto_client.return_value = mock_sf
        mock_sf.list_executions.side_effect = ClientError(
            {"Error": {"Code": "StateMachineNotFound"}}, "ListExecutions"
        )

        with pytest.raises(ShowError, match="State machine"):
            show_executions(flow_name="test-flow")


class TestPrintExecutions:
    """Tests for print_executions function."""

    def test_empty_executions(self, capsys) -> None:
        print_executions([])
        captured = capsys.readouterr()
        assert "No executions found" in captured.out

    def test_single_execution(self, capsys) -> None:
        executions = [
            {
                "run_id": "test-run",
                "status": "SUCCEEDED",
                "start_time": "2024-01-15T10:00:00+00:00",
                "duration": "1m 30s",
            }
        ]
        print_executions(executions)
        captured = capsys.readouterr()
        assert "test-run" in captured.out
        assert "SUCCEEDED" in captured.out
