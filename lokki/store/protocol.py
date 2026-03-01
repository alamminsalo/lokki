"""TransientStore protocol definition."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class TransientStore(Protocol):
    """Protocol defining the common interface for transient data storage backends.

    Both LocalStore and S3Store implement this interface, allowing the runner
    and runtime handlers to work with either storage backend interchangeably.

    S3Store reads bucket from LOKKI_ARTIFACT_BUCKET environment variable internally.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        """Initialize store.

        For S3Store: reads LOKKI_ARTIFACT_BUCKET from env internally.
        For LocalStore: uses base_dir or creates temp directory.
        """
        ...

    def write(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        obj: Any,
    ) -> str:
        """Write an object to storage and return the storage location URL."""
        ...

    def read(self, location: str) -> Any:
        """Read an object from storage (path or s3:// URL)."""
        ...

    def write_manifest(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        items: "Sequence[Any]",
    ) -> str:
        """Write a map manifest listing items for parallel processing."""
        ...

    def cleanup(self) -> None:
        """Clean up resources (NOP for S3, removes temp dir for LocalStore)."""
        ...
