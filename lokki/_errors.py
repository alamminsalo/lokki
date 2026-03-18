"""Custom exception hierarchy for lokki."""

__all__ = [
    "LokkiError",
    "GraphValidationError",
    "ConfigurationError",
    "BuildError",
    "StoreError",
    "DeployError",
    "DockerNotAvailableError",
    "ShowError",
    "LogsError",
    "DestroyError",
    "InvokeError",
]


class LokkiError(Exception):
    """Base exception for lokki.

    All custom exceptions in lokki inherit from this base class.
    """


class GraphValidationError(LokkiError):
    """Raised when flow graph validation fails.

    This exception is raised when the flow graph structure is invalid,
    such as cycles, unreachable steps, or duplicate step names.

    Attributes:
        message: Error description
        details: Additional validation failure details
    """

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        self.message = message
        self.details = details or []
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}\nDetails:\n" + "\n".join(
                f"  - {d}" for d in self.details
            )
        return self.message


class ConfigurationError(LokkiError):
    """Raised when configuration is invalid.

    This exception is raised when configuration values are missing,
    invalid, or inconsistent with deployment requirements.

    Attributes:
        message: Error description
        field: Configuration field name (optional)
        value: Invalid value (optional)
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: str | None = None,
    ) -> None:
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.field:
            return f"{self.message} (field: {self.field})"
        return self.message


class BuildError(LokkiError):
    """Raised when build process fails.

    This exception is raised when the build process encounters errors,
    such as missing dependencies, Docker failures, or artifact validation.

    Attributes:
        message: Error description
        step: Build step that failed (optional)
        underlying: Original exception (optional)
    """

    def __init__(
        self,
        message: str,
        step: str | None = None,
        underlying: Exception | None = None,
    ) -> None:
        self.message = message
        self.step = step
        self.underlying = underlying
        super().__init__(self.message)
        if underlying is not None:
            self.__cause__ = underlying

    def __str__(self) -> str:
        if self.step:
            return f"{self.message} (step: {self.step})"
        return self.message


class StoreError(LokkiError):
    """Raised when storage operation fails.

    This exception is raised when S3, local, or memory store operations
    encounter errors such as access denied, missing bucket, or I/O errors.

    Attributes:
        message: Error description
        operation: Storage operation (read, write, etc.)
        location: Storage location (optional)
        underlying: Original exception (optional)
    """

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        location: str | None = None,
        underlying: Exception | None = None,
    ) -> None:
        self.message = message
        self.operation = operation
        self.location = location
        self.underlying = underlying
        super().__init__(self.message)
        if underlying is not None:
            self.__cause__ = underlying

    def __str__(self) -> str:
        if self.location:
            return f"{self.message} (location: {self.location})"
        return self.message


class DeployError(LokkiError):
    """Raised when deployment fails.

    This exception is raised when deploying to AWS encounters errors,
    such as CloudFormation failures, ECR push errors, or IAM issues.
    """


class DockerNotAvailableError(DeployError):
    """Raised when Docker is not available."""


class ShowError(LokkiError):
    """Error during show operation."""


class LogsError(LokkiError):
    """Error during logs operation."""


class DestroyError(LokkiError):
    """Error during destroy operation."""


class InvokeError(LokkiError):
    """Error during invoke operation."""
