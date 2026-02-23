"""Local filesystem store implementation."""

from __future__ import annotations

import gzip
import json
import pickle
import shutil
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lokki.store.protocol import DataStore

if TYPE_CHECKING:
    pass


def _to_json_safe(obj: Any) -> Any:
    """Convert objects to JSON-safe types."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_to_json_safe(item) for item in obj]
    return obj


class LocalStore(DataStore):
    """Local file-based store implementing DataStore interface."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(tempfile.mkdtemp(prefix="lokki-"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> Path:
        return self.base_dir / flow_name / run_id / step_name / filename

    def write(
        self,
        flow_name: str | None = None,
        run_id: str | None = None,
        step_name: str | None = None,
        obj: Any = None,
        *,
        bucket: str | None = None,
        key: str | None = None,
    ) -> str:
        if bucket and key:
            path = Path(bucket) / key
        elif flow_name and run_id and step_name:
            path = self._get_path(flow_name, run_id, step_name, "output.pkl.gz")
        else:
            raise ValueError(
                "Must provide either (bucket, key) or (flow_name, run_id, step_name)"
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        path.write_bytes(data)
        return str(path)

    def write_manifest(
        self,
        flow_name: str | None = None,
        run_id: str | None = None,
        step_name: str | None = None,
        items: Sequence[dict[str, Any]] | None = None,
        *,
        bucket: str | None = None,
        key: str | None = None,
    ) -> str:
        if bucket and key:
            path = Path(bucket) / key
        elif flow_name and run_id and step_name:
            path = self._get_path(flow_name, run_id, step_name, "map_manifest.json")
        else:
            raise ValueError(
                "Must provide either (bucket, key) or (flow_name, run_id, step_name)"
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        serialized_items = _to_json_safe(items)
        path.write_text(json.dumps(serialized_items))
        return str(path)

    def read(self, location: str) -> Any:
        data = Path(location).read_bytes()
        return pickle.loads(gzip.decompress(data))

    def cleanup(self) -> None:
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
