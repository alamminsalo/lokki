"""Unit tests for lokki logging module."""

import json
import logging
from io import StringIO

from lokki.logging import (
    HumanFormatter,
    JsonFormatter,
    LoggingConfig,
    MapProgressLogger,
    StepLogger,
    get_logger,
    get_logging_config,
)


class TestLoggingConfig:
    def test_default_values(self) -> None:
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.format == "human"
        assert config.progress_interval == 10
        assert config.show_timestamps is True

    def test_custom_values(self) -> None:
        config = LoggingConfig(
            level="DEBUG", format="json", progress_interval=5, show_timestamps=False
        )
        assert config.level == "DEBUG"
        assert config.format == "json"
        assert config.progress_interval == 5
        assert config.show_timestamps is False


class TestGetLoggingConfig:
    def test_defaults(self) -> None:
        config = get_logging_config()
        assert config.level == "INFO"
        assert config.format == "human"

    def test_overrides(self) -> None:
        config = get_logging_config(
            level="DEBUG", format="json", progress_interval=20, show_timestamps=False
        )
        assert config.level == "DEBUG"
        assert config.format == "json"
        assert config.progress_interval == 20
        assert config.show_timestamps is False


class TestHumanFormatter:
    def test_format_with_timestamp(self) -> None:
        config = LoggingConfig(level="INFO", show_timestamps=True)
        formatter = HumanFormatter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[INFO]" in output
        assert "Test message" in output

    def test_format_without_timestamp(self) -> None:
        config = LoggingConfig(level="INFO", show_timestamps=False)
        formatter = HumanFormatter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[INFO]" in output
        assert "Test message" in output


class TestJsonFormatter:
    def test_format_basic(self) -> None:
        config = LoggingConfig(level="INFO")
        formatter = JsonFormatter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert "ts" in data
        assert data["event"] == "log"

    def test_format_with_extra_fields(self) -> None:
        config = LoggingConfig(level="INFO")
        formatter = JsonFormatter(config)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.step = "my_step"
        record.duration = 1.5
        record.status = "success"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["step"] == "my_step"
        assert data["duration"] == 1.5
        assert data["status"] == "success"


class TestStepLogger:
    def test_start_logs_info(self) -> None:
        config = LoggingConfig(level="INFO")
        logger = get_logger("test", config)

        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(HumanFormatter(config))
        logger.handlers = [handler]

        step_logger = StepLogger("my_step", logger)
        step_logger.start()

        output = handler.stream.getvalue()
        assert "Step 'my_step' started" in output


class TestMapProgressLogger:
    def test_progress_updates(self) -> None:
        config = LoggingConfig(level="INFO", progress_interval=1)
        logger = get_logger("test", config)

        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(HumanFormatter(config))
        logger.handlers = [handler]

        map_logger = MapProgressLogger("my_map", 10, logger, config)
        map_logger.start()

        for _ in range(10):
            map_logger.update("completed")

        output = handler.stream.getvalue()
        assert "Map 'my_map' started (10 items)" in output
        assert "100%" in output

    def test_complete(self) -> None:
        config = LoggingConfig(level="INFO")
        logger = get_logger("test", config)

        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(HumanFormatter(config))
        logger.handlers = [handler]

        map_logger = MapProgressLogger("my_map", 5, logger, config)
        map_logger.start()

        for _ in range(5):
            map_logger.update("completed")

        map_logger.complete()

        output = handler.stream.getvalue()
        assert "Map 'my_map' completed" in output


class TestGetLogger:
    def test_creates_logger(self) -> None:
        config = LoggingConfig(level="INFO")
        logger = get_logger("test_logger", config)

        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1

    def test_json_format(self) -> None:
        config = LoggingConfig(level="INFO", format="json")
        logger = get_logger("test_json", config)

        handler = logger.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)
