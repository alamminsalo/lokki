"""Local filesystem store implementation for transient data."""

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

from lokki.store.protocol import TransientStore

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


class LocalStore(TransientStore):
    """Local file-based store implementing TransientStore interface."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            self.base_dir = Path(tempfile.mkdtemp(prefix="lokki-"))
        elif isinstance(base_dir, str):
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> Path:
        return self.base_dir / flow_name / run_id / step_name / filename

    def write(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        obj: Any,
    ) -> str:
        path = self._get_path(flow_name, run_id, step_name, "output.pkl.gz")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        path.write_bytes(data)
        return str(path)

    def write_manifest(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        items: Sequence[dict[str, Any]],
    ) -> str:
        path = self._get_path(flow_name, run_id, step_name, "map_manifest.json")
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
