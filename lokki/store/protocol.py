"""DataStore protocol definition."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class DataStore(Protocol):
    """Protocol defining the common interface for data storage backends.

    Both LocalStore and S3Store implement this interface, allowing the runner
    and runtime handlers to work with either storage backend interchangeably.
    """

    def write(
        self,
        flow_name: str | None = None,
        run_id: str | None = None,
        step_name: str | None = None,
        obj: Any = None,
        *,
        bucket: str | None = None,
        key: str | None = None,
    ) -> str:
        """Write an object to storage and return the storage location."""
        ...

    def read(self, location: str) -> Any:
        """Read an object from storage."""
        ...

    def write_manifest(
        self,
        flow_name: str | None = None,
        run_id: str | None = None,
        step_name: str | None = None,
        items: "Sequence[dict[str, Any]] | None" = None,
        *,
        bucket: str | None = None,
        key: str | None = None,
    ) -> str:
        """Write a map manifest listing items for parallel processing."""
        ...
