"""In-memory store implementation for transient data."""

from __future__ import annotations

import gzip
import json
import pickle
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from lokki.store.protocol import TransientStore
from lokki.store.utils import _to_json_safe

if TYPE_CHECKING:
    pass


class _MemoryPath:
    """Fake path-like object for MemoryStore."""

    def __init__(self, key: str, data: dict[str, Any]) -> None:
        self._key = key
        self._data: dict[str, bytes | str] = data

    @property
    def parent(self) -> _MemoryPath:
        parts = self._key.rsplit("/", 1)
        if "/" in self._key:
            return _MemoryPath(parts[0], self._data)
        return _MemoryPath("", self._data)

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        pass

    def write_bytes(self, data: bytes) -> None:
        self._data[self._key] = data

    def read_bytes(self) -> bytes:
        data = self._data[self._key]
        assert isinstance(data, bytes)
        return data

    def write_text(self, content: str) -> None:
        self._data[self._key] = content.encode()

    def read_text(self) -> str:
        data = self._data[self._key]
        assert isinstance(data, str)
        return data

    def exists(self) -> bool:
        return self._key in self._data

    def __str__(self) -> str:
        return f"memory://{self._key}"


class MemoryStore(TransientStore):
    """In-memory store implementing TransientStore interface.

    Stores all data in memory without filesystem I/O.
    Useful for local development in environments without writable partitions.
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._data: dict[str, Any] = {}

    def write(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        obj: Any,
        input_hash: str | None = None,
    ) -> str:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        serialized = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        self._data[key] = serialized
        return f"memory://{key}"

    def get_input_hash(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> str | None:
        return None

    def write_manifest(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
        items: Sequence[Any],
    ) -> str:
        key = self._make_key(flow_name, run_id, step_name, "map_manifest.json")
        serialized_items = _to_json_safe(items)
        self._data[key] = json.dumps(serialized_items)
        return f"memory://{key}"

    def read(self, location: str) -> Any:
        if location.startswith("memory://"):
            key = location[9:]
            data = self._data[key]
            return pickle.loads(gzip.decompress(data))
        raise ValueError(f"Invalid location: {location}")

    def exists(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> bool:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        return key in self._data

    def read_cached(
        self,
        flow_name: str,
        run_id: str,
        step_name: str,
    ) -> Any:
        key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
        data = self._data[key]
        return pickle.loads(gzip.decompress(data))

    def cleanup(self) -> None:
        self._data.clear()

    def _make_key(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> str:
        return f"{flow_name}/{run_id}/{step_name}/{filename}"

    def _get_path(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> _MemoryPath:
        key = self._make_key(flow_name, run_id, step_name, filename)
        return _MemoryPath(key, self._data)
