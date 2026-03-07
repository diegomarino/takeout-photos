"""Tests for metadata stage error handling."""

from unittest.mock import MagicMock, patch

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.metadata import step_apply_metadata


def test_metadata_failure_leaves_files_pending(tmp_path):
    """When exiftool fails, files should remain in pending state."""
    # Setup
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)

    # Register ZIP and file
    db.register_zip("test.zip")
    db.register_file(
        zip_name="test.zip",
        original_path=str(tmp_path / "photo.jpg"),
        file_size=1000,
        photo_taken_ts=1234567890,
    )

    # Mock exiftool to return failure
    mock_result = MagicMock()
    mock_result.returncode = 1  # Failure

    with patch("takeout_photos.stages.metadata.run_exiftool", return_value=mock_result):
        step_apply_metadata(config, db, "test.zip", MagicMock())

    # Verify files stayed pending
    files = db.get_files_for_zip("test.zip", status="pending")
    assert len(files) == 1

    files = db.get_files_for_zip("test.zip", status="meta_applied")
    assert len(files) == 0


def test_metadata_success_advances_files(tmp_path):
    """When exiftool succeeds, files should advance to meta_applied."""
    # Setup
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)

    # Create test file
    test_file = tmp_path / "extracted" / "photo.jpg"
    test_file.parent.mkdir(parents=True)
    test_file.write_bytes(b"fake photo")

    db.register_zip("test.zip")
    db.register_file(
        zip_name="test.zip",
        original_path=str(test_file),
        file_size=1000,
        photo_taken_ts=1234567890,
    )

    # Mock exiftool to return success
    mock_result = MagicMock()
    mock_result.returncode = 0  # Success

    with patch("takeout_photos.stages.metadata.run_exiftool", return_value=mock_result):
        step_apply_metadata(config, db, "test.zip", MagicMock())

    # Verify files advanced
    files = db.get_files_for_zip("test.zip", status="meta_applied")
    assert len(files) == 1

    # Verify exif_datetime was stored
    assert files[0]["exif_datetime"] is not None
    assert files[0]["exif_datetime"].startswith("2009:")  # 1234567890 is 2009
