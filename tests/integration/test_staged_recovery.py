"""Integration tests for staged state recovery."""

import shutil
from unittest.mock import MagicMock

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.recovery import RecoveryManager


def test_recovery_completes_staged_with_moved_file(tmp_path):
    """Recovery should complete staging when file was moved successfully."""
    # Setup
    config = Config(workdir=tmp_path)
    config.organized_dir.mkdir(parents=True, exist_ok=True)
    config.extracted_dir.mkdir(parents=True, exist_ok=True)
    db = PipelineDB(config.db_path)

    # Create file and register
    extracted_file = config.extracted_dir / "photo.jpg"
    extracted_file.write_text("fake photo")

    db.register_zip("test.zip")
    db.register_file(
        zip_name="test.zip",
        original_path=str(extracted_file),
        file_size=10,
        content_hash="abc123",
    )

    # Simulate crash: file moved but DB not updated
    staged_path = "2020/05/photo.jpg"
    organized_file = config.organized_dir / staged_path
    organized_file.parent.mkdir(parents=True)
    shutil.move(str(extracted_file), str(organized_file))

    # Mark as staged in DB
    file_id = db.conn.execute(
        "SELECT id FROM files WHERE original_path = ?", (str(extracted_file),)
    ).fetchone()["id"]
    db.update_file(file_id, status="staged", staged_path=staged_path)
    db.commit()

    # Run recovery
    recovery = RecoveryManager(config, db, MagicMock())
    stats = recovery.check_and_recover()

    # Verify recovery completed staging
    assert stats.staged_files == 1

    file = db.conn.execute(
        "SELECT status, final_path FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    assert file["status"] == "organized"
    assert file["final_path"] == staged_path

    # Verify file registered in organized_files
    organized = db.conn.execute(
        "SELECT * FROM organized_files WHERE hash = ?", ("abc123",)
    ).fetchone()
    assert organized is not None


def test_recovery_reverts_staged_without_moved_file(tmp_path):
    """Recovery should revert to pending when file wasn't moved."""
    # Setup
    config = Config(workdir=tmp_path)
    config.organized_dir.mkdir(parents=True, exist_ok=True)
    config.extracted_dir.mkdir(parents=True, exist_ok=True)
    db = PipelineDB(config.db_path)

    # Create file
    extracted_file = config.extracted_dir / "photo.jpg"
    extracted_file.write_text("fake photo")

    db.register_zip("test.zip")
    db.register_file(
        zip_name="test.zip",
        original_path=str(extracted_file),
        file_size=10,
        content_hash="abc123",
    )

    # Simulate crash: DB updated but file not moved
    file_id = db.conn.execute(
        "SELECT id FROM files WHERE original_path = ?", (str(extracted_file),)
    ).fetchone()["id"]
    db.update_file(file_id, status="staged", staged_path="2020/05/photo.jpg")
    db.commit()

    # Run recovery
    recovery = RecoveryManager(config, db, MagicMock())
    stats = recovery.check_and_recover()

    # Verify recovery reverted to pending
    assert stats.staged_files == 1

    file = db.conn.execute(
        "SELECT status, staged_path FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    assert file["status"] == "pending"
    assert file["staged_path"] is None
