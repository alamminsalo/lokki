"""Data models for Lokki pipeline library."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepArtifact:
    """Represents a stored step output artifact."""

    step_name: str
    artifact_id: str
    storage_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataStoreConfig:
    """Configuration for datastore backends."""

    temp_dir: str | None = None
    compression_level: int = 6
    cleanup_on_exit: bool = True


@dataclass
class StepNode:
    """Represents a step in the pipeline DAG."""

    name: str
    function: Any
    dependencies: list[str]
    outputs: list[str]


@dataclass
class DAGInfo:
    """Serializable DAG information."""

    name: str
    steps: list[dict[str, Any]]
    dependencies: dict[str, list[str]]
    parameters: dict[str, str]
