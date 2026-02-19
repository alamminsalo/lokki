"""Local execution engine for lokki flows."""

from __future__ import annotations

import gzip
import json
import pickle
import shutil
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from lokki.graph import FlowGraph, MapCloseEntry, MapOpenEntry, TaskEntry


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
        path.write_text(json.dumps(items))
        return str(path)

    def read(self, path: str) -> Any:
        data = Path(path).read_bytes()
        return pickle.loads(gzip.decompress(data))

    def cleanup(self) -> None:
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)


class LocalRunner:
    def run(self, graph: FlowGraph) -> Any:
        run_id = "local-run"
        store = LocalStore()

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

        if node._default_args or node._default_kwargs:
            result = node.fn(*node._default_args, **node._default_kwargs)
        else:
            result = node.fn()

        store.write(flow_name, run_id, step_name, result)

        if isinstance(result, list):
            manifest_items = [
                {"item": item, "index": i} for i, item in enumerate(result)
            ]
            store.write_manifest(flow_name, run_id, step_name, manifest_items)

    def _run_map(
        self, store: LocalStore, flow_name: str, run_id: str, entry: MapOpenEntry
    ) -> None:
        source_name = entry.source.name
        manifest_path = store._get_path(
            flow_name, run_id, source_name, "map_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())

        inner_steps = entry.inner_steps

        with ThreadPoolExecutor() as executor:
            futures = {}
            for item in manifest:
                item_idx = item["index"]
                item_data = item["item"]

                for step_node in inner_steps:
                    step_name = step_node.name
                    result_path = store._get_path(
                        flow_name, run_id, f"{step_name}/{item_idx}", "output.pkl.gz"
                    )

                    fn = step_node.fn

                    def run_step(
                        fn: Callable[[Any], Any], rp: Path, it: Any
                    ) -> tuple[str, Path, Any]:
                        res = fn(it)
                        rp.parent.mkdir(parents=True, exist_ok=True)
                        data = gzip.compress(
                            pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL)
                        )
                        rp.write_bytes(data)
                        return "", rp, res

                    future = executor.submit(run_step, fn, result_path, item_data)
                    futures[future] = (step_name, result_path)

            for future in as_completed(futures):
                future.result()

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
