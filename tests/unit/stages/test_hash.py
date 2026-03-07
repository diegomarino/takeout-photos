"""Tests for content hashing stage."""

from __future__ import annotations

from unittest.mock import MagicMock

from takeout_photos.stages.hash import _compute_hash_worker, step_compute_hashes


class TestComputeHashWorker:
    """Test the parallel hash worker function."""

    def test_compute_hash_worker_success(self, tmp_path):
        """Test successful hash computation."""
        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"test content")

        file_record = {"id": 1, "original_path": str(test_file)}

        file_id, hash_value, error = _compute_hash_worker(file_record)

        assert file_id == 1
        assert hash_value is not None
        assert error is None
        assert len(hash_value) > 0

    def test_compute_hash_worker_file_not_found(self):
        """Test worker with non-existent file."""
        file_record = {"id": 1, "original_path": "/nonexistent/file.jpg"}

        file_id, hash_value, error = _compute_hash_worker(file_record)

        assert file_id == 1
        assert hash_value is None
        assert error is not None
        assert "No such file" in error or "not found" in error.lower()


class TestStepComputeHashes:
    """Test the hash computation stage."""

    def test_compute_hashes_no_files_to_hash(self, config, db, logger):
        """Test when all files already have hashes."""
        # Mock get_files_for_zip to return files with hashes
        db.get_files_for_zip = MagicMock(return_value=[{"id": 1, "content_hash": "abc123"}])

        step_compute_hashes(config, db, "test.zip", logger)

        # Should not update any files
        db.update_file.assert_not_called()

    def test_compute_hashes_with_files(self, config, db, logger, tmp_path):
        """Test hashing files without hashes."""
        # Create test files
        file1 = tmp_path / "file1.jpg"
        file1.write_bytes(b"content1")
        file2 = tmp_path / "file2.jpg"
        file2.write_bytes(b"content2")

        # Mock get_files_for_zip
        db.get_files_for_zip = MagicMock(
            return_value=[
                {"id": 1, "content_hash": None, "original_path": str(file1)},
                {"id": 2, "content_hash": None, "original_path": str(file2)},
            ]
        )

        step_compute_hashes(config, db, "test.zip", logger)

        # Should update both files
        assert db.update_file.call_count == 2
        db.commit.assert_called_once()

    def test_compute_hashes_mixed_files(self, config, db, logger, tmp_path):
        """Test with mix of hashed and unhashed files."""
        # Create test file
        test_file = tmp_path / "file.jpg"
        test_file.write_bytes(b"content")

        # Mock get_files_for_zip - mix of hashed and unhashed
        db.get_files_for_zip = MagicMock(
            return_value=[
                {"id": 1, "content_hash": "existing", "original_path": str(test_file)},
                {"id": 2, "content_hash": None, "original_path": str(test_file)},
            ]
        )

        step_compute_hashes(config, db, "test.zip", logger)

        # Should only update file without hash
        assert db.update_file.call_count == 1
        db.commit.assert_called_once()

    def test_compute_hashes_with_errors(self, config, db, logger):
        """Test handling of hash computation errors."""
        # Mock get_files_for_zip with non-existent file
        db.get_files_for_zip = MagicMock(
            return_value=[{"id": 1, "content_hash": None, "original_path": "/nonexistent.jpg"}]
        )

        step_compute_hashes(config, db, "test.zip", logger)

        # Should mark file as error when hash computation fails
        db.update_file.assert_called_once()
        call_args = db.update_file.call_args
        assert call_args[0][0] == 1  # file_id
        assert call_args[1]["status"] == "error"
        assert "Hash computation failed" in call_args[1]["error_msg"]
        db.commit.assert_called_once()
