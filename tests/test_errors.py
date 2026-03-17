"""Tests for custom exception hierarchy and error handling."""

import pytest

from lokki._errors import (
    BuildError,
    ConfigurationError,
    GraphValidationError,
    LokkiError,
    StoreError,
)


class TestLokkiError:
    """Test base LokkiError exception."""

    def test_base_exception_creation(self) -> None:
        """Test creating base LokkiError."""
        err = LokkiError("test message")
        assert str(err) == "test message"
        assert isinstance(err, Exception)

    def test_base_exception_inheritance(self) -> None:
        """Test that custom exceptions inherit from LokkiError."""
        assert issubclass(GraphValidationError, LokkiError)
        assert issubclass(ConfigurationError, LokkiError)
        assert issubclass(BuildError, LokkiError)
        assert issubclass(StoreError, LokkiError)


class TestGraphValidationError:
    """Test GraphValidationError exception."""

    def test_simple_message(self) -> None:
        """Test with simple message."""
        err = GraphValidationError("Graph has cycles")
        assert str(err) == "Graph has cycles"

    def test_with_details(self) -> None:
        """Test with detailed error information."""
        err = GraphValidationError(
            "Graph validation failed",
            details=["Cycle detected: A -> B -> C -> A", "Duplicate step: 'process'"],
        )
        assert "Graph validation failed" in str(err)
        assert "Cycle detected: A -> B -> C -> A" in str(err)
        assert "Duplicate step: 'process'" in str(err)

    def test_empty_details(self) -> None:
        """Test with empty details list."""
        err = GraphValidationError("Validation failed", details=[])
        assert str(err) == "Validation failed"


class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_simple_message(self) -> None:
        """Test with simple message."""
        err = ConfigurationError("Missing required field")
        assert str(err) == "Missing required field"

    def test_with_field(self) -> None:
        """Test with field name."""
        err = ConfigurationError("Field is required", field="artifact_bucket")
        assert str(err) == "Field is required (field: artifact_bucket)"

    def test_with_field_and_value(self) -> None:
        """Test with field name and value."""
        err = ConfigurationError("Invalid value", field="timeout", value="9000")
        assert str(err) == "Invalid value (field: timeout)"


class TestBuildError:
    """Test BuildError exception."""

    def test_simple_message(self) -> None:
        """Test with simple message."""
        err = BuildError("Build failed")
        assert str(err) == "Build failed"

    def test_with_step(self) -> None:
        """Test with step name."""
        err = BuildError("Docker build failed", step="lambda_package")
        assert str(err) == "Docker build failed (step: lambda_package)"

    def test_with_underlying(self) -> None:
        """Test with underlying exception."""
        underlying = RuntimeError("Original error")
        err = BuildError("Build failed", underlying=underlying)
        assert err.underlying is underlying
        assert err.__cause__ is underlying


class TestStoreError:
    """Test StoreError exception."""

    def test_simple_message(self) -> None:
        """Test with simple message."""
        err = StoreError("S3 access denied")
        assert str(err) == "S3 access denied"

    def test_with_operation(self) -> None:
        """Test with operation name."""
        err = StoreError("Permission denied", operation="write")
        assert str(err) == "Permission denied"

    def test_with_location(self) -> None:
        """Test with storage location."""
        err = StoreError("Not found", location="s3://bucket/key")
        assert str(err) == "Not found (location: s3://bucket/key)"

    def test_with_underlying(self) -> None:
        """Test with underlying exception."""
        underlying = PermissionError("Access denied")
        err = StoreError("S3 error", underlying=underlying)
        assert err.underlying is underlying
        assert err.__cause__ is underlying


class TestErrorHierarchy:
    """Test exception hierarchy and catching."""

    def test_catch_all_lokki_errors(self) -> None:
        """Test catching all Lokki errors."""
        errors = [
            GraphValidationError("test"),
            ConfigurationError("test"),
            BuildError("test"),
            StoreError("test"),
        ]

        for err in errors:
            with pytest.raises(LokkiError):
                raise err

    def test_catch_specific_error(self) -> None:
        """Test catching specific error types."""
        with pytest.raises(GraphValidationError):
            raise GraphValidationError("test")

        with pytest.raises(ConfigurationError):
            raise ConfigurationError("test")

        with pytest.raises(BuildError):
            raise BuildError("test")

        with pytest.raises(StoreError):
            raise StoreError("test")
