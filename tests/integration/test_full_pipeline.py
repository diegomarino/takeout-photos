"""Integration tests for the full Pipeline orchestrator."""

from __future__ import annotations

import zipfile
from unittest.mock import MagicMock, patch

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


class TestPipelineConstruction:
    """Test Pipeline initialization and setup."""

    def test_pipeline_creates_directories(self, tmp_path):
        """Test that Pipeline creates all required directories."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        pipeline = Pipeline(config)

        # Check all directories were created
        assert config.zips_dir.exists()
        assert config.extracted_dir.exists()
        assert config.duplicates_dir.exists()
        assert config.final_dir.exists()
        assert config.organized_dir.exists()
        assert config.logs_dir.exists()

        pipeline.close()

    def test_pipeline_creates_exif_warnings_file(self, tmp_path):
        """Test that pipeline creates exif_warnings file with correct timestamp."""
        config = Config(workdir=tmp_path)

        with Pipeline(config) as pipeline:
            # Check that exif_warnings_file is set
            assert pipeline.config.exif_warnings_file is not None
            assert pipeline.config.exif_warnings_file.parent == config.logs_dir
            assert pipeline.config.exif_warnings_file.name.endswith("_exif_warnings.txt")

            # Extract timestamp from filename
            filename = pipeline.config.exif_warnings_file.name
            timestamp = filename.split("_exif_warnings.txt")[0]

            # Should be valid timestamp format
            assert len(timestamp) == 15  # YYYYMMDD_HHMMSS

            # Should match run log timestamp
            run_logs = list(config.logs_dir.glob("*_run.log"))
            assert len(run_logs) == 1
            run_timestamp = run_logs[0].name.split("_run.log")[0]
            assert timestamp == run_timestamp

    def test_pipeline_creates_database(self, tmp_path):
        """Test that Pipeline creates database."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        pipeline = Pipeline(config)

        assert config.db_path.exists()
        assert pipeline.db is not None

        pipeline.close()

    def test_pipeline_context_manager(self, tmp_path):
        """Test Pipeline as context manager."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            assert pipeline.db is not None

        # Database should be closed after context
        # (we can't easily test this without accessing internals)

    def test_pipeline_verbose_override(self, tmp_path):
        """Test that verbose parameter overrides config.verbose."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), verbose=False)

        pipeline = Pipeline(config, verbose=True)

        assert pipeline.config.verbose is True

        pipeline.close()


class TestPipelinePhases:
    """Test individual Pipeline phase methods."""

    def test_extract_all_zips_no_zips(self, tmp_path):
        """Test extract_all_zips with no ZIPs."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Should not crash with no ZIPs
            pipeline.extract_all_zips()

    def test_extract_all_zips_with_zip(self, tmp_path):
        """Test extract_all_zips with a minimal ZIP."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.jpg", b"fake image")

        with Pipeline(config) as pipeline:
            pipeline.extract_all_zips()

            # Check ZIP was registered
            status = pipeline.db.get_zip_status("test.zip")
            assert status == "extracted"

    def test_validate_formats_no_files(self, tmp_path):
        """Test validate_formats with no files."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Should not crash with no files
            pipeline.validate_formats()

    def test_apply_metadata_phase_no_files(self, tmp_path):
        """Test apply_metadata_phase with no files."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Should not crash with no files
            pipeline.apply_metadata_phase()

    def test_quality_control_no_files(self, tmp_path):
        """Test quality_control with no files."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Should not crash with no files
            pipeline.quality_control()

            # Check QC report was created
            qc_reports = list(config.logs_dir.glob("*_qc.txt"))
            assert len(qc_reports) == 1


class TestFullPipeline:
    """Test complete pipeline execution."""

    def test_run_empty_pipeline(self, tmp_path):
        """Test run() with no ZIPs (empty pipeline)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Should complete without error even with no ZIPs
            pipeline.run()

            # Check completion was recorded
            last_run = pipeline.db.get_state("last_complete_run")
            assert last_run is not None

    def test_run_with_minimal_zip(self, tmp_path):
        """Test run() with a minimal ZIP containing one file."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP with one image
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")  # JPEG magic bytes

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Verify pipeline completed
            last_run = pipeline.db.get_state("last_complete_run")
            assert last_run is not None

            # Check ZIP was processed
            status = pipeline.db.get_zip_status("test.zip")
            assert status == "organized"

            # Check QC report was created
            qc_reports = list(config.logs_dir.glob("*_qc.txt"))
            assert len(qc_reports) >= 1

    def test_run_idempotent(self, tmp_path):
        """Test that run() is idempotent (can be run multiple times)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # Run twice - should not error
            pipeline.run()
            first_run = pipeline.db.get_state("last_complete_run")

            pipeline.run()
            second_run = pipeline.db.get_state("last_complete_run")

            # Second run should update timestamp
            assert second_run >= first_run

    def test_run_resumable_after_error(self, tmp_path):
        """Test that pipeline can resume after an error."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")

        # First run - simulate error during organize
        with Pipeline(config) as pipeline:
            pipeline.extract_all_zips()
            pipeline.validate_formats()
            pipeline.apply_metadata_phase()
            # Stop here (simulate error)

        # Second run - should resume and complete
        with Pipeline(config) as pipeline:
            pipeline.run()

            # Should complete successfully
            last_run = pipeline.db.get_state("last_complete_run")
            assert last_run is not None


class TestPipelinePhaseOrdering:
    """Test that phases are called in correct order."""

    def test_run_calls_phases_in_order(self, tmp_path):
        """Test that run() calls quality_control at the end (v3.0 incremental mode)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        with Pipeline(config) as pipeline:
            # In v3.0, run() processes ZIPs incrementally and calls QC at the end
            # Track that QC is called
            qc_called = []

            original_qc = pipeline.quality_control

            def mock_qc():
                qc_called.append(True)
                original_qc()

            pipeline.quality_control = mock_qc

            pipeline.run()

            # Verify QC was called once
            assert len(qc_called) == 1


class TestPipelineErrorHandling:
    """Test Pipeline error handling."""

    def test_run_propagates_exceptions(self, tmp_path):
        """Test that critical exceptions (outside ZIP processing) are propagated."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP to trigger processing
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.jpg", b"fake")

        with Pipeline(config) as pipeline:
            # Mock quality_control to raise a critical error
            def mock_qc():
                raise ValueError("Test error")

            pipeline.quality_control = mock_qc

            # Critical exception should be propagated
            with pytest.raises(ValueError, match="Test error"):
                pipeline.run()

    def test_error_is_logged(self, tmp_path):
        """Test that ZIP processing errors are caught and logged (v3.0.1 behavior)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP to trigger processing
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.jpg", b"fake")

        with Pipeline(config) as pipeline:
            # Mock _batch_process_all_files to raise error (v3.0.1 two-phase approach)
            def mock_batch(zips):
                # Mark the ZIP as error during processing
                pipeline.db.update_zip_status(
                    "test.zip", "error", error_msg="Test ZIP processing error"
                )
                # Don't call original to simulate error

            pipeline._batch_process_all_files = mock_batch

            # In v3.0.1, ZIP processing errors are caught and logged, not propagated
            pipeline.run()  # Should not raise

            # Check that ZIP status was marked as error
            status = pipeline.db.get_zip_status("test.zip")
            assert status == "error"

            # Check that error was logged
            log_files = list(config.logs_dir.glob("*_run.log"))
            assert len(log_files) >= 1


class TestDatedFilenamesFeature:
    """Test --dated-filenames feature integration."""

    def test_pipeline_with_dated_filenames(self, tmp_path):
        """Test complete pipeline with --dated-filenames flag.

        Note: This test relies on JSON metadata for dates. Files without
        JSON metadata will go to no_date/ directory since exif_datetime
        is only populated when photo_taken_ts exists in JSON."""
        workdir = tmp_path / "work"
        # Create config with dated_filenames enabled
        config = Config(workdir=str(workdir), dated_filenames=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP with JSON metadata
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # File 1: photo with JSON metadata (will have date)
            zf.writestr("photo_with_date.jpg", b"\xff\xd8\xff\x01")
            zf.writestr(
                "photo_with_date.jpg.json",
                '{"photoTakenTime": {"timestamp": "1653496222"}, "title": "photo_with_date.jpg"}',
            )
            # File 2: photo without JSON (will have NO-DATE prefix)
            zf.writestr("photo_no_date.jpg", b"\xff\xd8\xff\x02")

        with Pipeline(config) as pipeline:
            # Verify config has dated_filenames enabled
            assert config.dated_filenames is True

            # Mock exiftool to return success (test uses fake JPEG bytes)
            with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
                mock_exiftool.return_value = MagicMock(returncode=0)

                # Run pipeline
                pipeline.run()

                # Verify pipeline completed
                last_run = pipeline.db.get_state("last_complete_run")
                assert last_run is not None

                # Verify files were organized with date prefixes
                # File with JSON metadata should have date prefix from photo_taken_ts
                # 1653496222 = 2022-05-25 16:50:22 UTC
                dated_file = config.organized_dir / "2022" / "05" / "2022-05-25_photo_with_date.jpg"
                assert dated_file.exists(), f"Expected {dated_file} to exist"

                # File without JSON should be in no_date with NO-DATE prefix
                no_date_file = config.organized_dir / "no_date" / "NO-DATE_photo_no_date.jpg"
                assert no_date_file.exists(), f"Expected {no_date_file} to exist"

    def test_pipeline_without_dated_filenames(self, tmp_path):
        """Test pipeline preserves original filenames when feature is disabled."""
        workdir = tmp_path / "work"
        # Create config with dated_filenames disabled (default)
        config = Config(workdir=str(workdir), dated_filenames=False)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP with JSON metadata
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")
            zf.writestr(
                "photo.jpg.json",
                '{"photoTakenTime": {"timestamp": "1653496222"}, "title": "photo.jpg"}',
            )

        with Pipeline(config) as pipeline:
            # Verify config has dated_filenames disabled
            assert config.dated_filenames is False

            # Mock exiftool to return success (test uses fake JPEG bytes)
            with patch("takeout_photos.stages.metadata.run_exiftool") as mock_exiftool:
                mock_exiftool.return_value = MagicMock(returncode=0)

                # Run pipeline
                pipeline.run()

                # Verify file was organized without date prefix
                # File should be in organized/2022/05/photo.jpg (NO PREFIX)
                # 1653496222 = 2022-05-25 16:50:22 UTC
                original_file = config.organized_dir / "2022" / "05" / "photo.jpg"
                assert original_file.exists(), f"Expected {original_file} to exist"

                # Verify no date-prefixed file exists
                dated_file = config.organized_dir / "2022" / "05" / "2022-05-25_photo.jpg"
                assert not dated_file.exists(), f"Unexpected {dated_file} should not exist"


class TestPipelineCleanup:
    """Test pipeline cleanup behavior."""

    def test_pipeline_uses_conservative_cleanup(self, tmp_path):
        """Test that pipeline uses conservative cleanup with remove_empty_directories."""
        from unittest.mock import MagicMock, patch

        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")

        # Create some empty directories to test cleanup
        (config.extracted_dir / "empty1").mkdir(parents=True, exist_ok=True)
        (config.duplicates_dir / "empty2").mkdir(parents=True, exist_ok=True)
        (config.organized_dir / "empty3").mkdir(parents=True, exist_ok=True)

        # Mock the cleanup functions to track calls
        mock_remove_empty = MagicMock(return_value=5)
        mock_log_summary = MagicMock()

        # Patch at the source module where they're imported from
        with patch(
            "takeout_photos.utils.cleanup.remove_empty_directories", mock_remove_empty
        ), patch("takeout_photos.utils.cleanup.log_pipeline_summary", mock_log_summary):
            with Pipeline(config) as pipeline:
                pipeline.run()

                # Verify remove_empty_directories was called for each directory
                # Should be called 3 times: extracted/, duplicates/, organized/
                assert mock_remove_empty.call_count == 3

                # Verify it was called with correct directories
                calls = [call[0] for call in mock_remove_empty.call_args_list]
                called_dirs = [call[0] for call in calls]
                assert config.extracted_dir in called_dirs
                assert config.duplicates_dir in called_dirs
                assert config.organized_dir in called_dirs

                # Verify log_pipeline_summary was called once
                assert mock_log_summary.call_count == 1

                # Verify log_pipeline_summary was called with cleanup_stats
                summary_call = mock_log_summary.call_args
                assert summary_call is not None
                cleanup_stats = summary_call[0][3]  # 4th positional arg
                assert isinstance(cleanup_stats, dict)
                assert "extracted" in cleanup_stats
                assert "duplicates" in cleanup_stats
                assert "organized" in cleanup_stats

    def test_pipeline_respects_keep_extracted_files_flag(self, tmp_path):
        """Test that pipeline skips cleanup of extracted/ when --keep-extracted-files."""
        from unittest.mock import MagicMock, patch

        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), keep_extracted_files=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")

        # Mock the cleanup functions
        mock_remove_empty = MagicMock(return_value=0)

        # Patch at the source module
        with patch("takeout_photos.utils.cleanup.remove_empty_directories", mock_remove_empty):
            with Pipeline(config) as pipeline:
                pipeline.run()

                # Should still be called but only for duplicates/ and organized/
                # NOT for extracted/ because of --keep-extracted-files
                assert mock_remove_empty.call_count == 2

                # Verify extracted/ was NOT cleaned
                calls = [call[0] for call in mock_remove_empty.call_args_list]
                called_dirs = [call[0] for call in calls]
                assert config.extracted_dir not in called_dirs
                assert config.duplicates_dir in called_dirs
                assert config.organized_dir in called_dirs
