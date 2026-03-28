"""
Unit tests for PipelineDB class.

Tests cover schema creation, CRUD operations, JSON file registration,
hash lookups, and pipeline state management.
"""

from __future__ import annotations

import sqlite3

import pytest

from takeout_photos.core.database import PipelineDB


class TestSchemaCreation:
    """Test database schema initialization."""

    def test_init_creates_all_tables(self, db):
        """Should create all required tables on initialization."""
        # Query sqlite_master for table names (exclude sqlite_sequence)
        cursor = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "files",
            "json_files",
            "organized_files",
            "pipeline_state",
            "recovery_log",
            "zips",
        ]
        assert tables == expected_tables

    def test_init_creates_indexes(self, db):
        """Should create all required indexes on initialization."""
        cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = [
            "idx_files_hash",
            "idx_files_status",
            "idx_files_zip",
            "idx_json_filename",
            "idx_json_media_name",
            "idx_json_zip",
        ]

        for expected in expected_indexes:
            assert expected in indexes

    def test_init_is_idempotent(self, test_db_path):
        """Should safely initialize schema multiple times."""
        # Create database twice
        db1 = PipelineDB(test_db_path)
        db1.close()

        # Should not raise error
        db2 = PipelineDB(test_db_path)
        cursor = db2.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        db2.close()

        expected_tables = [
            "files",
            "json_files",
            "organized_files",
            "pipeline_state",
            "recovery_log",
            "zips",
        ]
        assert tables == expected_tables


class TestZipOperations:
    """Test ZIP file tracking operations."""

    def test_register_zip_creates_record(self, db):
        """Should create ZIP record with pending status."""
        db.register_zip("takeout-001.zip")

        status = db.get_zip_status("takeout-001.zip")
        assert status == "pending"

    def test_register_zip_is_idempotent(self, db):
        """Should safely register same ZIP multiple times."""
        db.register_zip("takeout-001.zip")
        db.register_zip("takeout-001.zip")  # Should not raise

        status = db.get_zip_status("takeout-001.zip")
        assert status == "pending"

    def test_update_zip_status_changes_status(self, db):
        """Should update ZIP status successfully."""
        db.register_zip("takeout-001.zip")
        db.update_zip_status("takeout-001.zip", "extracted")

        status = db.get_zip_status("takeout-001.zip")
        assert status == "extracted"

    def test_update_zip_status_with_metadata(self, db):
        """Should update ZIP status and additional fields."""
        db.register_zip("takeout-001.zip")
        db.update_zip_status(
            "takeout-001.zip", "extracted", file_count=1500, extracted_at="2024-01-20"
        )

        row = db.conn.execute("SELECT * FROM zips WHERE name = ?", ("takeout-001.zip",)).fetchone()
        assert row["status"] == "extracted"
        assert row["file_count"] == 1500
        assert row["extracted_at"] == "2024-01-20"

    def test_get_zip_status_returns_none_for_unknown_zip(self, db):
        """Should return None for non-existent ZIP."""
        status = db.get_zip_status("nonexistent.zip")
        assert status is None

    def test_get_pending_zips_returns_pending_and_error(self, db):
        """Should return ZIPs in pending or error state."""
        db.register_zip("pending-001.zip")
        db.register_zip("error-002.zip")
        db.register_zip("extracted-003.zip")

        db.update_zip_status("error-002.zip", "error")
        db.update_zip_status("extracted-003.zip", "extracted")

        pending_zips = db.get_pending_zips()
        assert set(pending_zips) == {"pending-001.zip", "error-002.zip"}

    def test_get_zips_needing_processing_returns_extracted_and_processing(self, db):
        """Should return ZIPs in extracted or processing state."""
        db.register_zip("pending-001.zip")
        db.register_zip("extracted-002.zip")
        db.register_zip("processing-003.zip")

        db.update_zip_status("extracted-002.zip", "extracted")
        db.update_zip_status("processing-003.zip", "processing")

        needing_processing = db.get_zips_needing_processing()
        assert set(needing_processing) == {"extracted-002.zip", "processing-003.zip"}


class TestFileOperations:
    """Test file record CRUD operations."""

    def test_register_file_creates_record(self, db):
        """Should create file record with basic info."""
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg")
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        assert len(files) == 1
        assert files[0]["original_path"] == "/path/to/IMG_1234.jpg"
        assert files[0]["status"] == "pending"

    def test_register_file_with_metadata(self, db):
        """Should create file record with additional metadata."""
        db.register_file(
            "takeout-001.zip",
            "/path/to/IMG_1234.jpg",
            file_size=1024000,
            has_json=1,
            json_path="/path/to/IMG_1234.jpg.json",
        )
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        assert files[0]["file_size"] == 1024000
        assert files[0]["has_json"] == 1
        assert files[0]["json_path"] == "/path/to/IMG_1234.jpg.json"

    def test_register_file_replaces_on_duplicate(self, db):
        """Should replace file record if same zip_name and path."""
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg", file_size=1000)
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg", file_size=2000)
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        assert len(files) == 1
        assert files[0]["file_size"] == 2000

    def test_get_files_for_zip_returns_all_files(self, db):
        """Should return all files for specified ZIP."""
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg")
        db.register_file("takeout-001.zip", "/path/to/IMG_5678.jpg")
        db.register_file("takeout-002.zip", "/path/to/IMG_9999.jpg")
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        assert len(files) == 2

    def test_get_files_for_zip_filters_by_status(self, db):
        """Should return only files with specified status."""
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg")
        db.register_file("takeout-001.zip", "/path/to/IMG_5678.jpg")
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        file_id = files[0]["id"]

        db.update_file(file_id, status="meta_applied")
        db.commit()

        meta_applied_files = db.get_files_for_zip("takeout-001.zip", status="meta_applied")
        pending_files = db.get_files_for_zip("takeout-001.zip", status="pending")

        assert len(meta_applied_files) == 1
        assert len(pending_files) == 1

    def test_update_file_changes_fields(self, db):
        """Should update file fields successfully."""
        db.register_file("takeout-001.zip", "/path/to/IMG_1234.jpg")
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        file_id = files[0]["id"]

        db.update_file(
            file_id, status="organized", content_hash="abc123", final_path="2023/2023_05/photo.jpg"
        )
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        assert files[0]["status"] == "organized"
        assert files[0]["content_hash"] == "abc123"
        assert files[0]["final_path"] == "2023/2023_05/photo.jpg"


class TestJSONFileOperations:
    """Test JSON metadata file registration and lookup."""

    def test_register_json_file_creates_record(self, db):
        """Should register JSON file with derived base media name."""
        db.register_json_file("takeout-001.zip", "/path/to/IMG_1234.HEIC.json")
        db.commit()

        row = db.conn.execute(
            "SELECT * FROM json_files WHERE zip_name = ?", ("takeout-001.zip",)
        ).fetchone()
        assert row["filename"] == "IMG_1234.HEIC.json"
        assert row["base_media_name"] == "IMG_1234.HEIC"

    def test_register_json_file_handles_supplemental_metadata(self, db):
        """Should strip .supplemental-metadata.json suffix."""
        db.register_json_file(
            "takeout-001.zip", "/path/to/IMG_1234.HEIC.supplemental-metadata.json"
        )
        db.commit()

        row = db.conn.execute(
            "SELECT * FROM json_files WHERE zip_name = ?", ("takeout-001.zip",)
        ).fetchone()
        assert row["base_media_name"] == "IMG_1234.HEIC"

    def test_register_json_file_handles_truncated_suffixes(self, db):
        """Should strip truncated JSON suffixes correctly."""
        test_cases = [
            ("IMG_1234.HEIC.supplemental-metada.json", "IMG_1234.HEIC"),
            ("IMG_1234.HEIC.supplemental-meta.json", "IMG_1234.HEIC"),
            ("IMG_1234.HEIC.supplemental.json", "IMG_1234.HEIC"),
            ("IMG_1234.HEIC.supp.json", "IMG_1234.HEIC"),
        ]

        for i, (json_name, _expected_base) in enumerate(test_cases):
            db.register_json_file(f"takeout-00{i}.zip", f"/path/to/{json_name}")
        db.commit()

        for i, (_json_name, expected_base) in enumerate(test_cases):
            row = db.conn.execute(
                "SELECT base_media_name FROM json_files WHERE zip_name = ?",
                (f"takeout-00{i}.zip",),
            ).fetchone()
            assert row["base_media_name"] == expected_base

    def test_find_json_for_media_db_exact_match(self, db):
        """Should find JSON by exact base_media_name match."""
        db.register_json_file("takeout-001.zip", "/path/to/IMG_1234.HEIC.json")
        db.commit()

        json_path = db.find_json_for_media_db("IMG_1234.HEIC")
        assert json_path == "/path/to/IMG_1234.HEIC.json"

    def test_find_json_for_media_db_numbered_suffix(self, db):
        """Should find JSON with numbered suffix (1), (2), etc."""
        db.register_json_file("takeout-001.zip", "/path/to/IMG_1234(1).HEIC.json")
        db.commit()

        json_path = db.find_json_for_media_db("/path/to/IMG_1234.HEIC")
        assert json_path == "/path/to/IMG_1234(1).HEIC.json"

    def test_find_json_for_media_db_truncated_filename(self, db):
        """Should find JSON for truncated media filename (>46 chars)."""
        long_name = "A" * 50 + ".HEIC"
        truncated_json = "A" * 46 + ".HEIC.json"

        db.register_json_file("takeout-001.zip", f"/path/to/{truncated_json}")
        db.commit()

        json_path = db.find_json_for_media_db(f"/path/to/{long_name}")
        assert json_path == f"/path/to/{truncated_json}"

    def test_find_json_for_media_db_returns_none_when_not_found(self, db):
        """Should return None when no JSON file matches."""
        json_path = db.find_json_for_media_db("/path/to/IMG_NONEXISTENT.HEIC")
        assert json_path is None


class TestHashOperations:
    """Test content hash operations for deduplication."""

    def test_get_all_hashes_returns_empty_for_no_files(self, db):
        """Should return empty dict when no files have hashes."""
        hashes = db.get_all_hashes()
        assert hashes == {}

    def test_get_all_hashes_returns_first_file_id_per_hash(self, db):
        """Should map each hash to its first (lowest) file ID."""
        db.register_file("takeout-001.zip", "/path/to/file1.jpg", content_hash="abc123")
        db.register_file("takeout-001.zip", "/path/to/file2.jpg", content_hash="abc123")
        db.register_file("takeout-001.zip", "/path/to/file3.jpg", content_hash="def456")
        db.commit()

        files = db.get_files_for_zip("takeout-001.zip")
        file_ids = sorted([f["id"] for f in files])

        hashes = db.get_all_hashes()
        assert hashes["abc123"] == file_ids[0]  # First file with abc123
        assert hashes["def456"] == file_ids[2]  # File with def456

    def test_get_all_hashes_ignores_null_hashes(self, db):
        """Should exclude files without content hashes."""
        db.register_file("takeout-001.zip", "/path/to/file1.jpg", content_hash="abc123")
        db.register_file("takeout-001.zip", "/path/to/file2.jpg")  # No hash
        db.commit()

        hashes = db.get_all_hashes()
        assert len(hashes) == 1
        assert "abc123" in hashes


class TestPipelineState:
    """Test global pipeline state management."""

    def test_get_state_returns_default_for_missing_key(self, db):
        """Should return default value when key doesn't exist."""
        value = db.get_state("nonexistent_key", default="default_value")
        assert value == "default_value"

    def test_get_state_returns_none_when_no_default(self, db):
        """Should return None when key doesn't exist and no default."""
        value = db.get_state("nonexistent_key")
        assert value is None

    def test_set_and_get_state_stores_value(self, db):
        """Should store and retrieve state values."""
        db.set_state("test_key", "test_value")

        value = db.get_state("test_key")
        assert value == "test_value"

    def test_set_state_replaces_existing_value(self, db):
        """Should replace existing state value."""
        db.set_state("test_key", "old_value")
        db.set_state("test_key", "new_value")

        value = db.get_state("test_key")
        assert value == "new_value"


class TestDatabaseLifecycle:
    """Test database connection lifecycle."""

    def test_close_closes_connection(self, test_db_path):
        """Should close database connection successfully."""
        db = PipelineDB(test_db_path)
        db.close()

        # Attempting to use closed connection should raise
        with pytest.raises((sqlite3.ProgrammingError, Exception)):
            db.conn.execute("SELECT 1")

    def test_commit_persists_changes(self, test_db_path):
        """Should persist uncommitted changes when commit() is called."""
        db = PipelineDB(test_db_path)
        db.register_file("takeout-001.zip", "/path/to/file.jpg")
        db.commit()
        db.close()

        # Reopen and verify data persisted
        db2 = PipelineDB(test_db_path)
        files = db2.get_files_for_zip("takeout-001.zip")
        assert len(files) == 1
        db2.close()


class TestOrganizedFiles:
    """Test organized_files table and deduplication operations (v3.0)."""

    def test_create_organized_files_table(self, db):
        """Should create organized_files table on initialization."""
        # Query sqlite_master for table existence
        cursor = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='organized_files'"
        )
        table = cursor.fetchone()

        assert table is not None
        assert table["name"] == "organized_files"

    def test_organized_files_has_correct_schema(self, db):
        """Should have correct columns in organized_files table."""
        cursor = db.conn.execute("PRAGMA table_info(organized_files)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            "hash",
            "original_name",
            "final_path",
            "organized_at",
            "source_zip",
            "file_size",
        }
        assert columns == expected_columns

    def test_organized_files_has_indexes(self, db):
        """Should create indexes for organized_files table."""
        cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_organized_hash" in indexes
        assert "idx_organized_zip" in indexes

    def test_insert_organized_file_creates_record(self, db):
        """Should insert organized file record successfully."""
        db.insert_organized_file(
            hash="abc123def456",
            original_name="IMG_1234.jpg",
            final_path="2020/01/IMG_1234.jpg",
            source_zip="takeout-001.zip",
            file_size=5242880,
        )

        # Verify record exists
        row = db.conn.execute(
            "SELECT * FROM organized_files WHERE hash = ?", ("abc123def456",)
        ).fetchone()

        assert row is not None
        assert row["hash"] == "abc123def456"
        assert row["original_name"] == "IMG_1234.jpg"
        assert row["final_path"] == "2020/01/IMG_1234.jpg"
        assert row["source_zip"] == "takeout-001.zip"
        assert row["file_size"] == 5242880
        assert row["organized_at"] is not None

    def test_insert_organized_file_ignores_duplicate_hash(self, db):
        """Should safely handle duplicate hash insertions."""
        db.insert_organized_file(
            hash="duplicate_hash",
            original_name="IMG_1234.jpg",
            final_path="2020/01/IMG_1234.jpg",
            source_zip="takeout-001.zip",
            file_size=1000,
        )

        # Try to insert same hash again
        db.insert_organized_file(
            hash="duplicate_hash",
            original_name="IMG_5678.jpg",
            final_path="2020/02/IMG_5678.jpg",
            source_zip="takeout-002.zip",
            file_size=2000,
        )

        # Should keep only first record
        rows = db.conn.execute(
            "SELECT * FROM organized_files WHERE hash = ?", ("duplicate_hash",)
        ).fetchall()

        assert len(rows) == 1
        assert rows[0]["original_name"] == "IMG_1234.jpg"  # First insert preserved

    def test_check_duplicate_returns_false_for_new_hash(self, db):
        """Should return False for hash that doesn't exist."""
        is_duplicate = db.check_duplicate("nonexistent_hash")
        assert is_duplicate is False

    def test_check_duplicate_returns_true_for_existing_hash(self, db):
        """Should return True for hash that already exists."""
        # Insert a file
        db.insert_organized_file(
            hash="existing_hash",
            original_name="IMG_9999.jpg",
            final_path="2021/05/IMG_9999.jpg",
            source_zip="takeout-001.zip",
            file_size=3000000,
        )

        # Check if it's a duplicate
        is_duplicate = db.check_duplicate("existing_hash")
        assert is_duplicate is True

    def test_check_duplicate_workflow(self, db):
        """Should support typical deduplication workflow."""
        test_hash = "workflow_hash_123"

        # First file - should not be duplicate
        assert db.check_duplicate(test_hash) is False

        # Organize the file
        db.insert_organized_file(
            hash=test_hash,
            original_name="photo.jpg",
            final_path="2022/03/photo.jpg",
            source_zip="takeout-001.zip",
            file_size=1500000,
        )

        # Second file with same hash - should be duplicate
        assert db.check_duplicate(test_hash) is True

    def test_organized_files_tracks_multiple_zips(self, db):
        """Should track files from multiple source ZIPs."""
        db.insert_organized_file(
            hash="hash1",
            original_name="file1.jpg",
            final_path="2020/01/file1.jpg",
            source_zip="takeout-001.zip",
            file_size=1000,
        )
        db.insert_organized_file(
            hash="hash2",
            original_name="file2.jpg",
            final_path="2020/02/file2.jpg",
            source_zip="takeout-002.zip",
            file_size=2000,
        )
        db.insert_organized_file(
            hash="hash3",
            original_name="file3.jpg",
            final_path="2020/03/file3.jpg",
            source_zip="takeout-001.zip",
            file_size=3000,
        )

        # Query by source ZIP
        rows = db.conn.execute(
            "SELECT * FROM organized_files WHERE source_zip = ? ORDER BY hash",
            ("takeout-001.zip",),
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]["hash"] == "hash1"
        assert rows[1]["hash"] == "hash3"


class TestRecoveryLog:
    """Test recovery_log table for auditing recovery operations."""

    def test_recovery_log_table_created(self, db):
        """Test recovery_log table is created in schema."""
        # Check table exists
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recovery_log'"
        ).fetchall()

        assert len(tables) == 1, "recovery_log table should exist"

        # Check indexes exist
        indexes = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='recovery_log'"
        ).fetchall()

        index_names = {idx[0] for idx in indexes}
        assert "idx_recovery_timestamp" in index_names
        assert "idx_recovery_type" in index_names


def test_log_recovery(tmp_path):
    """Test logging recovery action."""
    from takeout_photos.core.database import PipelineDB

    db_path = tmp_path / "test.db"
    db = PipelineDB(db_path)

    # Log recovery
    db.log_recovery(
        recovery_type="zip_reset",
        affected_count=2,
        details={"zip_name": "test.zip", "from_status": "extracting"},
    )

    # Verify record exists
    records = db.conn.execute("SELECT * FROM recovery_log").fetchall()
    assert len(records) == 1

    record = dict(records[0])
    assert record["recovery_type"] == "zip_reset"
    assert record["affected_count"] == 2
    assert "test.zip" in record["details"]


def test_get_recovery_history(tmp_path):
    """Test retrieving recovery history."""
    import time

    from takeout_photos.core.database import PipelineDB

    db_path = tmp_path / "test.db"
    db = PipelineDB(db_path)

    # Log multiple recoveries
    db.log_recovery("zip_reset", 1, {"zip": "1"})
    time.sleep(0.01)  # Ensure different timestamps
    db.log_recovery("orphaned_organized", 5, {"sample": "files"})
    time.sleep(0.01)
    db.log_recovery("missing_files", 2, {})

    # Get history (most recent first)
    history = db.get_recovery_history(limit=10)

    assert len(history) == 3
    assert history[0]["recovery_type"] == "missing_files"  # Most recent
    assert history[1]["recovery_type"] == "orphaned_organized"
    assert history[2]["recovery_type"] == "zip_reset"

    # Test limit
    history = db.get_recovery_history(limit=2)
    assert len(history) == 2
