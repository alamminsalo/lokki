"""Store utilities for lokki."""

from __future__ import annotations

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
