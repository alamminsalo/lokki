"""Local execution engine for lokki flows."""

from __future__ import annotations

import gzip
import json
import pickle
import shutil
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry
from lokki.logging import LoggingConfig, MapProgressLogger, StepLogger, get_logger


def _to_json_safe(obj: Any) -> Any:
    """Convert objects to JSON-safe types."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_to_json_safe(item) for item in obj]
    return obj


class LocalStore:
    """Local file-based store mirroring S3 interface."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(tempfile.mkdtemp(prefix="lokki-"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> Path:
        return self.base_dir / flow_name / run_id / step_name / filename

    def write(self, flow_name: str, run_id: str, step_name: str, obj: Any) -> str:
        path = self._get_path(flow_name, run_id, step_name, "output.pkl.gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        path.write_bytes(data)
        return str(path)

    def write_manifest(
        self, flow_name: str, run_id: str, step_name: str, items: list[dict[str, Any]]
    ) -> str:
        path = self._get_path(flow_name, run_id, step_name, "map_manifest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized_items = _to_json_safe(items)
        path.write_text(json.dumps(serialized_items))
        return str(path)

    def read(self, path: str) -> Any:
        data = Path(path).read_bytes()
        return pickle.loads(gzip.decompress(data))

    def cleanup(self) -> None:
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)


class LocalRunner:
    def __init__(self, logging_config: LoggingConfig | None = None) -> None:
        self.logging_config = logging_config or LoggingConfig()
        self.logger = get_logger("lokki.runner", self.logging_config)

    def run(self, graph: FlowGraph) -> Any:
        run_id = "local-run"
        store = LocalStore()

        self.logger.info(f"Starting flow '{graph.name}' (run_id={run_id})")

        try:
            for entry in graph.entries:
                if isinstance(entry, TaskEntry):
                    self._run_task(store, graph.name, run_id, entry)
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
        self, store: LocalStore, flow_name: str, run_id: str, entry: TaskEntry
    ) -> None:
        node = entry.node
        step_name = node.name

        step_logger = StepLogger(step_name, self.logger)
        step_logger.start()

        start_time = datetime.now()
        try:
            result = None
            if node._prev is not None:
                prev_path = store._get_path(
                    flow_name, run_id, node._prev.name, "output.pkl.gz"
                )
                if prev_path.exists():
                    result = store.read(str(prev_path))

            if result is not None:
                if node._default_args or node._default_kwargs:
                    result = node.fn(
                        result, *node._default_args, **node._default_kwargs
                    )
                else:
                    result = node.fn(result)
            elif node._default_args or node._default_kwargs:
                result = node.fn(*node._default_args, **node._default_kwargs)
            else:
                result = node.fn()

            duration = (datetime.now() - start_time).total_seconds()

            store.write(flow_name, run_id, step_name, result)

            if isinstance(result, list):
                manifest_items = [
                    {"item": item, "index": i} for i, item in enumerate(result)
                ]
                store.write_manifest(flow_name, run_id, step_name, manifest_items)

            step_logger.complete(duration)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            step_logger.fail(duration, e)
            raise

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
            fn: Callable[[Any], Any], item_data: Any, item_idx: int
        ) -> Any:
            result = fn(item_data)
            return item_idx, result

        item_data_by_idx = {item["index"]: item["item"] for item in manifest}
        current_results: dict[int, Any] = dict(item_data_by_idx)

        for _step_idx, step_node in enumerate(inner_steps):
            step_name = step_node.name
            fn = step_node.fn

            with ThreadPoolExecutor() as executor:
                futures = {}
                for item_idx, item_data in current_results.items():
                    future = executor.submit(run_step_for_item, fn, item_data, item_idx)
                    futures[future] = item_idx

                new_results: dict[int, Any] = {}
                for future in as_completed(futures):
                    item_idx, result = future.result()
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
        result = entry.agg_step.fn(inputs)

        step_name = entry.agg_step.name
        store.write(flow_name, run_id, step_name, result)
