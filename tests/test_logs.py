"""Unit tests for logs command."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from lokki.logs import (
    LogsError,
    _fetch_log_events,
    _parse_datetime,
    fetch_logs,
)


class TestParseDatetime:
    """Tests for _parse_datetime function."""

    def test_parse_with_z_suffix(self) -> None:
        dt = _parse_datetime("2024-01-15T10:30:00Z")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.tzinfo is not None

    def test_parse_with_offset(self) -> None:
        dt = _parse_datetime("2024-01-15T10:30:00+05:00")
        assert dt.hour == 10
        assert dt.minute == 30

    def test_parse_invalid(self) -> None:
        with pytest.raises(LogsError, match="Invalid datetime format"):
            _parse_datetime("not-a-date")


class TestFetchLogs:
    """Tests for fetch_logs function."""

    @patch("lokki.logs.boto3.client")
    def test_fetch_logs_default_times(self, mock_boto_client) -> None:
        mock_logs = MagicMock()
        mock_boto_client.return_value = mock_logs
        mock_logs.filter_log_events.return_value = {"events": []}

        fetch_logs(
            flow_name="test-flow",
            step_names=["step1", "step2"],
        )

        assert mock_logs.filter_log_events.call_count == 2

    @patch("lokki.logs.boto3.client")
    def test_fetch_logs_with_run_id(self, mock_boto_client) -> None:
        mock_logs = MagicMock()
        mock_boto_client.return_value = mock_logs
        mock_logs.filter_log_events.return_value = {"events": []}

        fetch_logs(
            flow_name="test-flow",
            step_names=["step1"],
            run_id="test-run-123",
        )

        call_kwargs = mock_logs.filter_log_events.call_args[1]
        assert "filterPattern" in call_kwargs
        assert "test-run-123" in call_kwargs["filterPattern"]

    @patch("lokki.logs.boto3.client")
    def test_log_group_not_found(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_logs = MagicMock()
        mock_boto_client.return_value = mock_logs
        mock_logs.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "FilterLogEvents"
        )

        fetch_logs(
            flow_name="test-flow",
            step_names=["nonexistent-step"],
        )

        mock_logs.filter_log_events.assert_called_once()


class TestFetchLogEvents:
    """Tests for _fetch_log_events function."""

    @patch("lokki.logs.boto3.client")
    def test_returns_events(self, mock_boto_client) -> None:
        mock_logs = MagicMock()
        mock_boto_client.return_value = mock_logs
        mock_logs.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1705315800000,
                    "message": "Test log message",
                    "logStreamName": "test-flow-step1",
                }
            ]
        }

        events = _fetch_log_events(
            mock_logs,
            "/aws/lambda/test-flow-step1",
            datetime(2024, 1, 15, tzinfo=UTC),
            datetime(2024, 1, 16, tzinfo=UTC),
            None,
        )

        assert len(events) == 1
        assert events[0]["message"] == "Test log message"

    @patch("lokki.logs.boto3.client")
    def test_handles_missing_log_group(self, mock_boto_client) -> None:
        from botocore.exceptions import ClientError

        mock_logs = MagicMock()
        mock_boto_client.return_value = mock_logs
        mock_logs.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "FilterLogEvents"
        )

        events = _fetch_log_events(
            mock_logs,
            "/aws/lambda/nonexistent",
            datetime(2024, 1, 15, tzinfo=UTC),
            datetime(2024, 1, 16, tzinfo=UTC),
            None,
        )

        assert events == []
