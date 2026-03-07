"""Integration tests for disk cleanup behavior in v3.0 incremental mode.

Tests that verify:
- Auto-cleanup of extracted/ after each ZIP
- --keep-extracted-files flag behavior
- --delete-zips-after-extract flag behavior
"""

from __future__ import annotations

import zipfile

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


class TestDiskCleanup:
    """Test disk space cleanup behavior."""

    def test_auto_deletes_extracted_directory(self, tmp_path):
        """After organizing, extracted/ directory should be auto-deleted (v3.0.1)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("subdir/photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Verify file was organized
            assert list(config.organized_dir.rglob("*.jpg"))

            # Verify extracted/ was cleaned up (v3.0.1: entire directory deleted)
            assert (
                not config.extracted_dir.exists() or len(list(config.extracted_dir.rglob("*"))) == 0
            )

            # Original ZIP should still exist
            assert zip_path.exists()

    def test_keep_extracted_files_flag(self, tmp_path):
        """With --keep-extracted-files, extracted/ should be preserved."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), keep_extracted_files=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP with nested structure
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("Google Photos/2020/photo.jpg", b"\xff\xd8\xff\xe0")
            zf.writestr("Google Photos/2020/photo.jpg.json", '{"timestamp": 1577836800}')

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Verify file was organized
            assert list(config.organized_dir.rglob("*.jpg"))

            # Verify extracted/ was NOT deleted (v3.0.1: entire directory preserved)
            assert config.extracted_dir.exists()

            # Verify directory structure preserved (v3.0.1: files in extracted/ root)
            assert (config.extracted_dir / "Google Photos" / "2020").exists()

    def test_delete_zips_after_extract_flag(self, tmp_path):
        """With --delete-zips-after-extract, original ZIP should be deleted."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), delete_zips_after_extract=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Verify file was organized
            assert list(config.organized_dir.rglob("*.jpg"))

            # Verify original ZIP was deleted
            assert not zip_path.exists()

            # Verify ZIP deletion is recorded in database
            row = pipeline.db.conn.execute(
                "SELECT deleted_at FROM zips WHERE name = ?", ("takeout-001.zip",)
            ).fetchone()
            assert row["deleted_at"] is not None

    def test_combined_cleanup_flags(self, tmp_path):
        """Test --delete-zips-after-extract with auto-cleanup of extracted/."""
        workdir = tmp_path / "work"
        config = Config(
            workdir=str(workdir),
            delete_zips_after_extract=True,
            keep_extracted_files=False,  # Default - auto-delete
        )
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create 2 ZIPs with unique content to avoid deduplication
        for i in [1, 2]:
            zip_path = config.zips_dir / f"takeout-{i:03d}.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                content = b"\xff\xd8\xff\xe0" + f"unique{i}".encode()
                zf.writestr(f"photo{i}.jpg", content)

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Both files should be organized
            organized = list(config.organized_dir.rglob("*.jpg"))
            assert len(organized) == 2

            # Original ZIPs should be deleted
            assert not (config.zips_dir / "takeout-001.zip").exists()
            assert not (config.zips_dir / "takeout-002.zip").exists()

            # extracted/ directory should be deleted (v3.0.1: entire directory)
            assert (
                not config.extracted_dir.exists() or len(list(config.extracted_dir.rglob("*"))) == 0
            )

    def test_multiple_zips_minimal_disk_usage(self, tmp_path):
        """Process 3 ZIPs and verify extracted/ is cleaned up at end (v3.0.1)."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create 3 ZIPs with unique content
        for i in range(1, 4):
            zip_path = config.zips_dir / f"takeout-{i:03d}.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                # JPEG magic bytes + unique content
                content = b"\xff\xd8\xff\xe0" + f"content{i}".encode() * 1000
                zf.writestr(f"photo{i}.jpg", content)

        # Track max number of extracted directories at any point
        # (We can't actually monitor during pipeline, but we can verify final state)

        with Pipeline(config) as pipeline:
            pipeline.run()

            # All files organized
            organized = list(config.organized_dir.rglob("*.jpg"))
            assert len(organized) == 3

            # NO extracted directories remaining
            extracted_dirs = list(config.extracted_dir.glob("*"))
            assert len(extracted_dirs) == 0

            # All ZIPs marked as organized
            for i in range(1, 4):
                status = pipeline.db.get_zip_status(f"takeout-{i:03d}.zip")
                assert status == "organized"


class TestDryRunMode:
    """Test dry-run mode doesn't delete or modify files."""

    def test_dry_run_preserves_all_files(self, tmp_path):
        """In dry-run mode, no files should be moved or deleted."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir), dry_run=True)
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Original ZIP should still exist
            assert zip_path.exists()

            # extracted/ should still exist (not cleaned up in dry-run)
            assert config.extracted_dir.exists()
            # Note: In dry-run, extraction happens but files aren't moved
            # So we can't test file organization, only that deletion didn't happen


class TestCustomOrganizedDir:
    """Test --organized-dir flag (v3.0 feature)."""

    def test_organized_dir_custom_location(self, tmp_path):
        """Files should be organized to custom directory if specified."""
        workdir = tmp_path / "work"
        custom_output = tmp_path / "my_photos"

        config = Config(workdir=str(workdir), organized_dir=str(custom_output))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create ZIP
        zip_path = config.zips_dir / "takeout-001.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        with Pipeline(config) as pipeline:
            pipeline.run()

            # Files should be in custom directory
            assert custom_output.exists()
            organized = list(custom_output.rglob("*.jpg"))
            assert len(organized) >= 1

            # Default organized_media/ should NOT be used
            default_dir = workdir / "organized_media"
            if default_dir.exists():
                default_files = list(default_dir.rglob("*.jpg"))
                assert len(default_files) == 0
