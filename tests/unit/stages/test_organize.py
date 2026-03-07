"""
Unit tests for organization module (v3.0.1 merge-extract mode).

In v3.0.1, all ZIPs extract to same directory with inline deduplication.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from takeout_photos.stages.organize import step_organize_files_from_zip


class TestStepOrganizeFilesFromZip:
    """Test per-ZIP organization with deduplication (v3.0)."""

    def test_organize_no_files_returns_zero_stats(self, config, real_db, logger):
        """Should return zeros when no files with hashes found."""
        stats = step_organize_files_from_zip(config, real_db, "nonexistent-zip", logger)

        assert stats["organized"] == 0
        assert stats["duplicates"] == 0
        assert stats["errors"] == 0

    def test_organize_unique_file_to_organized_dir(self, config, real_db, logger, tmp_path):
        """Should organize unique file to organized_dir/YYYY/MM/."""
        # Set up extracted directory with a file
        extracted_zip = config.extracted_dir / "test-zip"
        extracted_zip.mkdir(parents=True)
        test_file = extracted_zip / "IMG_1234.jpg"
        test_file.write_bytes(b"test content")

        # Register the file in database with hash
        real_db.register_zip("test-zip.zip")
        real_db.register_file(
            "test-zip.zip",
            str(test_file),
            content_hash="abc123def456",
            file_size=len(b"test content"),
        )
        real_db.commit()

        # Organize files
        stats = step_organize_files_from_zip(config, real_db, "test-zip", logger)

        # Should have organized 1 file
        assert stats["organized"] == 1
        assert stats["duplicates"] == 0
        assert stats["errors"] == 0

        # File should be in organized_files table
        assert real_db.check_duplicate("abc123def456") is True

    def test_organize_duplicate_to_duplicates_dir(self, config, real_db, logger, tmp_path):
        """Should move duplicate file to duplicates/zip_name/."""
        # Insert first file into organized_files (already organized)
        real_db.insert_organized_file(
            hash="duplicate_hash",
            original_name="IMG_1234.jpg",
            final_path="2020/01/IMG_1234.jpg",
            source_zip="previous-zip.zip",
            file_size=1000,
        )

        # Set up extracted directory with duplicate file
        extracted_zip = config.extracted_dir / "test-zip"
        extracted_zip.mkdir(parents=True)
        test_file = extracted_zip / "IMG_5678.jpg"
        test_file.write_bytes(b"duplicate content")

        # Register the duplicate file
        real_db.register_zip("test-zip.zip")
        real_db.register_file(
            "test-zip.zip", str(test_file), content_hash="duplicate_hash", file_size=17
        )
        real_db.commit()

        # Organize files
        stats = step_organize_files_from_zip(config, real_db, "test-zip", logger)

        # Should have 1 duplicate
        assert stats["organized"] == 0
        assert stats["duplicates"] == 1
        assert stats["errors"] == 0

        # File should be in duplicates/test-zip/
        dup_file = config.duplicates_dir / "test-zip" / "IMG_5678.jpg"
        assert dup_file.exists()

    def test_organize_handles_missing_file(self, config, real_db, logger):
        """Should handle missing file gracefully."""
        # Register file that doesn't exist
        real_db.register_zip("test-zip.zip")
        real_db.register_file(
            "test-zip.zip",
            "/nonexistent/file.jpg",
            content_hash="abc123",
            file_size=1000,
        )
        real_db.commit()

        # Organize files
        stats = step_organize_files_from_zip(config, real_db, "test-zip", logger)

        # Should report error
        assert stats["organized"] == 0
        assert stats["duplicates"] == 0
        assert stats["errors"] == 1


class TestComputeOrganizedDest:
    """Test _compute_organized_dest helper function."""

    def test_compute_organized_dest_with_date(self, config, tmp_path, monkeypatch):
        """Test destination computation with EXIF date."""
        from takeout_photos.stages.organize import _compute_organized_dest

        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image")

        # Pass EXIF datetime directly (from database)
        exif_datetime = "2020:05:15 12:30:00"

        # Compute destination
        dest_dir, filename = _compute_organized_dest(test_file, config, exif_datetime)

        # Should organize to 2020/05 directory
        assert dest_dir == config.organized_dir / "2020" / "05"
        assert filename == "test.jpg"

    def test_compute_organized_dest_no_date(self, config, tmp_path, monkeypatch):
        """Test destination computation without EXIF date."""
        from takeout_photos.stages.organize import _compute_organized_dest

        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image")

        # Pass None for exif_datetime (no date from database)
        exif_datetime = None

        # Compute destination
        dest_dir, filename = _compute_organized_dest(test_file, config, exif_datetime)

        # Should organize to no_date directory
        assert dest_dir == config.organized_dir / "no_date"
        assert filename == "test.jpg"

    def test_compute_organized_dest_filename_conflict(self, config, tmp_path, monkeypatch):
        """Test filename conflict resolution."""
        from takeout_photos.stages.organize import _compute_organized_dest

        # Create destination directory with existing file
        dest_dir = config.organized_dir / "2020" / "05"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "test.jpg").write_bytes(b"existing")

        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"new")

        # Pass EXIF datetime directly
        exif_datetime = "2020:05:15 12:30:00"

        # Compute destination
        _, filename = _compute_organized_dest(test_file, config, exif_datetime)

        # Should resolve conflict with (1)
        assert filename == "test(1).jpg"

    def test_compute_organized_dest_multiple_conflicts(self, config, tmp_path, monkeypatch):
        """Test multiple filename conflicts."""
        from takeout_photos.stages.organize import _compute_organized_dest

        # Create destination directory with multiple existing files
        dest_dir = config.organized_dir / "2020" / "05"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "test.jpg").write_bytes(b"existing 1")
        (dest_dir / "test(1).jpg").write_bytes(b"existing 2")

        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"new")

        # Pass EXIF datetime directly
        exif_datetime = "2020:05:15 12:30:00"

        # Compute destination
        _, filename = _compute_organized_dest(test_file, config, exif_datetime)

        # Should resolve with (2)
        assert filename == "test(2).jpg"

    def test_compute_dest_with_dated_filenames(self, tmp_path):
        """Test _compute_organized_dest applies date prefix when enabled."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _compute_organized_dest

        config = Config(workdir=tmp_path, dated_filenames=True)
        config.organized_dir = tmp_path / "organized"

        source = tmp_path / "IMG_1234.jpg"
        source.write_text("test")

        # Pass EXIF datetime directly
        exif_datetime = "2023:05:15 14:30:22"
        dest_dir, filename = _compute_organized_dest(source, config, exif_datetime)

        assert dest_dir == tmp_path / "organized" / "2023" / "05"
        assert filename == "2023-05-15_IMG_1234.jpg"

    def test_compute_dest_with_no_date_prefix(self, tmp_path):
        """Test _compute_organized_dest adds NO-DATE prefix for files without dates."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _compute_organized_dest

        config = Config(workdir=tmp_path, dated_filenames=True)
        config.organized_dir = tmp_path / "organized"

        source = tmp_path / "screenshot.png"
        source.write_text("test")

        # Pass None for exif_datetime
        exif_datetime = None
        dest_dir, filename = _compute_organized_dest(source, config, exif_datetime)

        assert dest_dir == tmp_path / "organized" / "no_date"
        assert filename == "NO-DATE_screenshot.png"

    def test_compute_dest_dated_filenames_disabled(self, tmp_path):
        """Test _compute_organized_dest preserves original name when disabled."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _compute_organized_dest

        config = Config(workdir=tmp_path, dated_filenames=False)
        config.organized_dir = tmp_path / "organized"

        source = tmp_path / "IMG_1234.jpg"
        source.write_text("test")

        # Pass EXIF datetime directly
        exif_datetime = "2023:05:15 14:30:22"
        dest_dir, filename = _compute_organized_dest(source, config, exif_datetime)

        assert dest_dir == tmp_path / "organized" / "2023" / "05"
        assert filename == "IMG_1234.jpg"  # Original name preserved

    def test_compute_dest_collision_with_dated_filenames(self, tmp_path):
        """Test collision resolution preserves date prefix."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _compute_organized_dest

        config = Config(workdir=tmp_path, dated_filenames=True)
        config.organized_dir = tmp_path / "organized"
        organized_dir = config.organized_dir / "2023" / "05"
        organized_dir.mkdir(parents=True)

        # Create existing file with date prefix
        (organized_dir / "2023-05-15_photo.jpg").touch()

        # Create source file
        source = tmp_path / "photo.jpg"
        source.write_text("test")

        # Pass EXIF datetime directly
        exif_datetime = "2023:05:15 14:30:22"
        dest_dir, filename = _compute_organized_dest(source, config, exif_datetime)

        assert filename == "2023-05-15_photo(1).jpg"  # Date prefix preserved
        assert dest_dir == organized_dir


class TestBuildFilename:
    """Test _build_filename helper function."""

    def test_build_filename_with_date(self, tmp_path):
        """Test filename prefix with valid EXIF date."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _build_filename

        config = Config(workdir=tmp_path, dated_filenames=True)
        result = _build_filename("photo.jpg", "2023:05:15 14:30:22", config)
        assert result == "2023-05-15_photo.jpg"

    def test_build_filename_no_date(self, tmp_path):
        """Test filename prefix when no EXIF date available."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _build_filename

        config = Config(workdir=tmp_path, dated_filenames=True)
        result = _build_filename("photo.jpg", None, config)
        assert result == "NO-DATE_photo.jpg"

    def test_build_filename_disabled(self, tmp_path):
        """Test filename unchanged when feature disabled."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _build_filename

        config = Config(workdir=tmp_path, dated_filenames=False)
        result = _build_filename("photo.jpg", "2023:05:15 14:30:22", config)
        assert result == "photo.jpg"

    def test_build_filename_preserves_extension(self, tmp_path):
        """Test date prefix preserves file extension."""
        from takeout_photos.core.config import Config
        from takeout_photos.stages.organize import _build_filename

        config = Config(workdir=tmp_path, dated_filenames=True)
        result = _build_filename("IMG_1234.HEIC", "2020:12:25 10:30:00", config)
        assert result == "2020-12-25_IMG_1234.HEIC"


class TestReadExifDate:
    """Test _read_exif_date helper function."""

    def test_read_exif_date_uses_warnings_file(self, tmp_path):
        """Test that _read_exif_date passes warnings file to run_exiftool."""
        from takeout_photos.stages.organize import _read_exif_date

        # Create test file
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Create warnings file
        warnings_file = tmp_path / "exif_warnings.txt"

        # Mock run_exiftool
        with patch("takeout_photos.stages.organize.run_exiftool") as mock_exiftool:
            mock_result = MagicMock()
            mock_result.stdout = "2023:05:15 14:30:22\n"
            mock_exiftool.return_value = mock_result

            # Create a mock logger
            from logging import getLogger

            logger = getLogger("test")

            # Call with warnings file and logger
            result = _read_exif_date(test_file, warnings_file, logger)

            # Verify run_exiftool was called with warnings file and logger
            mock_exiftool.assert_called_once()
            call_args = mock_exiftool.call_args[0][0]
            call_kwargs = mock_exiftool.call_args[1]

            # Check args contain expected exiftool flags
            assert "-DateTimeOriginal" in call_args
            assert "-s3" in call_args
            assert str(test_file) in call_args

            # Check kwargs have warnings file and log
            assert call_kwargs["exif_warnings_file"] == warnings_file
            assert call_kwargs["log"] == logger

            # Check result
            assert result == "2023:05:15 14:30:22"
