"""Store module for lokki data persistence.

This module provides storage backends for pipeline data:
- LocalStore: Local filesystem storage for development/testing
- S3Store: AWS S3 storage for cloud deployments
"""

from lokki.store.local import LocalStore  # noqa: E402, F401
from lokki.store.protocol import DataStore  # noqa: E402, F401
from lokki.store.s3 import S3Store  # noqa: E402, F401

__all__ = ["DataStore", "LocalStore", "S3Store"]
