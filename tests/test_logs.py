"""Unit tests for logs command."""

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from lokki.cli.logs import (
    LogsError,
    _fetch_and_print_logs,
    _fetch_log_events,
    _parse_datetime,
    _print_logs,
    fetch_logs,
    logs,
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

    @patch("lokki.cli.logs.get_logs_client")
    def test_fetch_logs_default_times(self, mock_get_client) -> None:
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs
        mock_logs.filter_log_events.return_value = {"events": []}

        fetch_logs(
            flow_name="test-flow",
            step_names=["step1", "step2"],
        )

        assert mock_logs.filter_log_events.call_count >= 1

    @patch("lokki.cli.logs.get_logs_client")
    def test_fetch_logs_with_run_id(self, mock_get_client) -> None:
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs
        mock_logs.filter_log_events.return_value = {"events": []}

        fetch_logs(
            flow_name="test-flow",
            step_names=["step1"],
            run_id="test-run-123",
        )

        call_kwargs = mock_logs.filter_log_events.call_args[1]
        assert "filterPattern" in call_kwargs
        assert "test-run-123" in call_kwargs["filterPattern"]

    @patch("lokki.cli.logs.get_logs_client")
    def test_log_group_not_found(self, mock_get_client) -> None:
        from botocore.exceptions import ClientError

        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs
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

    def test_returns_events(self) -> None:
        mock_logs = MagicMock()
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

    def test_handles_missing_log_group(self) -> None:
        from botocore.exceptions import ClientError

        mock_logs = MagicMock()
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


class TestPrintLogs:
    def test_print_logs_with_events(self):
        mock_logs = MagicMock()
        mock_logs.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1705315800000,
                    "message": "Test log message 1",
                    "logStreamName": "test-flow-step1",
                },
                {
                    "timestamp": 1705315810000,
                    "message": "Test log message 2",
                    "logStreamName": "test-flow-step2",
                },
            ]
        }

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _print_logs(
                mock_logs,
                "test-flow",
                ["step1", "step2"],
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, tzinfo=UTC),
                None,
            )
            output = mock_stdout.getvalue()
            assert "Test log message 1" in output
            assert "Test log message 2" in output

    def test_print_logs_no_events(self):
        mock_logs = MagicMock()
        mock_logs.filter_log_events.return_value = {"events": []}

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _print_logs(
                mock_logs,
                "test-flow",
                ["step1"],
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, tzinfo=UTC),
                None,
            )
            output = mock_stdout.getvalue()
            assert "No log events found" in output


class TestTailLogs:
    def test_tail_log_events_basic(self):
        mock_logs = MagicMock()
        mock_logs.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1705315800000,
                    "message": "Tailed log message",
                    "logStreamName": "test-flow-step1",
                }
            ]
        }

        from lokki.cli.logs import _tail_log_events

        events = _tail_log_events(
            mock_logs,
            "/aws/lambda/test-flow-step1",
            None,
            {},
        )

        assert len(events) == 1
        assert events[0]["message"] == "Tailed log message"

    def test_tail_log_events_filters_old(self):
        mock_logs = MagicMock()
        mock_logs.filter_log_events.return_value = {
            "events": [
                {"timestamp": 1705315800000, "message": "Old message"},
                {"timestamp": 1705315900000, "message": "New message"},
            ]
        }

        from lokki.cli.logs import _tail_log_events

        events = _tail_log_events(
            mock_logs,
            "/aws/lambda/test-flow-step1",
            None,
            {"/aws/lambda/test-flow-step1": 1705315850000},
        )

        assert len(events) == 1
        assert events[0]["message"] == "New message"

    def test_tail_log_events_handles_missing_group(self):
        from botocore.exceptions import ClientError

        mock_logs = MagicMock()
        mock_logs.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "FilterLogEvents"
        )

        from lokki.cli.logs import _tail_log_events

        events = _tail_log_events(
            mock_logs,
            "/aws/lambda/nonexistent",
            None,
            {},
        )

        assert events == []


class TestFetchAndPrintLogs:
    @patch("lokki.cli.logs._tail_logs")
    def test_fetch_and_print_logs_tail(self, mock_tail):
        mock_logs = MagicMock()
        mock_tail.side_effect = SystemExit

        with pytest.raises(SystemExit):
            _fetch_and_print_logs(
                mock_logs,
                "test-flow",
                ["step1"],
                datetime(2024, 1, 15, tzinfo=UTC),
                datetime(2024, 1, 16, tzinfo=UTC),
                None,
                tail=True,
            )

        mock_tail.assert_called_once()


class TestLogsFunction:
    @patch("lokki.cli.logs.fetch_logs")
    def test_logs_success(self, mock_fetch):
        logs(
            flow_name="test-flow",
            step_names=["step1"],
            start_time="2024-01-15T10:00:00Z",
            end_time="2024-01-15T11:00:00Z",
        )

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["start_time"] is not None
        assert mock_fetch.call_args.kwargs["end_time"] is not None

    @patch("lokki.cli.logs.fetch_logs")
    def test_logs_no_times(self, mock_fetch):
        logs(
            flow_name="test-flow",
            step_names=["step1"],
        )

        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["start_time"] is None
        assert mock_fetch.call_args.kwargs["end_time"] is None

    @patch("lokki.cli.logs.fetch_logs")
    def test_logs_aws_error(self, mock_fetch):
        mock_fetch.side_effect = LogsError("AWS error")

        with pytest.raises(SystemExit) as exc_info:
            logs(
                flow_name="test-flow",
                step_names=["step1"],
            )

        assert exc_info.value.code == 1

    @patch("lokki.cli.logs.fetch_logs")
    def test_logs_cloudwatch_not_enabled(self, mock_fetch):
        mock_fetch.side_effect = LogsError(
            "CloudWatch Logs is not enabled in LocalStack"
        )

        with pytest.raises(SystemExit) as exc_info:
            logs(
                flow_name="test-flow",
                step_names=["step1"],
                endpoint="http://localhost:4566",
            )

        assert exc_info.value.code == 1

    @patch("lokki.cli.logs.fetch_logs")
    def test_logs_keyboard_interrupt(self, mock_fetch):
        mock_fetch.side_effect = KeyboardInterrupt

        with pytest.raises(SystemExit) as exc_info:
            logs(
                flow_name="test-flow",
                step_names=["step1"],
            )

        assert exc_info.value.code == 0
