"""Step and flow decorators for defining pipelines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lokki.graph import FlowGraph


@dataclass
class RetryConfig:
    """Configuration for step retry behavior."""

    retries: int = 0
    delay: float = 1.0
    backoff: float = 1.0
    max_delay: float = 60.0
    exceptions: tuple[type, ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.retries < 0:
            raise ValueError("retries must be non-negative")
        if self.delay <= 0:
            raise ValueError("delay must be positive")
        if self.backoff <= 0:
            raise ValueError("backoff must be positive")
        if self.max_delay <= 0:
            raise ValueError("max_delay must be positive")


@dataclass
class JobTypeConfig:
    """Configuration for step execution backend (Lambda or Batch)."""

    job_type: str = "lambda"  # "lambda" or "batch"
    vcpu: int | None = None  # None = use global config
    memory_mb: int | None = None
    timeout_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.job_type not in ("lambda", "batch"):
            raise ValueError("job_type must be 'lambda' or 'batch'")
        if self.vcpu is not None and self.vcpu <= 0:
            raise ValueError("vcpu must be positive")
        if self.memory_mb is not None and self.memory_mb <= 0:
            raise ValueError("memory_mb must be positive")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class StepNode:
    """Represents a single step in a pipeline.

    A StepNode wraps a function and provides methods for chaining steps together:
    - `.map(step)` - Run step in parallel for each item in a list (fan-out)
    - `.next(step)` - Run step sequentially after current step
    - `.agg(step)` - Aggregate results from parallel execution
      (must be called on MapBlock)

    Attributes:
        fn: The wrapped function.
        name: Function name.
        retry: Retry configuration for transient failures.
        job_type: Execution backend ("lambda" or "batch").
        vcpu: vCPUs for Batch jobs (overrides global config).
        memory_mb: Memory in MB for Batch jobs (overrides global config).
        timeout_seconds: Timeout in seconds for Batch jobs (overrides global config).
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        retry: RetryConfig | None = None,
        job_type: str = "lambda",
        vcpu: int | None = None,
        memory_mb: int | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.fn = fn
        self.name = fn.__name__
        self.retry = retry or RetryConfig()
        self.job_type = job_type
        self.vcpu = vcpu
        self.memory_mb = memory_mb
        self.timeout_seconds = timeout_seconds
        self._default_args: tuple[Any, ...] = ()
        self._default_kwargs: dict[str, Any] = {}
        self._flow_kwargs: dict[str, Any] = {}
        self._next: StepNode | None = None
        self._prev: StepNode | None = None
        self._map_block: MapBlock | None = None
        self._closes_map_block: bool = False

    def __call__(self, *args: Any, **kwargs: Any) -> StepNode:
        """Record default args and return self for chaining."""
        self._default_args = args
        self._default_kwargs = kwargs
        return self

    def map(
        self,
        step_node: StepNode,
        concurrency_limit: int | None = None,
        **kwargs: Any,
    ) -> MapBlock:
        """Start a Map block with optional concurrency limit and flow-level kwargs.

        Args:
            step_node: The step to run for each item
            concurrency_limit: Optional limit on parallel iterations
            **kwargs: Flow-level parameters passed to the step
        """
        block = MapBlock(
            source=self,
            inner_head=step_node,
            concurrency_limit=concurrency_limit,
        )
        step_node._flow_kwargs = kwargs
        self._map_block = block
        return block

    def next(self, step_node: StepNode, **kwargs: Any) -> StepNode:
        """Chain a step with flow-level kwargs."""
        step_node._prev = self
        step_node._flow_kwargs = kwargs
        self._next = step_node
        return step_node

    def agg(self, step_node: StepNode) -> StepNode:
        """Raises TypeError - agg() must be called on MapBlock."""
        raise TypeError(
            ".agg() must be called on the result of .map(), not directly on a step"
        )


class MapBlock:
    """Represents a Map block for parallel processing.

    Created by calling `.map()` on a StepNode. Contains:
    - source: The step that produces the list of items to process
    - inner_steps: Steps to run for each item (chain via `.map()` or `.next()`)
    - concurrency_limit: Optional limit on parallel iterations

    Methods:
        .map(step) - Add step to run for each item
        .next(step) - Add step to run for each item (alias for .map())
        .agg(step) - Close block and aggregate results
    """

    def __init__(
        self,
        source: StepNode,
        inner_head: StepNode,
        concurrency_limit: int | None = None,
    ) -> None:
        self.source = source
        self.inner_head = inner_head
        self.inner_tail = inner_head
        self._next: StepNode | None = None
        self._flow_kwargs: dict[str, Any] = {}
        self.concurrency_limit = concurrency_limit

    @property
    def inner_steps(self) -> list[StepNode]:
        """Get all inner steps as a list."""
        steps = []
        current: StepNode | None = self.inner_head
        while current is not None:
            steps.append(current)
            if current is self.inner_tail:
                break
            current = current._next
        return steps

    def map(self, step_node: StepNode, **kwargs: Any) -> MapBlock:
        """Add another step to the inner chain with flow-level kwargs."""
        step_node._prev = self.inner_tail
        step_node._flow_kwargs = kwargs
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def next(self, step_node: StepNode, **kwargs: Any) -> MapBlock:
        """Add step to inner chain (before agg) with flow-level kwargs."""
        step_node._prev = self.inner_tail
        step_node._flow_kwargs = kwargs
        self.inner_tail._next = step_node
        self.inner_tail = step_node
        return self

    def agg(self, step_node: StepNode, **kwargs: Any) -> StepNode:
        """Close the Map block and attach an aggregation step with flow-level kwargs."""
        step_node._closes_map_block = True
        step_node._map_block = self
        step_node._flow_kwargs = kwargs
        self._next = step_node
        return step_node


def step(
    fn: Callable[..., Any] | None = None,
    *,
    retry: RetryConfig | dict[str, Any] | None = None,
    job_type: str = "lambda",
    vcpu: int | None = None,
    memory_mb: int | None = None,
    timeout_seconds: int | None = None,
) -> StepNode | Callable[[Callable[..., Any]], StepNode]:
    """Decorate a function as a pipeline step.

    Args:
        fn: The function to decorate as a step.
        retry: Optional retry configuration. Can be a RetryConfig instance or a dict
               with keys: retries, delay, backoff, max_delay, exceptions.
        job_type: Execution backend - "lambda" (default) or "batch".
        vcpu: Number of vCPUs for Batch jobs (overrides global config).
        memory_mb: Memory in MB for Batch jobs (overrides global config).
        timeout_seconds: Timeout in seconds for Batch jobs (overrides global config).
    """

    def decorator(fn: Callable[..., Any]) -> StepNode:
        if retry is None:
            retry_config = RetryConfig()
        elif isinstance(retry, RetryConfig):
            retry_config = retry
        elif isinstance(retry, dict):
            retry_config = RetryConfig(**retry)
        else:
            raise TypeError(
                f"retry must be RetryConfig, dict, or None, got {type(retry).__name__}"
            )
        return StepNode(
            fn,
            retry=retry_config,
            job_type=job_type,
            vcpu=vcpu,
            memory_mb=memory_mb,
            timeout_seconds=timeout_seconds,
        )

    if fn is None:
        return decorator
    return decorator(fn)


def _validate_schedule(schedule: str) -> None:
    """Validate a schedule expression (cron or rate).

    Args:
        schedule: A cron or rate expression, e.g., "cron(0 9 * * ? *)" or "rate(1 hour)"

    Raises:
        ValueError: If the schedule expression is invalid
    """
    schedule = schedule.strip()

    if schedule.startswith("cron(") and schedule.endswith(")"):
        cron_expr = schedule[5:-1].strip()
        _validate_cron_expression(cron_expr)
    elif schedule.startswith("rate(") and schedule.endswith(")"):
        rate_expr = schedule[5:-1].strip()
        _validate_rate_expression(rate_expr)
    else:
        raise ValueError(
            f"Invalid schedule expression: '{schedule}'. "
            "Use 'cron(minute hour day month day-of-week ?)' or 'rate(value unit)'"
        )


def _validate_cron_expression(cron_expr: str) -> None:
    """Validate a cron expression.

    Args:
        cron_expr: The cron expression (without cron() wrapper)

    Raises:
        ValueError: If the cron expression is invalid
    """
    parts = cron_expr.split()
    if len(parts) < 5 or len(parts) > 6:
        raise ValueError(
            f"Invalid cron expression: '{cron_expr}'. "
            "Expected 5 or 6 fields (minute hour day month day-of-week ?)"
        )


def _validate_rate_expression(rate_expr: str) -> None:
    """Validate a rate expression.

    Args:
        rate_expr: The rate expression (without rate() wrapper)

    Raises:
        ValueError: If the rate expression is invalid
    """
    rate_expr = rate_expr.strip()
    if not rate_expr:
        raise ValueError("Rate expression cannot be empty")

    valid_units = {"minute", "minutes", "hour", "hours", "day", "days"}

    parts = rate_expr.split()
    if len(parts) != 2:
        raise ValueError(
            f"Invalid rate expression: '{rate_expr}'. Expected 'rate(value unit)'"
        )

    try:
        value = int(parts[0])
        if value < 1:
            raise ValueError()
    except ValueError as e:
        raise ValueError(
            f"Invalid rate expression: '{rate_expr}'. Value must be a positive integer"
        ) from e

    unit = parts[1].lower()
    if unit not in valid_units:
        raise ValueError(
            f"Invalid rate expression: '{rate_expr}'. "
            f"Unit must be one of: {', '.join(sorted(valid_units))}"
        )


def flow(
    fn: Callable[..., Any] | None = None,
    *,
    schedule: str | None = None,
) -> (
    Callable[..., FlowGraph] | Callable[[Callable[..., Any]], Callable[..., FlowGraph]]
):
    """Decorate a function as a pipeline flow.

    The decorated function must return a chain of steps (StepNode or MapBlock).
    The flow name is derived from the function name (snake_case -> kebab-case).

    Args:
        fn: A function that returns a step chain, e.g., step1().map(step2)
        schedule: Optional schedule expression (cron or rate), e.g., "cron(0 9 * * ? *)"
            or "rate(1 hour)"

    Returns:
        A wrapper that constructs a FlowGraph when called.

    Example:
        @flow
        def my_flow():
            return step1().next(step2())

        @flow(schedule="cron(0 9 * * ? *)")
        def daily_flow():
            return fetch_data().process().save()

        @flow(schedule="rate(1 hour)")
        def hourly_flow():
            return hourly_task()
    """
    if schedule is not None:
        _validate_schedule(schedule)

    def decorator(fn: Callable[..., Any]) -> Callable[..., FlowGraph]:
        def wrapper(*args: Any, **kwargs: Any) -> FlowGraph:
            from lokki.graph import FlowGraph

            head = fn(*args, **kwargs)

            if head is None:
                raise ValueError(
                    f"@flow function '{fn.__name__}' returned None. "
                    "Did you forget to return the chain? "
                    "Example: return step1().map(step2)"
                )

            if not isinstance(head, StepNode | MapBlock):
                raise ValueError(
                    f"@flow function '{fn.__name__}' must return a step chain "
                    "(e.g., step1().map(step2)), but returned {type(head).__name__}"
                )

            return FlowGraph(
                name=fn.__name__.replace("_", "-").lower(),
                head=head,
                schedule=schedule,
            )

        wrapper._is_flow = True  # type: ignore[attr-defined]
        wrapper._fn = fn  # type: ignore[attr-defined]
        return wrapper

    if fn is None:
        return decorator
    return decorator(fn)
