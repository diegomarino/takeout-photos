"""Tests for metadata application stage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from takeout_photos.stages.metadata import step_apply_metadata


class TestStepApplyMetadata:
    """Test the metadata application stage."""

    def test_apply_metadata_no_pending_files(self, config, db, logger):
        """Test when there are no pending files."""
        # Mock get_files_for_zip to return empty list
        db.get_files_for_zip = MagicMock(return_value=[])

        step_apply_metadata(config, db, "test.zip", logger)

        # Should return early without applying metadata
        db.commit.assert_not_called()

    def test_apply_metadata_calls_exiftool(self, config, db, logger, tmp_path):
        """Test that exiftool is called when applying metadata."""
        # Create test file
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Mock database with file having timestamp
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        # Mock run_exiftool
        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            step_apply_metadata(config, db, "test.zip", logger)

            # exiftool should be called
            mock_exiftool.assert_called_once()

    def test_apply_metadata_applies_timestamps(self, config, db, logger, tmp_path):
        """Test that timestamps are applied from JSON."""
        # Create test file
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Mock database with timestamp
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,  # 2021-05-17
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        # Mock run_exiftool and capture argfile content
        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            captured_args = []

            def capture_write(content):
                captured_args.append(content)

            with patch("tempfile.NamedTemporaryFile") as mock_tempfile:
                mock_file = MagicMock()
                mock_file.name = "/tmp/test_argfile.txt"
                mock_file.write = capture_write
                mock_tempfile.return_value.__enter__.return_value = mock_file

                step_apply_metadata(config, db, "test.zip", logger)

                # Check that DateTimeOriginal was written to argfile
                args_str = "".join(str(arg) for arg in captured_args)
                assert "DateTimeOriginal" in args_str
                assert "CreateDate" in args_str

    def test_apply_metadata_applies_gps_coordinates(self, config, db, logger, tmp_path):
        """Test that GPS coordinates are applied from JSON."""
        # Create test file
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Mock database with GPS data
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": None,
                    "geo_lat": 37.7749,  # San Francisco
                    "geo_lon": -122.4194,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        # Mock run_exiftool
        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            captured_args = []

            def capture_write(content):
                captured_args.append(content)

            with patch("tempfile.NamedTemporaryFile") as mock_tempfile:
                mock_file = MagicMock()
                mock_file.name = "/tmp/test_argfile.txt"
                mock_file.write = capture_write
                mock_tempfile.return_value.__enter__.return_value = mock_file

                step_apply_metadata(config, db, "test.zip", logger)

                # Check GPS tags in argfile
                args_str = "".join(str(arg) for arg in captured_args)
                assert "GPSLatitude" in args_str
                assert "GPSLongitude" in args_str
                assert "GPSLatitudeRef=N" in args_str
                assert "GPSLongitudeRef=W" in args_str

    def test_apply_metadata_gps_reference_directions(self, config, db, logger, tmp_path):
        """Test that GPS reference directions are set correctly."""
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Test all 4 quadrants
        test_cases = [
            (40.7128, -74.0060, "N", "W"),  # New York (N, W)
            (51.5074, 0.1278, "N", "E"),  # London (N, E)
            (-33.8688, 151.2093, "S", "E"),  # Sydney (S, E)
            (-22.9068, -43.1729, "S", "W"),  # Rio (S, W)
        ]

        for lat, lon, lat_ref, lon_ref in test_cases:
            db.get_files_for_zip = MagicMock(
                return_value=[
                    {
                        "id": 1,
                        "original_path": str(test_file),
                        "photo_taken_ts": None,
                        "geo_lat": lat,
                        "geo_lon": lon,
                    }
                ]
            )
            db.update_file = MagicMock()
            db.commit = MagicMock()

            with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
                mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

                captured_args: list = []

                def make_capture_write(args_list):
                    def capture_write(content):
                        args_list.append(content)

                    return capture_write

                with patch("tempfile.NamedTemporaryFile") as mock_tempfile:
                    mock_file = MagicMock()
                    mock_file.name = "/tmp/test_argfile.txt"
                    mock_file.write = make_capture_write(captured_args)
                    mock_tempfile.return_value.__enter__.return_value = mock_file

                    step_apply_metadata(config, db, "test.zip", logger)

                    args_str = "".join(str(arg) for arg in captured_args)
                    assert f"GPSLatitudeRef={lat_ref}" in args_str
                    assert f"GPSLongitudeRef={lon_ref}" in args_str

    def test_apply_metadata_skips_files_without_metadata(self, config, db, logger, tmp_path):
        """Test that files without metadata are skipped."""
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Mock database with file having no metadata
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": None,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            step_apply_metadata(config, db, "test.zip", logger)

            # File status should still be updated even though no metadata applied
            db.update_file.assert_called()
            db.commit.assert_called()

    def test_apply_metadata_dry_run_mode(self, config, db, logger, tmp_path):
        """Test that dry-run mode doesn't modify filesystem or database."""
        config.dry_run = True

        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            step_apply_metadata(config, db, "test.zip", logger)

            # exiftool should not be called in dry-run
            mock_exiftool.assert_not_called()

        # Database should NOT be updated in dry-run mode
        db.update_file.assert_not_called()
        db.commit.assert_not_called()

    def test_apply_metadata_handles_exiftool_warnings(self, config, db, logger, tmp_path):
        """Test handling of exiftool warnings."""
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            # Simulate exiftool failure
            mock_exiftool.return_value = MagicMock(returncode=1, stderr="Warning: some minor issue")

            step_apply_metadata(config, db, "test.zip", logger)

            # Files should NOT be updated when exiftool fails (stay pending for retry)
            db.update_file.assert_not_called()
            db.commit.assert_not_called()

    def test_apply_metadata_updates_file_status(self, config, db, logger, tmp_path):
        """Test that file status is updated to meta_applied."""
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 123,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            step_apply_metadata(config, db, "test.zip", logger)

            # Check that file was updated with meta_applied status and exif_datetime
            # Timestamp 1621234567 = 2021-05-17 06:56:07 UTC
            db.update_file.assert_called_with(
                123, status="meta_applied", exif_datetime="2021:05:17 06:56:07"
            )

    def test_apply_metadata_batch_processing(self, config, db, logger, tmp_path):
        """Test that multiple files are processed in a single batch."""
        # Create multiple test files
        files = []
        for i in range(3):
            f = tmp_path / f"photo{i}.jpg"
            f.write_bytes(b"image")
            files.append(f)

        # Mock database with multiple files
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": i + 1,
                    "original_path": str(f),
                    "photo_taken_ts": 1621234567 + i * 1000,
                    "geo_lat": 37.7749,
                    "geo_lon": -122.4194,
                }
                for i, f in enumerate(files)
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            step_apply_metadata(config, db, "test.zip", logger)

            # exiftool should be called only once (batch mode)
            assert mock_exiftool.call_count == 1

            # All files should be updated
            assert db.update_file.call_count == 3

    def test_metadata_stage_uses_warnings_file(self, config, db, logger, tmp_path):
        """Test that exif_warnings_file is passed to run_exiftool."""
        # Set up config with warnings file
        warnings_file = tmp_path / "exif_warnings.txt"
        config.exif_warnings_file = warnings_file

        # Create test file
        test_file = tmp_path / "photo.jpg"
        test_file.write_bytes(b"image")

        # Mock database
        db.get_files_for_zip = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "original_path": str(test_file),
                    "photo_taken_ts": 1621234567,
                    "geo_lat": None,
                    "geo_lon": None,
                }
            ]
        )
        db.update_file = MagicMock()
        db.commit = MagicMock()

        # Mock run_exiftool
        with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(returncode=0, stderr="")

            step_apply_metadata(config, db, "test.zip", logger)

            # Verify run_exiftool was called with warnings file and logger
            mock_exiftool.assert_called_once()
            call_kwargs = mock_exiftool.call_args[1]
            assert call_kwargs["exif_warnings_file"] == warnings_file
            assert call_kwargs["log"] == logger
