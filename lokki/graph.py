"""Execution graph model for lokki pipelines."""

__all__ = ["TaskEntry", "MapOpenEntry", "MapCloseEntry", "GraphEntry", "FlowGraph"]

from dataclasses import dataclass, field

from lokki.decorators import JobType, MapBlock, StepNode


@dataclass(slots=True)
class TaskEntry:
    """A single task step in the execution graph.

    Attributes:
        node: The step node to execute.
        job_type: Execution backend - "lambda" or "batch".
        vcpu: vCPUs for Batch jobs (overrides global config).
        memory_mb: Memory in MB for Batch jobs (overrides global config).
        timeout_seconds: Timeout in seconds for Batch jobs (overrides global config).
    """

    node: StepNode
    job_type: JobType = "lambda"
    vcpu: int | None = None
    memory_mb: int | None = None
    timeout_seconds: int | None = None


@dataclass(slots=True)
class MapOpenEntry:
    """Opens a Map block with source and inner steps.

    Attributes:
        source: The step that produces the list of items to process.
        inner_steps: Steps to run for each item in parallel.
        concurrency_limit: Optional limit on parallel iterations.
        has_aggregation: True if map block has .agg() step, False otherwise.
        direct_pass: Pass results in memory between inner steps.
    """

    source: StepNode
    inner_steps: list[StepNode] = field(default_factory=list)
    concurrency_limit: int | None = None
    has_aggregation: bool = True
    direct_pass: bool = False


@dataclass(slots=True, frozen=True)
class MapCloseEntry:
    """Closes a Map block with an aggregation step.

    Attributes:
        agg_step: The aggregation step that processes all map results.
    """

    agg_step: StepNode


type GraphEntry = TaskEntry | MapOpenEntry | MapCloseEntry


class FlowGraph:
    """Resolved execution graph for a pipeline flow.

    Attributes:
        name: The flow name (kebab-case)
        head: The head of the step chain
        entries: List of resolved graph entries in execution order
        schedule: Optional schedule expression (cron or rate)
    """

    def __init__(
        self,
        name: str,
        head: StepNode | MapBlock,
        schedule: str | None = None,
    ) -> None:
        self.name = name
        self.head = head
        self.entries: list[GraphEntry] = []
        self.schedule = schedule
        chain_start = self._find_chain_start(head)
        self._resolve_from_head(chain_start)

    def _find_chain_start(self, node: StepNode | MapBlock) -> StepNode:
        """Find the true start of the chain by following back-references.

        Args:
            node: The starting node (StepNode or MapBlock).

        Returns:
            StepNode: The first node in the chain.
        """
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
        """Walk the chain from the head and populate entries in execution order.

        Args:
            head: The starting StepNode of the chain.
        """
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
                self.entries.append(
                    TaskEntry(
                        node=current,
                        job_type=current.job_type,
                        vcpu=current.vcpu,
                        memory_mb=current.memory_mb,
                        timeout_seconds=current.timeout_seconds,
                    )
                )
                self._resolve_map_block(current._map_block)
                if (
                    current._map_block._next is not None
                    and current._map_block._next._closes_map_block
                ):
                    processed_nodes.add(id(current._map_block._next))
                current = current._map_block._next
            else:
                self.entries.append(
                    TaskEntry(
                        node=current,
                        job_type=current.job_type,
                        vcpu=current.vcpu,
                        memory_mb=current.memory_mb,
                        timeout_seconds=current.timeout_seconds,
                    )
                )
                current = current._next

        self._validate()

    def _resolve_map_block(self, block: MapBlock) -> None:
        """Resolve a MapBlock into MapOpenEntry and MapCloseEntry.

        Args:
            block: The MapBlock to resolve.
        """
        inner_steps: list[StepNode] = []
        step: StepNode | None = block.inner_head
        while step is not None:
            inner_steps.append(step)
            if step is block.inner_tail:
                break
            step = step._next

        has_aggregation = block._closed

        self.entries.append(
            MapOpenEntry(
                source=block.source,
                inner_steps=inner_steps,
                concurrency_limit=block.concurrency_limit,
                has_aggregation=has_aggregation,
                direct_pass=block.direct_pass,
            )
        )

        if block._next is not None and block._next._closes_map_block:
            self.entries.append(MapCloseEntry(agg_step=block._next))

    def _validate(self) -> None:
        """Validate the resolved graph for common errors.

        Checks:
        - No empty graphs (no entries)
        - Map blocks have inner steps

        Raises:
            GraphValidationError: If graph validation fails
        """
        errors: list[str] = []

        # Check for empty map blocks
        for entry in self.entries:
            if isinstance(entry, MapOpenEntry):
                if not entry.inner_steps:
                    errors.append(f"Map block '{entry.source.name}' has no inner steps")

        # Check for unreachable steps (steps not in the main chain)
        # This is already prevented by the graph resolution logic, but we check anyway
        if not self.entries:
            errors.append(
                "Graph has no entries - flow function must return a step chain"
            )

        if errors:
            from lokki._errors import GraphValidationError

            raise GraphValidationError(
                f"Graph validation failed for '{self.name}'",
                errors,
            )

    @property
    def step_names(self) -> set[str]:
        """Extract unique step names from graph."""
        names: set[str] = set()
        for entry in self.entries:
            if isinstance(entry, TaskEntry):
                names.add(entry.node.name)
            elif isinstance(entry, MapOpenEntry):
                names.add(entry.source.name)
                for step in entry.inner_steps:
                    names.add(step.name)
            elif isinstance(entry, MapCloseEntry):
                names.add(entry.agg_step.name)
        return names
