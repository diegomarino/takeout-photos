"""
Unit tests for deduplication module (v3.0 incremental mode).

In v3.0, deduplication happens per-file during organization,
not as a global batch operation.
"""

from __future__ import annotations

from takeout_photos.stages.dedupe import check_if_duplicate


class TestCheckIfDuplicate:
    """Test per-file deduplication check (v3.0)."""

    def test_check_if_duplicate_returns_false_for_new_hash(self, real_db):
        """Should return False for hash that doesn't exist in organized_files."""
        is_dup = check_if_duplicate("nonexistent_hash_123", real_db)
        assert is_dup is False

    def test_check_if_duplicate_returns_true_for_existing_hash(self, real_db):
        """Should return True for hash that exists in organized_files."""
        # Insert a file into organized_files
        real_db.insert_organized_file(
            hash="existing_hash_456",
            original_name="IMG_1234.jpg",
            final_path="2020/01/IMG_1234.jpg",
            source_zip="takeout-001.zip",
            file_size=5242880,
        )

        # Check if it's a duplicate
        is_dup = check_if_duplicate("existing_hash_456", real_db)
        assert is_dup is True

    def test_check_if_duplicate_workflow(self, real_db):
        """Should support typical deduplication workflow."""
        test_hash = "workflow_hash_789"

        # First check - should not be duplicate
        assert check_if_duplicate(test_hash, real_db) is False

        # Organize the first file
        real_db.insert_organized_file(
            hash=test_hash,
            original_name="photo.jpg",
            final_path="2021/03/photo.jpg",
            source_zip="takeout-001.zip",
            file_size=1500000,
        )

        # Second check - should be duplicate now
        assert check_if_duplicate(test_hash, real_db) is True

    def test_check_if_duplicate_with_multiple_hashes(self, real_db):
        """Should correctly identify duplicates among multiple hashes."""
        # Insert several files
        real_db.insert_organized_file(
            hash="hash_a",
            original_name="file_a.jpg",
            final_path="2020/01/file_a.jpg",
            source_zip="takeout-001.zip",
            file_size=1000000,
        )
        real_db.insert_organized_file(
            hash="hash_b",
            original_name="file_b.jpg",
            final_path="2020/02/file_b.jpg",
            source_zip="takeout-002.zip",
            file_size=2000000,
        )

        # Check each hash
        assert check_if_duplicate("hash_a", real_db) is True
        assert check_if_duplicate("hash_b", real_db) is True
        assert check_if_duplicate("hash_c", real_db) is False  # Not inserted

    def test_check_if_duplicate_case_sensitive(self, real_db):
        """Should treat hash comparison as case-sensitive."""
        real_db.insert_organized_file(
            hash="abc123DEF",
            original_name="file.jpg",
            final_path="2020/01/file.jpg",
            source_zip="takeout-001.zip",
            file_size=1000000,
        )

        # Exact match should be duplicate
        assert check_if_duplicate("abc123DEF", real_db) is True

        # Different case should not be duplicate
        assert check_if_duplicate("abc123def", real_db) is False
        assert check_if_duplicate("ABC123DEF", real_db) is False
