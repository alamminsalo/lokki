"""Execution graph model for lokki pipelines."""

from dataclasses import dataclass, field

from lokki.decorators import MapBlock, StepNode


@dataclass
class TaskEntry:
    """A single task step in the execution graph."""

    node: StepNode


@dataclass
class MapOpenEntry:
    """Opens a Map block with source and inner steps."""

    source: StepNode
    inner_steps: list[StepNode] = field(default_factory=list)


@dataclass
class MapCloseEntry:
    """Closes a Map block with an aggregation step."""

    agg_step: StepNode


type GraphEntry = TaskEntry | MapOpenEntry | MapCloseEntry


class FlowGraph:
    """Resolved execution graph for a pipeline flow."""

    def __init__(self, name: str, head: StepNode | MapBlock) -> None:
        self.name = name
        self.head = head
        self.entries: list[GraphEntry] = []
        chain_start = self._find_chain_start(head)
        self._resolve_from_head(chain_start)

    def _find_chain_start(self, node: StepNode | MapBlock) -> StepNode:
        """Find the true start of the chain by following back-references."""
        if isinstance(node, MapBlock):
            return node.source
        if isinstance(node, StepNode):
            current = node
            visited: set[int] = set()
            while current is not None:
                if id(current) in visited:
                    break
                visited.add(id(current))
                if hasattr(current, "_prev") and current._prev is not None:
                    current = current._prev
                elif current._map_block is not None:
                    current = current._map_block.source
                else:
                    break
            return current
        return node

    def _resolve_from_head(self, head: StepNode) -> None:
        """Walk the chain from the head and populate entries in execution order."""
        processed_nodes: set[int] = set()
        processed_blocks: set[int] = set()

        current: StepNode | None = head

        while current is not None:
            if id(current) in processed_nodes:
                break

            processed_nodes.add(id(current))

            if (
                current._map_block is not None
                and id(current._map_block) not in processed_blocks
            ):
                processed_blocks.add(id(current._map_block))
                self.entries.append(TaskEntry(node=current))
                self._resolve_map_block(current._map_block)
                if (
                    current._map_block._next is not None
                    and current._map_block._next._closes_map_block
                ):
                    processed_nodes.add(id(current._map_block._next))
                current = current._map_block._next
            else:
                self.entries.append(TaskEntry(node=current))
                current = current._next

        self._validate()

    def _resolve_map_block(self, block: MapBlock) -> None:
        """Resolve a MapBlock into MapOpenEntry and MapCloseEntry."""
        inner_steps: list[StepNode] = []
        step: StepNode | None = block.inner_head
        while step is not None:
            inner_steps.append(step)
            if step is block.inner_tail:
                break
            step = step._next

        self.entries.append(MapOpenEntry(source=block.source, inner_steps=inner_steps))

        if block._next is not None and block._next._closes_map_block:
            self.entries.append(MapCloseEntry(agg_step=block._next))

    def _validate(self) -> None:
        """Validate the resolved graph for common errors."""
        open_map_blocks: dict[int, MapBlock] = {}

        for entry in self.entries:
            if isinstance(entry, MapOpenEntry):
                if entry.source._map_block is not None:
                    open_map_blocks[id(entry.source._map_block)] = (
                        entry.source._map_block
                    )

            if isinstance(entry, MapCloseEntry):
                if entry.agg_step._map_block is not None:
                    block_id = id(entry.agg_step._map_block)
                    if block_id in open_map_blocks:
                        del open_map_blocks[block_id]

        if open_map_blocks:
            block = list(open_map_blocks.values())[0]
            raise ValueError(
                f"Flow ends with an open Map block from step '{block.source.name}'. "
                "Use .agg() to close the Map block before ending the flow."
            )
