"""Lokki - A Python library for creating pipelines from @flow and @step decorators."""

from .data_store import (
    DataStore,
    DataStoreConfig,
    S3Config,
    S3DataStore,
    TempFileDataStore,
)
from .decorators import flow, step
from .models import DAGInfo, StepArtifact, StepNode
from .pipeline import Pipeline

__all__ = [
    "Pipeline",
    "step",
    "flow",
    "DataStore",
    "TempFileDataStore",
    "S3DataStore",
    "DataStoreConfig",
    "S3Config",
    "StepArtifact",
    "StepNode",
    "DAGInfo",
]


def main() -> None:
    """Entry point for the lokki CLI."""
    print("Lokki pipeline library")
