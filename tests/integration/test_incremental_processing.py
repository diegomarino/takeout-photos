"""Integration tests for v3.0 incremental ZIP-by-ZIP processing.

Tests that verify:
- ZIPs are processed one at a time
- Status progression: pending → organized
- Deduplication across multiple ZIPs
- Resumability after interruption
- Handling of already-organized ZIPs
"""

from __future__ import annotations

import zipfile

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


class TestIncrementalProcessing:
    """Test incremental ZIP-by-ZIP processing behavior."""

    def test_processes_single_zip_through_all_stages(self, tmp_path):
        """Single ZIP should go through all stages and end with status='organized'."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal ZIP
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")  # JPEG magic bytes

        with Pipeline(config) as pipeline:
            pipeline.run()

            # ZIP should be marked as organized
            status = pipeline.db.get_zip_status("takeout-001.zip")
            assert status == "organized"

            # File should be in organized/
            organized_files = list(config.organized_dir.rglob("*.jpg"))
            assert len(organized_files) >= 1

            # extracted/ should be auto-deleted (v3.0.1: entire directory)
            assert (
                not config.extracted_dir.exists() or len(list(config.extracted_dir.rglob("*"))) == 0
            )

    def test_processes_multiple_zips_sequentially(self, tmp_path):
        """Multiple ZIPs should be processed one at a time."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create 3 ZIPs with unique content to avoid deduplication
        for i in range(1, 4):
            zip_path = config.zips_dir / f"takeout-{i:03d}.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                # Each file has unique content
                content = b"\xff\xd8\xff\xe0" + f"unique{i}".encode()
                zf.writestr(f"photo{i}.jpg", content)

        with Pipeline(config) as pipeline:
            pipeline.run()

            # All ZIPs should be organized
            for i in range(1, 4):
                status = pipeline.db.get_zip_status(f"takeout-{i:03d}.zip")
                assert status == "organized"

            # All files should be organized
            organized_files = list(config.organized_dir.rglob("*.jpg"))
            assert len(organized_files) == 3

    def test_deduplication_across_multiple_zips(self, tmp_path):
        """Duplicate files across ZIPs should be detected and moved to duplicates/."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create 2 ZIPs with identical file content
        same_content = b"\xff\xd8\xff\xe0" + b"identical content"

        zip1_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip1_path, "w") as zf:
            zf.writestr("photo1.jpg", same_content)

        zip2_path = config.zips_dir / "takeout-002.zip"
        with zipfile.ZipFile(zip2_path, "w") as zf:
            zf.writestr("photo2.jpg", same_content)  # Same content, different name

        with Pipeline(config) as pipeline:
            pipeline.run()

            # First ZIP's file should be organized
            organized_files = list(config.organized_dir.rglob("*.jpg"))
            assert len(organized_files) == 1

            # Second ZIP's file should be in duplicates/
            duplicate_files = list(config.duplicates_dir.rglob("*.jpg"))
            assert len(duplicate_files) == 1

            # Both ZIPs should be marked as organized
            assert pipeline.db.get_zip_status("takeout-001.zip") == "organized"
            assert pipeline.db.get_zip_status("takeout-002.zip") == "organized"

    def test_resumes_after_interruption(self, tmp_path):
        """Pipeline should skip already-organized ZIPs on resume."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create 2 ZIPs
        zip1_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip1_path, "w") as zf:
            zf.writestr("photo1.jpg", b"\xff\xd8\xff\xe0")

        zip2_path = config.zips_dir / "takeout-002.zip"
        with zipfile.ZipFile(zip2_path, "w") as zf:
            zf.writestr("photo2.jpg", b"\xff\xd8\xff\xe1")

        # First run - process first ZIP only
        with Pipeline(config) as pipeline:
            pipeline.db.register_zip("takeout-001.zip")
            pipeline.db.update_zip_status("takeout-001.zip", "organized")

        # Second run - should skip first ZIP
        with Pipeline(config) as pipeline:
            pipeline.run()

            # First ZIP should still be organized (not reprocessed)
            assert pipeline.db.get_zip_status("takeout-001.zip") == "organized"

            # Second ZIP should be processed
            assert pipeline.db.get_zip_status("takeout-002.zip") == "organized"

    def test_handles_zip_processing_error_gracefully(self, tmp_path):
        """Pipeline should mark failed ZIP as 'error' and continue with next ZIP."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a good ZIP and a corrupted ZIP
        good_zip = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(good_zip, "w") as zf:
            zf.writestr("photo1.jpg", b"\xff\xd8\xff\xe0")

        bad_zip = config.zips_dir / "takeout-002.zip"
        bad_zip.write_text("not a valid ZIP file")

        another_good_zip = config.zips_dir / "takeout-003.zip"
        with zipfile.ZipFile(another_good_zip, "w") as zf:
            zf.writestr("photo3.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            # Should not raise - continues past bad ZIP
            pipeline.run()

            # First ZIP should be organized
            assert pipeline.db.get_zip_status("takeout-001.zip") == "organized"

            # Bad ZIP should be marked as error
            status = pipeline.db.get_zip_status("takeout-002.zip")
            assert status == "error"

            # Third ZIP should still be processed
            assert pipeline.db.get_zip_status("takeout-003.zip") == "organized"


class TestIncrementalDiskSpace:
    """Test disk space behavior of incremental processing."""

    def test_extracted_dir_cleaned_after_processing(self, tmp_path):
        """extracted/ directory should be deleted after successful organization (v3.0.1)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # extracted/ directory should NOT exist (v3.0.1: entire directory deleted)
            assert (
                not config.extracted_dir.exists() or len(list(config.extracted_dir.rglob("*"))) == 0
            )

    def test_keep_extracted_files_preserves_directory(self, tmp_path):
        """With --keep-extracted-files, extracted/ should be preserved (v3.0.1)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), keep_extracted_files=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # extracted/ directory SHOULD still exist (v3.0.1: entire directory preserved)
            assert config.extracted_dir.exists()


class TestOrganizedFilesTable:
    """Test organized_files table tracking across runs."""

    def test_organized_files_recorded_in_database(self, tmp_path):
        """Files organized should be inserted into organized_files table."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Check organized_files table has entry
            rows = pipeline.db.conn.execute("SELECT * FROM organized_files").fetchall()
            assert len(rows) >= 1

            # Should have hash, original_name, final_path, source_zip
            row = rows[0]
            assert row["hash"] is not None
            assert row["original_name"] is not None
            assert row["final_path"] is not None
            assert row["source_zip"] == "takeout-001.zip"
