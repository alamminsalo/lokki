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
        For MemoryStore: in-memory storage.
        """
        ...

    def write(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        obj: Any,
        input_hash: str | None = None,
    ) -> str:
        """Write an object to storage and return the storage location URL.

        Args:
            input_hash: Optional hash of input data. If provided, stored as S3 tag
                for cache validation.
        """
        ...

    def get_input_hash(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> str | None:
        """Get the stored input hash for a step's output.

        Returns the input_hash stored as S3 tag, or None if not set.
        Used for cache validation.
        """
        ...

    def read(self, location: str) -> Any:
        """Read an object from storage (path or s3:// URL)."""
        ...

    def exists(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> bool:
        """Check if output already exists for this step in this run.

        Used for caching within a single run execution.
        """
        ...

    def read_cached(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> Any:
        """Read cached output for this step."""
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

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> Any:
        """Get storage path for a file. Returns Path-like object."""
        ...
