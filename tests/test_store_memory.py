"""Unit tests for MemoryStore implementation."""

import gzip
import json
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from lokki.store.memory import MemoryStore


class TestMemoryStoreInit:
    """Tests for MemoryStore initialization."""

    def test_init_default(self) -> None:
        """Test MemoryStore initializes with default parameters."""
        store = MemoryStore()
        assert store._data == {}

    def test_init_with_base_dir(self) -> None:
        """Test MemoryStore accepts base_dir parameter (ignored)."""
        store = MemoryStore(base_dir="/tmp/test")
        assert store._data == {}


class TestMemoryStoreWriteRead:
    """Tests for MemoryStore write and read operations."""

    def test_write_read_basic(self) -> None:
        """Test basic write and read operations."""
        store = MemoryStore()
        test_data = {"key": "value", "number": 42}

        location = store.write(
            flow_name="test-flow",
            run_id="run-123",
            step_name="process",
            obj=test_data,
        )

        assert location.startswith("memory://")
        result = store.read(location)
        assert result == test_data

    def test_write_read_nested_data(self) -> None:
        """Test write and read with nested data structures."""
        store = MemoryStore()
        test_data = {
            "items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
            "metadata": {"count": 2, "tags": ["x", "y"]},
        }

        location = store.write(
            flow_name="complex-flow",
            run_id="run-456",
            step_name="transform",
            obj=test_data,
        )

        result = store.read(location)
        assert result == test_data

    def test_write_read_with_input_hash(self) -> None:
        """Test write with input_hash parameter (stored but not used in MemoryStore)."""
        store = MemoryStore()
        test_data = [1, 2, 3]

        location = store.write(
            flow_name="test-flow",
            run_id="run-789",
            step_name="step1",
            obj=test_data,
            input_hash="abc123",
        )

        result = store.read(location)
        assert result == test_data

    def test_write_multiple_steps(self) -> None:
        """Test writing multiple steps in same flow."""
        store = MemoryStore()

        loc1 = store.write("flow1", "run1", "step1", {"data": "step1"})
        loc2 = store.write("flow1", "run1", "step2", {"data": "step2"})
        loc3 = store.write("flow1", "run1", "step3", {"data": "step3"})

        assert store.read(loc1) == {"data": "step1"}
        assert store.read(loc2) == {"data": "step2"}
        assert store.read(loc3) == {"data": "step3"}

    def test_write_multiple_runs(self) -> None:
        """Test writing same step in different runs."""
        store = MemoryStore()

        loc1 = store.write("flow1", "run1", "step1", {"run": 1})
        loc2 = store.write("flow1", "run2", "step1", {"run": 2})

        assert store.read(loc1) == {"run": 1}
        assert store.read(loc2) == {"run": 2}


class TestMemoryStoreExists:
    """Tests for MemoryStore exists method."""

    def test_exists_after_write(self) -> None:
        """Test exists returns True after write."""
        store = MemoryStore()
        store.write("flow1", "run1", "step1", {"data": "test"})

        assert store.exists("flow1", "run1", "step1") is True

    def test_exists_before_write(self) -> None:
        """Test exists returns False before write."""
        store = MemoryStore()

        assert store.exists("flow1", "run1", "step1") is False

    def test_exists_different_flows(self) -> None:
        """Test exists distinguishes between flows."""
        store = MemoryStore()
        store.write("flow1", "run1", "step1", {"data": "test"})

        assert store.exists("flow1", "run1", "step1") is True
        assert store.exists("flow2", "run1", "step1") is False

    def test_exists_different_runs(self) -> None:
        """Test exists distinguishes between runs."""
        store = MemoryStore()
        store.write("flow1", "run1", "step1", {"data": "test"})

        assert store.exists("flow1", "run1", "step1") is True
        assert store.exists("flow1", "run2", "step1") is False


class TestMemoryStoreReadCached:
    """Tests for MemoryStore read_cached method."""

    def test_read_cached_basic(self) -> None:
        """Test basic read_cached operation."""
        store = MemoryStore()
        test_data = {"cached": "data"}

        store.write("flow1", "run1", "step1", test_data)
        result = store.read_cached("flow1", "run1", "step1")

        assert result == test_data

    def test_read_cached_missing(self) -> None:
        """Test read_cached raises KeyError for missing data."""
        store = MemoryStore()

        with pytest.raises(KeyError):
            store.read_cached("flow1", "run1", "step1")

    def test_read_cached_multiple_steps(self) -> None:
        """Test read_cached for multiple steps."""
        store = MemoryStore()

        store.write("flow1", "run1", "step1", {"step": 1})
        store.write("flow1", "run1", "step2", {"step": 2})

        assert store.read_cached("flow1", "run1", "step1") == {"step": 1}
        assert store.read_cached("flow1", "run1", "step2") == {"step": 2}


class TestMemoryStoreWriteManifest:
    """Tests for MemoryStore write_manifest method."""

    def test_write_manifest_basic(self) -> None:
        """Test basic write_manifest operation."""
        store = MemoryStore()
        items = [{"id": 1}, {"id": 2}, {"id": 3}]

        location = store.write_manifest(
            flow_name="flow1",
            run_id="run1",
            step_name="map_step",
            items=items,
        )

        assert location.startswith("memory://")
        assert "map_manifest.json" in location

    def test_write_manifest_empty(self) -> None:
        """Test write_manifest with empty list."""
        import json

        store = MemoryStore()

        location = store.write_manifest(
            flow_name="flow1",
            run_id="run1",
            step_name="map_step",
            items=[],
        )

        key = location[9:]
        result = json.loads(store._data[key])
        assert result == []

    def test_write_manifest_complex_objects(self) -> None:
        """Test write_manifest with complex objects."""
        import json

        store = MemoryStore()
        items = [
            {"data": [1, 2, 3], "nested": {"key": "value"}},
            {"data": [4, 5, 6], "nested": {"key": "value2"}},
        ]

        location = store.write_manifest("flow1", "run1", "map_step", items)
        key = location[9:]
        result = json.loads(store._data[key])

        assert result == items

    def test_write_manifest_multiple_steps(self) -> None:
        """Test write_manifest for multiple map steps."""
        import json

        store = MemoryStore()

        loc1 = store.write_manifest("flow1", "run1", "map1", [{"id": 1}])
        loc2 = store.write_manifest("flow1", "run1", "map2", [{"id": 2}])

        key1 = loc1[9:]
        key2 = loc2[9:]
        assert json.loads(store._data[key1]) == [{"id": 1}]
        assert json.loads(store._data[key2]) == [{"id": 2}]


class TestMemoryStoreCleanup:
    """Tests for MemoryStore cleanup method."""

    def test_cleanup_clears_all_data(self) -> None:
        """Test cleanup removes all stored data."""
        store = MemoryStore()

        store.write("flow1", "run1", "step1", {"data": "test"})
        store.write_manifest("flow1", "run1", "map1", [{"id": 1}])

        store.cleanup()

        assert store._data == {}
        assert store.exists("flow1", "run1", "step1") is False

    def test_cleanup_idempotent(self) -> None:
        """Test cleanup can be called multiple times."""
        store = MemoryStore()
        store.write("flow1", "run1", "step1", {"data": "test"})

        store.cleanup()
        store.cleanup()

        assert store._data == {}


class TestMemoryStoreConcurrentAccess:
    """Tests for MemoryStore concurrent access patterns."""

    def test_concurrent_writes(self) -> None:
        """Test concurrent writes from multiple threads."""
        store = MemoryStore()
        num_threads = 10

        def write_step(thread_id: int) -> None:
            store.write(
                "flow1",
                f"run-{thread_id}",
                "step1",
                {"thread": thread_id},
            )

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(write_step, i) for i in range(num_threads)]
            for future in futures:
                future.result()

        for i in range(num_threads):
            assert store.exists("flow1", f"run-{i}", "step1") is True
            location = f"memory://flow1/run-{i}/step1/output.pkl.gz"
            data = store.read(location)
            assert data == {"thread": i}

    def test_concurrent_reads(self) -> None:
        """Test concurrent reads from multiple threads."""
        store = MemoryStore()

        for i in range(10):
            store.write("flow1", "run1", f"step{i}", {"step": i})

        results: list[dict] = []
        lock = threading.Lock()

        def read_step(step_id: int) -> None:
            data = store.read_cached("flow1", "run1", f"step{step_id}")
            with lock:
                results.append(data)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_step, i) for i in range(10)]
            for future in futures:
                future.result()

        assert len(results) == 10
        assert all(r is not None for r in results)

    def test_concurrent_mixed_operations(self) -> None:
        """Test concurrent mix of writes, reads, and exists checks."""
        store = MemoryStore()
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            try:
                for i in range(5):
                    store.write(
                        f"flow{worker_id}",
                        f"run{i}",
                        "step1",
                        {"worker": worker_id, "iteration": i},
                    )
                    store.exists(f"flow{worker_id}", f"run{i}", "step1")
                    location = f"memory://flow{worker_id}/run{i}/step1/output.pkl.gz"
                    store.read(location)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for future in futures:
                future.result()

        assert len(errors) == 0


class TestMemoryStoreEdgeCases:
    """Tests for MemoryStore edge cases."""

    def test_write_large_object(self) -> None:
        """Test writing large objects."""
        store = MemoryStore()
        large_data = {"items": list(range(10000))}

        location = store.write("flow1", "run1", "step1", large_data)
        result = store.read(location)

        assert result == large_data

    def test_write_special_values(self) -> None:
        """Test writing special Python values."""
        store = MemoryStore()

        test_cases = [
            ("none", None),
            ("empty_list", []),
            ("empty_dict", {}),
            ("boolean_true", True),
            ("boolean_false", False),
            ("zero", 0),
            ("empty_string", ""),
        ]

        for name, value in test_cases:
            location = store.write("flow1", "run1", name, value)
            result = store.read(location)
            assert result == value

    def test_unicode_data(self) -> None:
        """Test writing and reading unicode data."""
        store = MemoryStore()
        unicode_data = {"text": "Hello 世界 🌍", "emoji": "🚀🎉"}

        location = store.write("flow1", "run1", "unicode_step", unicode_data)
        result = store.read(location)

        assert result == unicode_data

    def test_get_input_hash_returns_none(self) -> None:
        """Test get_input_hash always returns None in MemoryStore."""
        store = MemoryStore()
        store.write("flow1", "run1", "step1", {"data": "test"}, input_hash="hash123")

        hash_value = store.get_input_hash("flow1", "run1", "step1")
        assert hash_value is None
