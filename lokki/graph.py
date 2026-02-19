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
        if isinstance(node, StepNode) and node._map_block is not None:
            return node._map_block.source
        return node

    def _resolve_from_head(self, head: StepNode) -> None:
        """Walk the chain from the head and populate entries in execution order."""
        current: StepNode | MapBlock | None = head
        processed_blocks: set[int] = set()
        processed_nodes: set[int] = set()

        while current is not None:
            if isinstance(current, StepNode) and id(current) in processed_nodes:
                current = current._next
                continue

            if isinstance(current, MapBlock):
                if id(current) not in processed_blocks:
                    processed_blocks.add(id(current))
                    self._resolve_map_block(current)
                current = current._next
            elif isinstance(current, StepNode):
                processed_nodes.add(id(current))
                if (
                    current._map_block is not None
                    and id(current._map_block) not in processed_blocks
                ):
                    # This step is a source of a Map block
                    self.entries.append(TaskEntry(node=current))
                    processed_blocks.add(id(current._map_block))
                    self._resolve_map_block(current._map_block)
                    current = current._map_block._next
                else:
                    self.entries.append(TaskEntry(node=current))
                    current = current._next
            else:
                break
            processed_nodes.add(id(current))

            if isinstance(current, MapBlock):
                if id(current) not in processed_blocks:
                    processed_blocks.add(id(current))
                    # Source step should already be added; add Map entries now
                    self._resolve_map_block(current)
                current = current._next
            elif isinstance(current, StepNode):
                if current._map_block is not None:
                    # This step has a Map block - add source as TaskEntry first
                    if (
                        id(current) not in processed_nodes
                        or current._map_block.source is current
                    ):
                        if id(current) not in processed_nodes:
                            self.entries.append(TaskEntry(node=current))
                        # Then process the Map block
                        if id(current._map_block) not in processed_blocks:
                            processed_blocks.add(id(current._map_block))
                            self._resolve_map_block(current._map_block)
                        current = current._map_block._next
                    else:
                        current = current._next
                else:
                    self.entries.append(TaskEntry(node=current))
                    current = current._next
            else:
                break

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
