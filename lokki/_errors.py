"""Centralized error classes for lokki."""


class DeployError(Exception):
    """Raised when deployment fails."""

    pass


class DockerNotAvailableError(DeployError):
    """Raised when Docker is not available."""

    pass


class ShowError(Exception):
    """Error during show operation."""

    pass


class LogsError(Exception):
    """Error during logs operation."""

    pass


class DestroyError(Exception):
    """Error during destroy operation."""

    pass
