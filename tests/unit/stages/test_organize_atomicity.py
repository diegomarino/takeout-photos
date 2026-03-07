"""Tests for organize stage atomicity guarantees."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.organize import step_organize_files_from_zip


def test_organize_moves_before_db_insert(tmp_path):
    """
    Critical test: Ensure file move happens BEFORE insert_organized_file.

    If process crashes after DB insert but before rename, the DB claims the
    file is organized when it's actually still in extracted/. This leads to
    incorrect deduplication. Moving first prevents orphaned DB records.

    This test verifies the fix for CODEX suggestion #28.
    """
    config = Config(workdir=tmp_path)
    config.dry_run = False  # Ensure we actually perform operations
    db = PipelineDB(config.db_path)

    # Setup: Register ZIP and file with hash
    db.register_zip("test.zip")
    db.update_zip_status("test.zip", "extracted")

    source_file = config.extracted_dir / "test.jpg"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"test image content")

    db.register_file(
        zip_name="test.zip",
        original_path=str(source_file),
        file_size=100,
        content_hash="abc123hash",
    )
    db.commit()

    # Mock DB insert to simulate crash after move
    call_order = []

    def tracked_insert(*args, **kwargs):
        call_order.append("insert")
        raise Exception("Simulated crash during DB insert")

    from pathlib import Path as PathlibPath

    original_rename = PathlibPath.rename

    def tracked_rename(self, target):
        call_order.append("rename")
        # Actually perform the rename using the original method
        return original_rename(self, target)

    with patch.object(db, "insert_organized_file", side_effect=tracked_insert):
        with patch("pathlib.Path.rename", tracked_rename):
            try:
                step_organize_files_from_zip(config, db, "test", MagicMock())
            except Exception:
                pass  # Expected crash

    # CRITICAL ASSERTION: rename must happen BEFORE insert
    assert call_order == [
        "rename",
        "insert",
    ], "File move must happen BEFORE DB insert for atomicity"

    # Verify: File was moved even though DB insert failed
    # This is the better failure mode - file is in the right place, just not tracked yet
    assert not db.check_duplicate(
        "abc123hash"
    ), "File should NOT be in organized_files table if insert failed"
