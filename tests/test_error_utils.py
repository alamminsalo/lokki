"""Unit tests for CLI error utilities."""

import logging
from unittest.mock import patch

import pytest

from lokki.cli import error_utils
from lokki.config import LokkiConfig
from lokki.decorators import step
from lokki.graph import FlowGraph


class TestPrintError:
    """Tests for print_error function."""

    def test_print_error_calls_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that print_error logs the message."""
        with caplog.at_level(logging.ERROR):
            error_utils.print_error("test error message")
        assert "test error message" in caplog.text
        assert caplog.records[0].levelno == logging.ERROR


class TestExitOnError:
    """Tests for exit_on_error function."""

    def test_exit_on_error_logs_and_exits(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that exit_on_error logs and calls sys.exit."""
        with caplog.at_level(logging.ERROR):
            with patch("sys.exit") as mock_exit:
                error_utils.exit_on_error("exit message", code=42)
                assert "exit message" in caplog.text
                mock_exit.assert_called_once_with(42)

    def test_exit_on_error_default_code(self) -> None:
        """Test that exit_on_error uses default code 1."""
        with patch("sys.exit") as mock_exit:
            error_utils.exit_on_error("message")
            mock_exit.assert_called_once_with(1)


class TestCliContext:
    """Tests for cli_context context manager."""

    def test_cli_context_require_bucket_true(self) -> None:
        """Test cli_context with require_bucket=True and empty bucket."""
        from lokki.config import LokkiConfig
        from lokki.graph import FlowGraph

        @step
        def step1():
            return [1]

        graph = FlowGraph(name="test", head=step1)
        config = LokkiConfig()
        config.artifact_bucket = ""

        with patch("lokki.config.load_config", return_value=config):
            with patch("sys.exit") as mock_exit:
                with error_utils.cli_context(lambda: graph, require_bucket=True) as (
                    g,
                    c,
                ):
                    pass
                mock_exit.assert_called_once_with(1)

    def test_cli_context_require_bucket_false(self) -> None:
        """Test cli_context with require_bucket=False skips bucket check."""
        from lokki.config import LokkiConfig
        from lokki.graph import FlowGraph
        from lokki.decorators import step

        @step
        def step1():
            return [1]

        graph = FlowGraph(name="test", head=step1)
        config = LokkiConfig()
        config.artifact_bucket = ""

        with patch("lokki.config.load_config", return_value=config):
            with error_utils.cli_context(lambda: graph, require_bucket=False) as (g, c):
                assert g is graph
                assert c is config
