"""
Unit tests for Hashing module.

Tests cover content hashing for deduplication with both xxhash and SHA256.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from takeout_photos.hashing.hasher import compute_hash


class TestComputeHash:
    """Test content hashing functionality."""

    def test_compute_hash_returns_hex_string(self, temp_dir):
        """Should return hex digest string."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        hash_val = compute_hash(file_path)

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0
        # Should be hex characters only
        assert all(c in "0123456789abcdef" for c in hash_val.lower())

    def test_compute_hash_identical_content_produces_same_hash(self, temp_dir):
        """Should produce identical hashes for identical content."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_text("identical content")
        file2.write_text("identical content")

        hash1 = compute_hash(file1)
        hash2 = compute_hash(file2)

        assert hash1 == hash2

    def test_compute_hash_different_content_produces_different_hash(self, temp_dir):
        """Should produce different hashes for different content."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_text("content A")
        file2.write_text("content B")

        hash1 = compute_hash(file1)
        hash2 = compute_hash(file2)

        assert hash1 != hash2

    def test_compute_hash_empty_file(self, temp_dir):
        """Should handle empty files."""
        file_path = temp_dir / "empty.txt"
        file_path.touch()

        hash_val = compute_hash(file_path)

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_compute_hash_binary_file(self, temp_dir):
        """Should handle binary files."""
        file_path = temp_dir / "binary.dat"
        file_path.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        hash_val = compute_hash(file_path)

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_compute_hash_large_file(self, temp_dir):
        """Should handle large files (tests chunked reading)."""
        file_path = temp_dir / "large.dat"

        # Create 200KB file (larger than 64KB chunk size)
        chunk_size = 65536
        data = b"x" * (chunk_size * 3)
        file_path.write_bytes(data)

        hash_val = compute_hash(file_path)

        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    def test_compute_hash_consistent_across_calls(self, temp_dir):
        """Should produce consistent hash across multiple calls."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("consistent content")

        hash1 = compute_hash(file_path)
        hash2 = compute_hash(file_path)
        hash3 = compute_hash(file_path)

        assert hash1 == hash2 == hash3

    def test_compute_hash_different_names_same_content(self, temp_dir):
        """Should produce same hash for files with same content but different names."""
        file1 = temp_dir / "name1.txt"
        file2 = temp_dir / "totally_different_name.txt"

        file1.write_text("same content")
        file2.write_text("same content")

        hash1 = compute_hash(file1)
        hash2 = compute_hash(file2)

        assert hash1 == hash2

    def test_compute_hash_different_extensions_same_content(self, temp_dir):
        """Should produce same hash regardless of file extension."""
        file1 = temp_dir / "file.jpg"
        file2 = temp_dir / "file.png"

        content = b"\x89PNG\r\n\x1a\n"  # PNG header
        file1.write_bytes(content)
        file2.write_bytes(content)

        hash1 = compute_hash(file1)
        hash2 = compute_hash(file2)

        assert hash1 == hash2

    def test_compute_hash_raises_for_nonexistent_file(self, temp_dir):
        """Should raise FileNotFoundError for missing file."""
        file_path = temp_dir / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            compute_hash(file_path)

    def test_compute_hash_single_byte_difference(self, temp_dir):
        """Should detect even single byte differences."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_bytes(b"abcdefgh")
        file2.write_bytes(b"abcdefgi")  # Last byte different

        hash1 = compute_hash(file1)
        hash2 = compute_hash(file2)

        assert hash1 != hash2


class TestHashingWithXXHash:
    """Test hashing with xxhash if available."""

    @pytest.mark.skipif(
        not hasattr(__import__("takeout_photos.hashing.hasher"), "use_xxhash")
        or not __import__("takeout_photos.hashing.hasher").use_xxhash,
        reason="xxhash not available",
    )
    def test_compute_hash_uses_xxhash_when_available(self, temp_dir):
        """Should use xxhash when available."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        hash_val = compute_hash(file_path)

        # xxhash produces 16-character hex digest
        assert len(hash_val) == 16

    def test_compute_hash_with_xxhash_disabled(self, temp_dir):
        """Should fall back to SHA256 when xxhash disabled."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test content")

        # Mock xxhash as unavailable
        with patch("takeout_photos.hashing.hasher.use_xxhash", False):
            with patch("takeout_photos.hashing.hasher.xxhash", None):
                hash_val = compute_hash(file_path)

                # SHA256 produces 64-character hex digest
                assert len(hash_val) == 64


class TestHashingIntegration:
    """Integration tests for hashing module."""

    def test_deduplication_workflow(self, temp_dir):
        """Should identify duplicates in typical workflow."""
        from collections import defaultdict

        # Create test files
        file1 = temp_dir / "photo1.jpg"
        file2 = temp_dir / "photo2.jpg"  # Duplicate of file1
        file3 = temp_dir / "photo3.jpg"  # Unique

        file1.write_bytes(b"image data A")
        file2.write_bytes(b"image data A")  # Same as file1
        file3.write_bytes(b"image data B")  # Different

        # Hash all files
        hash_to_files = defaultdict(list)
        for f in [file1, file2, file3]:
            h = compute_hash(f)
            hash_to_files[h].append(f)

        # Should have 2 unique hashes
        assert len(hash_to_files) == 2

        # One hash should have 2 files (duplicates)
        duplicates = [files for files in hash_to_files.values() if len(files) > 1]
        assert len(duplicates) == 1
        assert len(duplicates[0]) == 2

    def test_hash_stability_across_file_operations(self, temp_dir):
        """Should produce same hash after file is moved or renamed."""
        original = temp_dir / "original.txt"
        original.write_text("stable content")

        hash_original = compute_hash(original)

        # Rename file
        renamed = temp_dir / "renamed.txt"
        original.rename(renamed)

        hash_renamed = compute_hash(renamed)

        assert hash_original == hash_renamed

    def test_large_collection_hashing(self, temp_dir):
        """Should efficiently hash multiple files."""
        files = []
        for i in range(20):
            file_path = temp_dir / f"file{i}.txt"
            file_path.write_text(f"content {i}")
            files.append(file_path)

        # Hash all files
        hashes = [compute_hash(f) for f in files]

        # All hashes should be unique (different content)
        assert len(set(hashes)) == 20

        # All hashes should be strings
        assert all(isinstance(h, str) for h in hashes)

    def test_hash_ignores_modification_time(self, temp_dir):
        """Should produce same hash regardless of modification time."""
        import time

        file_path = temp_dir / "test.txt"
        file_path.write_text("content")

        hash1 = compute_hash(file_path)

        # Wait and modify file timestamp (without changing content)
        time.sleep(0.01)
        file_path.touch()  # Update modification time

        hash2 = compute_hash(file_path)

        # Hash should be unchanged
        assert hash1 == hash2
