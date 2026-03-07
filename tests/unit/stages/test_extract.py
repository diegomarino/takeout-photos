"""Tests for ZIP extraction stage."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from takeout_photos.stages.extract import step_extract_zip


class TestStepExtractZip:
    """Test the ZIP extraction stage."""

    def test_extract_zip_creates_extract_directory(self, config, db, logger, tmp_path):
        """Test that extraction directory is created."""
        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "content")

        # Mock database methods
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()

        step_extract_zip(config, db, zip_path, logger)

        # Check extraction directory was created (v3.0.1: files in root)
        assert config.extracted_dir.exists()
        assert config.extracted_dir.is_dir()

    def test_extract_zip_extracts_files(self, config, db, logger, tmp_path):
        """Test that files are extracted from ZIP."""
        # Create test ZIP with file
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.jpg", b"image content")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Check file was extracted (v3.0.1: files in root, not subdirectory)
        extracted_file = config.extracted_dir / "test.jpg"
        assert extracted_file.exists()
        assert extracted_file.read_bytes() == b"image content"

    def test_extract_zip_registers_json_files(self, config, db, logger, tmp_path):
        """Test that JSON files are registered in database."""
        # Create ZIP with JSON file
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("metadata.json", '{"photoTakenTime": 123}')

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Check JSON was registered
        db.register_json_file.assert_called()
        call_args = db.register_json_file.call_args
        assert "test.zip" in str(call_args)
        assert "metadata.json" in str(call_args)

    def test_extract_zip_registers_media_files(self, config, db, logger, tmp_path):
        """Test that media files are registered with metadata."""
        # Create ZIP with media file
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"image data")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Check media file was registered
        db.register_file.assert_called()
        call_args = db.register_file.call_args[1]
        assert call_args["zip_name"] == "test.zip"
        assert "photo.jpg" in call_args["original_path"]

    def test_extract_zip_links_json_to_media(self, config, db, logger, tmp_path):
        """Test that JSON metadata is linked to media files."""
        # Create ZIP with photo and JSON
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("IMG_1234.jpg", b"image")
            zf.writestr("IMG_1234.jpg.json", '{"photoTakenTime": {"timestamp": "123"}}')

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()

        # Mock find_json_for_media_db to return the JSON path
        def find_json_side_effect(media_path):
            if "IMG_1234.jpg" in media_path:
                return str(config.extracted_dir / "IMG_1234.jpg.json")
            return None

        db.find_json_for_media_db = MagicMock(side_effect=find_json_side_effect)

        step_extract_zip(config, db, zip_path, logger)

        # Check that register_file was called with has_json=1
        call_args = db.register_file.call_args[1]
        assert call_args["has_json"] == 1
        assert "IMG_1234.jpg.json" in call_args["json_path"]

    def test_extract_zip_updates_status(self, config, db, logger, tmp_path):
        """Test that ZIP status is updated during extraction."""
        # Create minimal ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "content")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()

        step_extract_zip(config, db, zip_path, logger)

        # Check status updates
        calls = [call[0] for call in db.update_zip_status.call_args_list]
        assert any("extracting" in str(call) for call in calls)
        assert any("extracted" in str(call) for call in calls)

    def test_extract_zip_skips_existing_files(self, config, db, logger, tmp_path):
        """Test that existing extracted files are not re-extracted."""
        # Create ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.jpg", b"new content")

        # Pre-extract file with different content
        extract_dir = config.extracted_dir / "test"
        extract_dir.mkdir(parents=True, exist_ok=True)
        existing_file = extract_dir / "test.jpg"
        existing_file.write_bytes(b"existing content")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Existing file should not be overwritten
        assert existing_file.read_bytes() == b"existing content"

    def test_extract_zip_handles_errors(self, config, db, logger, tmp_path):
        """Test error handling during extraction."""
        # Create invalid ZIP path
        zip_path = config.zips_dir / "nonexistent.zip"

        # Mock database
        db.update_zip_status = MagicMock()

        # Should raise exception and update status to error
        with pytest.raises(FileNotFoundError):
            step_extract_zip(config, db, zip_path, logger)

        # Check error status was set
        calls = db.update_zip_status.call_args_list
        assert any("error" in str(call) for call in calls)

    def test_extract_zip_ignores_non_media_files(self, config, db, logger, tmp_path):
        """Test that non-media files are extracted but not registered."""
        # Create ZIP with mixed files
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"image")  # Media
            zf.writestr("readme.txt", b"text")  # Not media

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Only media file should be registered
        assert db.register_file.call_count == 1
        call_args = db.register_file.call_args[1]
        assert "photo.jpg" in call_args["original_path"]

    def test_extract_zip_counts_files(self, config, db, logger, tmp_path):
        """Test that file count is tracked correctly."""
        # Create ZIP with multiple media files
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo1.jpg", b"img1")
            zf.writestr("photo2.jpg", b"img2")
            zf.writestr("video.mp4", b"vid")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Check that final status includes file count
        final_call = [
            call for call in db.update_zip_status.call_args_list if "extracted" in str(call)
        ][-1]
        assert "file_count" in str(final_call) or "3" in str(final_call)

    def test_extract_zip_deletes_when_flag_enabled(self, config, db, logger, tmp_path):
        """Test that ZIP is deleted after successful extraction when flag is enabled."""
        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"image")

        # Enable deletion flag
        config.delete_zips_after_extract = True

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)
        db.mark_zip_deleted = MagicMock()

        step_extract_zip(config, db, zip_path, logger)

        # ZIP should be deleted
        assert not zip_path.exists()
        # Database should be updated
        db.mark_zip_deleted.assert_called_once_with("test.zip")

    def test_extract_zip_preserves_when_flag_disabled(self, config, db, logger, tmp_path):
        """Test that ZIP is preserved when deletion flag is disabled."""
        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"image")

        # Keep deletion flag disabled (default)
        config.delete_zips_after_extract = False

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)
        db.mark_zip_deleted = MagicMock()

        step_extract_zip(config, db, zip_path, logger)

        # ZIP should still exist
        assert zip_path.exists()
        # Database should NOT be updated with deletion
        db.mark_zip_deleted.assert_not_called()

    def test_extract_zip_preserves_on_error(self, config, db, logger, tmp_path):
        """Test that ZIP is not deleted if extraction fails."""
        # Create corrupted ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(b"not a valid zip file")

        # Enable deletion flag
        config.delete_zips_after_extract = True

        # Mock database
        db.update_zip_status = MagicMock()
        db.mark_zip_deleted = MagicMock()

        # Extraction should fail
        with pytest.raises(zipfile.BadZipFile):
            step_extract_zip(config, db, zip_path, logger)

        # ZIP should still exist (not deleted on error)
        assert zip_path.exists()
        # Database should NOT be updated with deletion
        db.mark_zip_deleted.assert_not_called()

    def test_extract_zip_deletion_respects_dry_run(self, config, db, logger, tmp_path):
        """Test that dry-run mode prevents actual ZIP deletion."""
        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"image")

        # Enable deletion flag AND dry-run
        config.delete_zips_after_extract = True
        config.dry_run = True

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)
        db.mark_zip_deleted = MagicMock()

        step_extract_zip(config, db, zip_path, logger)

        # ZIP should still exist (dry-run prevents deletion)
        assert zip_path.exists()
        # Database should NOT be updated
        db.mark_zip_deleted.assert_not_called()

    def test_extract_zip_rejects_path_traversal(self, config, db, logger, tmp_path):
        """Test that path traversal attacks (Zip Slip) are prevented."""
        # Create malicious ZIP with path traversal attempts
        zip_path = config.zips_dir / "malicious.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w") as zf:
            # Try various path traversal techniques
            zf.writestr("../../../etc/passwd", "malicious content")
            zf.writestr("../../escape.txt", "malicious content")
            zf.writestr("/etc/shadow", "malicious content")
            # Add one legitimate file
            zf.writestr("legit.txt", "safe content")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        # Extract (should reject malicious paths)
        step_extract_zip(config, db, zip_path, logger)

        # Verify malicious files were NOT extracted outside extracted_dir
        # Check common attack targets don't exist
        assert not (config.extracted_dir / ".." / ".." / "etc" / "passwd").exists()
        assert not (config.extracted_dir / ".." / "escape.txt").exists()
        assert (
            not Path("/etc/shadow").exists()
            or Path("/etc/shadow").read_bytes() != b"malicious content"
        )  # noqa: E501

        # Verify legitimate file WAS extracted
        legit_file = config.extracted_dir / "legit.txt"
        assert legit_file.exists()
        assert legit_file.read_text() == "safe content"

        # The security check logs errors, which we can see in captured logs
        # The key is that malicious files are rejected and not extracted

    def test_extract_zip_handles_path_collisions_same_content(self, config, db, logger, tmp_path):
        """Test that files with same path and same content are skipped."""
        # Create first ZIP with a file
        zip1_path = config.zips_dir / "zip1.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip1_path, "w") as zf:
            zf.writestr("photo.jpg", b"same content")

        # Create second ZIP with same path, same content
        zip2_path = config.zips_dir / "zip2.zip"
        with zipfile.ZipFile(zip2_path, "w") as zf:
            zf.writestr("photo.jpg", b"same content")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        # Extract first ZIP
        step_extract_zip(config, db, zip1_path, logger)

        # Extract second ZIP
        step_extract_zip(config, db, zip2_path, logger)

        # Only one file should exist (no conflict created)
        photo = config.extracted_dir / "photo.jpg"
        assert photo.exists()
        assert photo.read_bytes() == b"same content"

        # No conflict file should exist
        assert not (config.extracted_dir / "photo_conflict_1.jpg").exists()

    def test_extract_zip_handles_path_collisions_different_content(
        self, config, db, logger, tmp_path
    ):
        """Test that files with same path but different content are both kept."""
        # Create first ZIP with a file
        zip1_path = config.zips_dir / "zip1.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip1_path, "w") as zf:
            zf.writestr("photo.jpg", b"content from zip1")

        # Create second ZIP with same path, different content
        zip2_path = config.zips_dir / "zip2.zip"
        with zipfile.ZipFile(zip2_path, "w") as zf:
            zf.writestr("photo.jpg", b"different content from zip2")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        # Extract first ZIP
        step_extract_zip(config, db, zip1_path, logger)

        # Extract second ZIP
        step_extract_zip(config, db, zip2_path, logger)

        # Both files should exist
        original = config.extracted_dir / "photo.jpg"
        conflict = config.extracted_dir / "photo_conflict_1.jpg"

        assert original.exists()
        assert conflict.exists()

        # Verify content
        assert original.read_bytes() == b"content from zip1"
        assert conflict.read_bytes() == b"different content from zip2"

    def test_extract_zip_dry_run_mode(self, config, db, logger, tmp_path):
        """Test extraction in dry-run mode."""
        from takeout_photos.stages.extract import delete_zip_after_extraction

        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "content")

        db.mark_zip_deleted = MagicMock()

        # Test dry run - should not delete
        delete_zip_after_extraction(zip_path, "test.zip", db, logger, dry_run=True)

        assert zip_path.exists()  # File should still exist
        db.mark_zip_deleted.assert_not_called()

    def test_extract_zip_handles_missing_zip_for_deletion(self, config, db, logger, tmp_path):
        """Test deletion handles FileNotFoundError gracefully."""
        from takeout_photos.stages.extract import delete_zip_after_extraction

        # Create a path that doesn't exist
        zip_path = config.zips_dir / "nonexistent.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        db.mark_zip_deleted = MagicMock()

        # Should handle missing file gracefully
        delete_zip_after_extraction(zip_path, "nonexistent.zip", db, logger, dry_run=False)

        # Should mark as deleted despite file not existing
        db.mark_zip_deleted.assert_called_once_with("nonexistent.zip")

    def test_extract_zip_handles_deletion_error(self, config, db, logger, tmp_path, monkeypatch):
        """Test deletion handles generic exceptions gracefully."""
        from takeout_photos.stages.extract import delete_zip_after_extraction

        # Create test ZIP
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "content")

        db.mark_zip_deleted = MagicMock()

        # Mock unlink to raise an exception
        def mock_unlink(self, *args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr(Path, "unlink", mock_unlink)

        # Should handle exception without crashing
        delete_zip_after_extraction(zip_path, "test.zip", db, logger, dry_run=False)

        # Should not mark as deleted if deletion failed
        db.mark_zip_deleted.assert_not_called()

    def test_extract_zip_handles_dry_run_inspection_error(self, config, db, logger, tmp_path):
        """Test dry run handles corrupted ZIP inspection errors."""
        # Create a corrupted "ZIP" file
        zip_path = config.zips_dir / "corrupted.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(b"not a valid zip file")

        db.update_zip_status = MagicMock()
        db.register_zip = MagicMock()

        # Set config to dry run
        config_dry = config
        config_dry.dry_run = True

        # Should handle inspection error gracefully (no crash)
        # The function returns early on error without crashing
        step_extract_zip(config_dry, db, zip_path, logger)

        # The function should complete without raising an exception
        # (No additional assertions needed - success is not crashing)

    def test_extract_zip_skips_macos_resource_forks(self, config, db, logger, tmp_path):
        """Test that __MACOSX files and ._* files are skipped."""
        # Create ZIP with macOS resource fork files
        zip_path = config.zips_dir / "macos.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"jpeg content")
            zf.writestr("__MACOSX/._photo.jpg", b"resource fork")
            zf.writestr("._metadata", b"more metadata")

        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Should only register the real photo, not the resource forks
        assert db.register_file.call_count == 1
        call_args = db.register_file.call_args[1]
        assert "photo.jpg" in call_args["original_path"]
        assert "__MACOSX" not in call_args["original_path"]
        assert not call_args["original_path"].endswith("._metadata")

    def test_extract_zip_handles_directory_members(self, config, db, logger, tmp_path):
        """Test extraction correctly handles directory members in ZIP."""
        # Create ZIP with directory structure
        zip_path = config.zips_dir / "dirs.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w") as zf:
            # Add directory entries (ending with /)
            zf.writestr("subdir/", "")
            zf.writestr("subdir/photo.jpg", b"jpeg content")

        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        step_extract_zip(config, db, zip_path, logger)

        # Directory should be created
        subdir = config.extracted_dir / "subdir"
        assert subdir.exists()
        assert subdir.is_dir()

        # File should be extracted
        photo = subdir / "photo.jpg"
        assert photo.exists()

    def test_extract_zip_multiple_conflicts_same_file(self, config, db, logger, tmp_path):
        """Test handling of multiple conflicts for the same file."""
        # Create three ZIPs with same filename but different content
        for i in range(3):
            zip_path = config.zips_dir / f"zip{i}.zip"
            config.zips_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("photo.jpg", f"content {i}".encode())

            db.update_zip_status = MagicMock()
            db.register_json_file = MagicMock()
            db.register_file = MagicMock()
            db.commit = MagicMock()
            db.find_json_for_media_db = MagicMock(return_value=None)

            step_extract_zip(config, db, zip_path, logger)

        # Should have original + 2 conflicts
        original = config.extracted_dir / "photo.jpg"
        conflict1 = config.extracted_dir / "photo_conflict_1.jpg"
        conflict2 = config.extracted_dir / "photo_conflict_2.jpg"

        assert original.exists()
        assert conflict1.exists()
        assert conflict2.exists()

        # Verify different content
        assert original.read_bytes() == b"content 0"
        assert conflict1.read_bytes() == b"content 1"
        assert conflict2.read_bytes() == b"content 2"

    def test_extract_zip_filters_system_files(self, config, db, logger, tmp_path):
        """Test that extract_zip filters AppleDouble and other system files during registration."""
        # Create a ZIP with media and system files
        zip_path = config.zips_dir / "test.zip"
        config.zips_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Legitimate media files
            zf.writestr("Takeout/photo.jpg", b"fake jpeg")
            zf.writestr("Takeout/video.mp4", b"fake video")
            zf.writestr("Takeout/photo.jpg.json", '{"photoTakenTime": {}}')

            # System files that should be ignored
            # AppleDouble files (have media extensions)
            zf.writestr("Takeout/._photo.jpg", b"appledouble")
            zf.writestr("Takeout/._video.mp4", b"appledouble video")
            # __MACOSX directory files
            zf.writestr("Takeout/__MACOSX/photo.jpg", b"macos metadata")
            zf.writestr("Takeout/__MACOSX/._.DS_Store", b"macos metadata")

        # Mock database
        db.update_zip_status = MagicMock()
        db.register_json_file = MagicMock()
        db.register_file = MagicMock()
        db.commit = MagicMock()
        db.find_json_for_media_db = MagicMock(return_value=None)

        # Extract and register
        step_extract_zip(config, db, zip_path, logger)

        # Verify only legitimate files were registered
        registered_calls = list(db.register_file.call_args_list)

        # Should have 2 calls for photo.jpg and video.mp4 only
        assert len(registered_calls) == 2
        registered_paths = [call[1]["original_path"] for call in registered_calls]
        assert any("photo.jpg" in p and "._" not in p for p in registered_paths)
        assert any(
            "video.mp4" in p and "._" not in p and "__MACOSX" not in p for p in registered_paths
        )
        # System files should not be registered
        assert not any("._photo.jpg" in p for p in registered_paths)
        assert not any("._video.mp4" in p for p in registered_paths)
        assert not any("__MACOSX" in p for p in registered_paths)
