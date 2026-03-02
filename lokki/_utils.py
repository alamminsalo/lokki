"""Shared utility functions for lokki."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lokki.graph import FlowGraph


def to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def to_kebab(name: str) -> str:
    """Convert snake_case to kebab-case."""
    return name.replace("_", "-")


def get_step_names(graph: FlowGraph) -> set[str]:
    """Extract unique step names from graph.

    Note: This function is deprecated. Use graph.step_names property instead.
    """
    return graph.step_names
