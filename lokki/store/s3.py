"""S3 store implementation."""

from __future__ import annotations

import gzip
import json
import pickle
from typing import TYPE_CHECKING, Any

from lokki._aws import get_s3_client
from lokki.store.protocol import DataStore

if TYPE_CHECKING:
    from collections.abc import Sequence


class S3Store(DataStore):
    """S3-based store implementing DataStore interface."""

    def __init__(self, bucket: str, endpoint: str = "") -> None:
        self.bucket = bucket
        self.endpoint = endpoint
        self._client = get_s3_client(endpoint) if endpoint else get_s3_client()

    def _make_key(
        self, flow_name: str, run_id: str, step_name: str, filename: str
    ) -> str:
        return f"lokki/{flow_name}/{run_id}/{step_name}/{filename}"

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
            data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
            self._client.put_object(Bucket=bucket, Key=key, Body=data)
            return f"s3://{bucket}/{key}"

        if flow_name and run_id and step_name:
            key = self._make_key(flow_name, run_id, step_name, "output.pkl.gz")
            data = gzip.compress(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
            return f"s3://{self.bucket}/{key}"

        raise ValueError(
            "Must provide either (bucket, key) or (flow_name, run_id, step_name)"
        )

    def read(self, location: str) -> Any:
        bucket, key = self._parse_url(location)
        data = self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return pickle.loads(gzip.decompress(data))

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
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(items),
                ContentType="application/json",
            )
            return f"s3://{bucket}/{key}"

        if flow_name and run_id and step_name:
            key = self._make_key(flow_name, run_id, step_name, "map_manifest.json")
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(items),
                ContentType="application/json",
            )
            return f"s3://{self.bucket}/{key}"

        raise ValueError(
            "Must provide either (bucket, key) or (flow_name, run_id, step_name)"
        )

    @staticmethod
    def _parse_url(url: str) -> tuple[str, str]:
        if not url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL: {url}. Must start with 's3://'")
        parts = url[5:].split("/", 1)
        bucket = parts[0]
        if not bucket:
            raise ValueError(f"Invalid S3 URL: {url}. Missing bucket")
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key
