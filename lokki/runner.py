"""Local execution engine for lokki flows.

This module provides the LocalRunner class for executing flows locally.
It mimics AWS Step Functions behavior using local filesystem storage.
"""

from __future__ import annotations

import gzip
import json
import pickle
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from lokki._store import LocalStore
from lokki.decorators import RetryConfig, StepNode
from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry
from lokki.logging import LoggingConfig, MapProgressLogger, StepLogger, get_logger

# Backward compatibility
LocalStore = LocalStore


class LocalRunner:
    """Executes lokki flows locally.

    LocalRunner mimics AWS Step Functions behavior by executing flows
    on the local machine using filesystem storage for inter-step data.
    """

    def __init__(self, logging_config: LoggingConfig | None = None) -> None:
        self.logging_config = logging_config or LoggingConfig()
        self.logger = get_logger("lokki.runner", self.logging_config)

    def run(self, graph: FlowGraph, params: dict[str, Any] | None = None) -> Any:
        run_id = "local-run"
        store = LocalStore()
        params = params or {}

        self.logger.info(f"Starting flow '{graph.name}' (run_id={run_id})")
        if params:
            self.logger.debug(f"Input parameters: {params}")

        try:
            for entry in graph.entries:
                if isinstance(entry, TaskEntry):
                    self._run_task(store, graph.name, run_id, entry, params)
                elif isinstance(entry, MapOpenEntry):
                    self._run_map(store, graph.name, run_id, entry)
                elif isinstance(entry, MapCloseEntry):
                    self._run_agg(store, graph.name, run_id, entry)

            last_entry = graph.entries[-1]
            if isinstance(last_entry, MapCloseEntry):
                result_path = store._get_path(
                    graph.name, run_id, last_entry.agg_step.name, "output.pkl.gz"
                )
                return store.read(str(result_path))
            elif isinstance(last_entry, TaskEntry):
                result_path = store._get_path(
                    graph.name, run_id, last_entry.node.name, "output.pkl.gz"
                )
                return store.read(str(result_path))
            return None
        finally:
            store.cleanup()

    def _run_task(
        self,
        store: LocalStore,
        flow_name: str,
        run_id: str,
        entry: TaskEntry,
        params: dict[str, Any],
    ) -> None:
        node = entry.node
        step_name = node.name
        retry_config = node.retry
        job_type = entry.job_type or "lambda"

        step_logger = StepLogger(step_name, self.logger)
        step_logger.start()

        if job_type == "batch":
            self.logger.info(
                "Running Batch step '%s' locally (use AWS Batch for production)",
                step_name,
            )

        start_time = datetime.now()
        last_exception: Exception | None = None

        for attempt in range(retry_config.retries + 1):
            try:
                result = self._execute_step(
                    node, store, flow_name, run_id, params, job_type
                )

                duration = (datetime.now() - start_time).total_seconds()
                store.write(flow_name, run_id, step_name, result)

                if isinstance(result, list):
                    manifest_items = [
                        {"item": item, "index": i} for i, item in enumerate(result)
                    ]
                    store.write_manifest(flow_name, run_id, step_name, manifest_items)

                step_logger.complete(duration)
                return
            except Exception as e:
                if not self._is_retriable(e, retry_config):
                    raise
                last_exception = e
                if attempt < retry_config.retries:
                    delay = min(
                        retry_config.delay * (retry_config.backoff**attempt),
                        retry_config.max_delay,
                    )
                    self.logger.info(
                        f"Step '{step_name}' failed (attempt {attempt + 1}/"
                        f"{retry_config.retries + 1}), retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    duration = (datetime.now() - start_time).total_seconds()
                    step_logger.fail(duration, e)

        if last_exception:
            raise last_exception

    def _is_retriable(self, error: Exception, retry_config: RetryConfig) -> bool:
        """Check if the error is an instance of any retriable exception type."""
        return any(isinstance(error, exc_type) for exc_type in retry_config.exceptions)

    def _execute_step(
        self,
        node: StepNode,
        store: LocalStore,
        flow_name: str,
        run_id: str,
        params: dict[str, Any],
        job_type: str = "lambda",
    ) -> Any:
        """Execute a single step function without retry logic."""
        result = None
        if node._prev is not None:
            prev_path = store._get_path(
                flow_name, run_id, node._prev.name, "output.pkl.gz"
            )
            if prev_path.exists():
                result = store.read(str(prev_path))

        flow_kwargs = getattr(node, "_flow_kwargs", {})

        if result is not None:
            if node._default_args or node._default_kwargs or flow_kwargs:
                result = node.fn(
                    result,
                    *node._default_args,
                    **node._default_kwargs,
                    **flow_kwargs,
                )
            else:
                result = node.fn(result)
        elif node._default_args or node._default_kwargs:
            result = node.fn(*node._default_args, **node._default_kwargs)
        elif flow_kwargs:
            result = node.fn(**flow_kwargs)
        elif params:
            result = node.fn(**params)
        else:
            result = node.fn()

        return result

    def _run_map(
        self, store: LocalStore, flow_name: str, run_id: str, entry: MapOpenEntry
    ) -> None:
        source_name = entry.source.name
        manifest_path = store._get_path(
            flow_name, run_id, source_name, "map_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())

        inner_steps = entry.inner_steps

        step_logger = StepLogger(source_name, self.logger)
        step_logger.start()

        map_logger = MapProgressLogger(
            source_name, len(manifest), self.logger, self.logging_config
        )
        map_logger.start()

        def run_step_for_item(
            fn: Callable[[Any], Any],
            item_data: Any,
            item_idx: int,
            flow_kwargs: dict[str, Any],
            retry_config: RetryConfig,
        ) -> Any:
            last_exception: Exception | None = None
            for attempt in range(retry_config.retries + 1):
                try:
                    if flow_kwargs:
                        result = fn(item_data, **flow_kwargs)
                    else:
                        result = fn(item_data)
                    return result
                except Exception as e:
                    if not any(
                        isinstance(e, exc_type) for exc_type in retry_config.exceptions
                    ):
                        raise
                    last_exception = e
                    if attempt < retry_config.retries:
                        delay = min(
                            retry_config.delay * (retry_config.backoff**attempt),
                            retry_config.max_delay,
                        )
                        time.sleep(delay)
            if last_exception:
                raise last_exception

        item_data_by_idx = {item["index"]: item["item"] for item in manifest}
        current_results: dict[int, Any] = dict(item_data_by_idx)

        for _step_idx, step_node in enumerate(inner_steps):
            step_name = step_node.name
            fn = step_node.fn
            flow_kwargs = getattr(step_node, "_flow_kwargs", {})
            retry_config = step_node.retry

            with ThreadPoolExecutor() as executor:
                futures = {}
                for item_idx, item_data in current_results.items():
                    future = executor.submit(
                        run_step_for_item,
                        fn,
                        item_data,
                        item_idx,
                        flow_kwargs,
                        retry_config,
                    )
                    futures[future] = item_idx

                new_results: dict[int, Any] = {}
                for future in as_completed(futures):
                    result = future.result()
                    item_idx = futures[future]
                    new_results[item_idx] = result

                    item_result_path = store._get_path(
                        flow_name, run_id, f"{step_name}/{item_idx}", "output.pkl.gz"
                    )
                    item_result_path.parent.mkdir(parents=True, exist_ok=True)
                    data = gzip.compress(
                        pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
                    )
                    item_result_path.write_bytes(data)
                    map_logger.update("completed")

            current_results = new_results

        map_logger.complete()
        step_logger.complete(0.0)

    def _run_agg(
        self, store: LocalStore, flow_name: str, run_id: str, entry: MapCloseEntry
    ) -> None:
        if entry.agg_step._map_block is None:
            raise ValueError("Aggregation step must follow a map block")

        map_block = entry.agg_step._map_block
        source_name = map_block.source.name
        last_inner_step = map_block.inner_tail.name

        manifest = json.loads(
            store._get_path(
                flow_name, run_id, source_name, "map_manifest.json"
            ).read_text()
        )

        result_urls: list[str] = []
        for item in manifest:
            item_idx = item["index"]
            result_path = store._get_path(
                flow_name, run_id, f"{last_inner_step}/{item_idx}", "output.pkl.gz"
            )
            result_urls.append(str(result_path))

        inputs = [store.read(url) for url in result_urls]

        flow_kwargs = getattr(entry.agg_step, "_flow_kwargs", {})
        if flow_kwargs:
            result = entry.agg_step.fn(inputs, **flow_kwargs)
        else:
            result = entry.agg_step.fn(inputs)

        step_name = entry.agg_step.name
        store.write(flow_name, run_id, step_name, result)
