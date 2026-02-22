"""Shared utility functions for lokki."""

from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


def to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def to_kebab(name: str) -> str:
    """Convert snake_case to kebab-case."""
    return name.replace("_", "-")


def get_step_names(graph: FlowGraph) -> set[str]:
    """Extract unique step names from graph."""
    names: set[str] = set()
    for entry in graph.entries:
        if isinstance(entry, TaskEntry):
            names.add(entry.node.name)
        elif isinstance(entry, MapOpenEntry):
            names.add(entry.source.name)
            for step in entry.inner_steps:
                names.add(step.name)
        elif isinstance(entry, MapCloseEntry):
            names.add(entry.agg_step.name)
    return names
