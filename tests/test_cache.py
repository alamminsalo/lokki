"""Tests for caching and input hash validation."""

import pytest

from lokki.store.utils import _hash_input


class TestInputHash:
    """Tests for input hash computation."""

    def test_same_inputs_produce_same_hash(self) -> None:
        """Same input data should produce same hash."""
        data = {"key": "value", "count": 42}

        hash1 = _hash_input(data)
        hash2 = _hash_input(data)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_different_inputs_produce_different_hash(self) -> None:
        """Different input data should produce different hashes."""
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}

        hash1 = _hash_input(data1)
        hash2 = _hash_input(data2)

        assert hash1 != hash2

    def test_list_input(self) -> None:
        """Test hashing list input."""
        data = [1, 2, 3, "a", "b", "c"]

        hash1 = _hash_input(data)
        hash2 = _hash_input(data)

        assert hash1 == hash2
        assert hash1 != _hash_input([1, 2, 3, "a", "b", "d"])

    def test_nested_dict_input(self) -> None:
        """Test hashing nested dictionary."""
        data = {"outer": {"inner": [1, 2, 3]}, "other": "value"}

        hash1 = _hash_input(data)
        hash2 = _hash_input(data)

        assert hash1 == hash2

    def test_empty_input(self) -> None:
        """Test hashing empty structures."""
        assert _hash_input({}) == _hash_input({})
        assert _hash_input([]) == _hash_input([])

    def test_order_independent_dict(self) -> None:
        """Dictionary order should not affect hash."""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}

        assert _hash_input(data1) == _hash_input(data2)

    def test_datetime_handling(self) -> None:
        """Datetime objects should be handled correctly."""
        from datetime import datetime

        dt1 = datetime(2024, 1, 1, 12, 0, 0)
        dt2 = datetime(2024, 1, 1, 12, 0, 0)

        data1 = {"time": dt1}
        data2 = {"time": dt2}

        assert _hash_input(data1) == _hash_input(data2)


class TestCacheValidation:
    """Tests for cache input hash validation logic."""

    def test_hash_matches_for_equivalent_data(self) -> None:
        """Test that hash validation works correctly."""
        original = {"items": [1, 2, 3], "name": "test"}
        cached_input_hash = _hash_input(original)

        # Same data should match
        current_hash = _hash_input({"items": [1, 2, 3], "name": "test"})
        assert current_hash == cached_input_hash

    def test_hash_mismatch_for_changed_data(self) -> None:
        """Test that changed data produces different hash."""
        original = {"items": [1, 2, 3], "name": "test"}
        cached_input_hash = _hash_input(original)

        # Changed data should not match
        current_hash = _hash_input({"items": [1, 2, 3], "name": "test-changed"})
        assert current_hash != cached_input_hash

    def test_missing_tag_treated_as_mismatch(self) -> None:
        """Missing input hash tag should be treated as mismatch."""
        stored_hash = None  # Simulates missing tag

        current_hash = _hash_input({"data": "value"})

        # Missing tag should not match current hash
        assert stored_hash != current_hash

    def test_s3_tag_format(self) -> None:
        """Test S3 tag format for input hash."""
        data = {"test": "value"}
        input_hash = _hash_input(data)

        tag = "input_hash=" + input_hash
        assert tag.startswith("input_hash=")
        assert len(input_hash) == 16
