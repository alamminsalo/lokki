"""Store utilities for lokki."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any


def _to_json_safe(obj: Any) -> Any:
    """Convert objects to JSON-safe types."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_to_json_safe(item) for item in obj]
    return obj


def _hash_input(input_data: Any) -> str:
    """Compute a deterministic hash of input data.

    Used to create cache validation keys. Same inputs will produce the same hash.
    """
    json_safe = _to_json_safe(input_data)
    json_str = json.dumps(json_safe, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]
