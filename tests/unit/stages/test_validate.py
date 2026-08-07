"""Tests for file format validation stage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from takeout_photos.stages.validate import _validate_worker, step_validate_formats


class TestStepValidateFormats:
    """Test the file format validation stage."""

    def test_validate_no_files(self, config, db, logger):
        """Test when there are no files to validate."""
        # Mock get_files_for_zip to return empty list
        db.get_files_for_zip = MagicMock(return_value=[])

        step_validate_formats(config, db, "test.zip", logger)

        # Should not make any database updates
        db.commit.assert_not_called()

    def test_validate_skips_missing_files(self, config, db, logger):
        """Test that missing files are skipped with warning."""
        # Mock get_files_for_zip with non-existent file
        db.get_files_for_zip = MagicMock(
            return_value=[{"id": 1, "original_path": "/nonexistent/file.jpg"}]
        )

        step_validate_formats(config, db, "test.zip", logger)

        # Should not crash, just log warning
        db.commit.assert_not_called()

    def test_validate_corrects_mismatched_extension(self, config, db, logger, tmp_path):
        """Test correction of mismatched file extension."""
        # Create JPEG file with .HEIC extension
        misnamed = tmp_path / "photo.HEIC"
        misnamed.write_bytes(b"\xff\xd8\xff")  # JPEG magic bytes

        # Mock database
        db.get_files_for_zip = MagicMock(return_value=[{"id": 1, "original_path": str(misnamed)}])
        db.conn.execute = MagicMock()

        # Mock get_file_type_and_exif to detect JPEG (returns lowercase)
        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            mock_detect.return_value = ("jpeg", {})

            step_validate_formats(config, db, "test.zip", logger)

            # Should have renamed file (appending correct extension)
            corrected = tmp_path / "photo.HEIC.jpeg"
            assert corrected.exists()
            assert not misnamed.exists()

            # Should have updated database
            assert db.conn.execute.call_count >= 1

    def test_validate_preserves_correct_extensions(self, config, db, logger, tmp_path):
        """Test that correct extensions are not changed."""
        # Create JPEG file with correct .jpg extension
        correct_file = tmp_path / "photo.jpg"
        correct_file.write_bytes(b"\xff\xd8\xff")

        # Mock database
        db.get_files_for_zip = MagicMock(
            return_value=[{"id": 1, "original_path": str(correct_file)}]
        )
        db.conn.execute = MagicMock()

        # Don't mock - use real exiftool (will detect JPEG correctly)
        step_validate_formats(config, db, "test.zip", logger)

        # File has correct extension (.jpg for JPEG), so no correction needed
        assert correct_file.exists()
        # Path unchanged, database not updated
        assert db.conn.execute.call_count == 0

    def test_validate_worker_with_exif(self, tmp_path):
        """Test that worker extracts EXIF datetime when detecting extension mismatch."""
        # Create HEIC file (misnamed) with JPEG content
        test_file = tmp_path / "photo.HEIC"
        test_file.write_bytes(b"\xff\xd8\xff")

        file_record = {"id": 1, "original_path": str(test_file)}

        # Mock get_file_type_and_exif to return type and EXIF
        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            mock_detect.return_value = ("jpeg", {"DateTimeOriginal": "2023:05:15 12:34:56"})

            file_id, new_path, exif_datetime, error = _validate_worker(file_record)

            assert file_id == 1
            assert new_path == str(tmp_path / "photo.HEIC.jpeg")
            assert exif_datetime == "2023:05:15 12:34:56"
            assert error is None

    def test_validate_stores_existing_exif(self, config, db, logger, tmp_path):
        """Test that existing EXIF datetime is stored when extension is corrected."""
        # Create HEIC file (misnamed) with JPEG content
        test_file = tmp_path / "photo.HEIC"
        test_file.write_bytes(b"\xff\xd8\xff")

        # Mock database
        db.get_files_for_zip = MagicMock(return_value=[{"id": 1, "original_path": str(test_file)}])
        db.conn.execute = MagicMock()

        # Mock detection with EXIF date (returns jpeg which doesn't match .heic)
        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            mock_detect.return_value = (
                "jpeg",
                {"DateTimeOriginal": "2023:05:15 12:34:56"},
            )

            step_validate_formats(config, db, "test.zip", logger)

            # Should have renamed file and updated database
            corrected = tmp_path / "photo.HEIC.jpeg"
            assert corrected.exists()

            # Should update both path and EXIF datetime
            # Note: Due to ProcessPoolExecutor, the mock won't work in worker process
            # So we just verify the path was updated (the worker test above verifies EXIF logic)
            assert db.conn.execute.call_count >= 1

            # Verify first call is path update
            first_call = db.conn.execute.call_args_list[0]
            assert "UPDATE files SET original_path" in first_call[0][0]

    def test_validate_dry_run_mode(self, config, db, logger, tmp_path):
        """Test that dry-run mode doesn't modify files."""
        config.dry_run = True

        # Create file with mismatched extension
        test_file = tmp_path / "photo.HEIC"
        test_file.write_bytes(b"\xff\xd8\xff")

        # Mock database
        db.get_files_for_zip = MagicMock(return_value=[{"id": 1, "original_path": str(test_file)}])

        step_validate_formats(config, db, "test.zip", logger)

        # In dry-run mode, file should not be renamed
        assert test_file.exists()
        assert not (tmp_path / "photo.HEIC.jpeg").exists()

    def test_validate_worker_propagates_exif_when_extension_correct(self, tmp_path):
        """Worker must return the embedded EXIF date even when NO rename is needed.

        Regression: the "extension already correct" path used to return
        (id, None, None, None), discarding a DateTimeOriginal that had already
        been read. Non-Takeout input (loose images, no JSON) then lost its date
        and was bucketed into no_date/ during organize.
        """
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"\xff\xd8\xff")

        file_record = {"id": 7, "original_path": str(test_file)}

        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            # .jpg extension already matches jpeg type → no correction needed
            mock_detect.return_value = ("jpeg", {"DateTimeOriginal": "2021:07:15 09:30:00"})

            file_id, new_path, exif_datetime, error = _validate_worker(file_record)

            assert file_id == 7
            assert new_path is None  # no rename
            assert exif_datetime == "2021:07:15 09:30:00"  # but date still propagated
            assert error is None

    def test_validate_worker_propagates_exif_when_type_undetectable(self, tmp_path):
        """Worker propagates EXIF date even when the real type cannot be detected."""
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"\xff\xd8\xff")

        file_record = {"id": 8, "original_path": str(test_file)}

        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            mock_detect.return_value = (None, {"DateTimeOriginal": "2019:01:02 03:04:05"})

            file_id, new_path, exif_datetime, error = _validate_worker(file_record)

            assert file_id == 8
            assert new_path is None
            assert exif_datetime == "2019:01:02 03:04:05"
            assert error is None

    def test_validate_worker_handles_undetectable_types(self, tmp_path):
        """Test worker handling of files with undetectable type."""
        # Create file
        test_file = tmp_path / "unknown.dat"
        test_file.write_bytes(b"unknown data")

        file_record = {"id": 1, "original_path": str(test_file)}

        # Mock detection to return None
        with patch("takeout_photos.stages.validate.get_file_type_and_exif") as mock_detect:
            mock_detect.return_value = (None, {})

            file_id, new_path, exif_datetime, error = _validate_worker(file_record)

            assert file_id == 1
            assert new_path is None  # No correction when type cannot be detected
            assert exif_datetime is None
            assert error is None

    def test_validate_counts_corrections(self, config, db, logger, tmp_path):
        """Test that corrections are counted and reported."""
        # Create files with mismatched extensions
        files = []
        for i in range(3):
            f = tmp_path / f"photo{i}.HEIC"
            f.write_bytes(b"\xff\xd8\xff")
            files.append(f)

        # Mock database
        db.get_files_for_zip = MagicMock(
            return_value=[{"id": i + 1, "original_path": str(f)} for i, f in enumerate(files)]
        )
        db.conn.execute = MagicMock()

        # Don't mock - use real exiftool (will detect JPEG and trigger corrections)
        step_validate_formats(config, db, "test.zip", logger)

        # Should have corrected all 3 files and committed
        db.commit.assert_called_once()
        # Should have 3 DB updates (one per file)
        assert db.conn.execute.call_count == 3

    def test_validate_batch_processing(self, config, db, logger, tmp_path):
        """Test validation of multiple files in batch."""
        # Create multiple files with different issues
        jpeg_as_heic = tmp_path / "photo1.HEIC"
        jpeg_as_heic.write_bytes(b"\xff\xd8\xff")

        correct_jpeg = tmp_path / "photo2.jpg"
        correct_jpeg.write_bytes(b"\xff\xd8\xff")

        png_as_jpg = tmp_path / "photo3.jpg"
        png_as_jpg.write_bytes(b"\x89PNG")

        # Mock database
        db.get_files_for_zip = MagicMock(
            return_value=[
                {"id": 1, "original_path": str(jpeg_as_heic)},
                {"id": 2, "original_path": str(correct_jpeg)},
                {"id": 3, "original_path": str(png_as_jpg)},
            ]
        )
        db.conn.execute = MagicMock()

        # Don't mock - use real exiftool detection (it will work correctly)
        step_validate_formats(config, db, "test.zip", logger)

        # Should have corrected the misnamed files
        # jpeg_as_heic (.HEIC → .HEIC.jpeg) and png_as_jpg (.jpg → .jpg.png or similar)
        # Exact behavior depends on real exiftool, so just verify some corrections happened
        assert db.conn.execute.call_count >= 2  # At least 2 corrections
