"""Tests for system file filtering."""

from pathlib import Path

from takeout_photos.utils.system_files import should_ignore_path


class TestShouldIgnorePath:
    """Test system file filtering logic."""

    # AppleDouble files (PRIMARY ISSUE)
    def test_ignores_appledouble_files(self):
        """AppleDouble resource fork files should be ignored."""
        assert should_ignore_path(Path("._photo.jpg")) is True
        assert should_ignore_path(Path("._metadata.json")) is True
        assert should_ignore_path(Path("._takeout.zip")) is True
        assert should_ignore_path(Path("/path/to/._file.mp4")) is True

    def test_preserves_underscore_prefixed_files(self):
        """Files starting with underscore (not dot-underscore) should NOT be ignored."""
        assert should_ignore_path(Path("_7A_0520.jpg")) is False
        assert should_ignore_path(Path("_photo.mp4")) is False
        assert should_ignore_path(Path("_MG_1234.JPG")) is False
        assert should_ignore_path(Path("/path/_file.json")) is False

    # macOS system files
    def test_ignores_ds_store(self):
        """.DS_Store files should be ignored."""
        assert should_ignore_path(Path(".DS_Store")) is True
        assert should_ignore_path(Path("/path/to/.DS_Store")) is True

    def test_ignores_macos_system_files(self):
        """macOS system files and folders should be ignored."""
        assert should_ignore_path(Path(".Spotlight-V100")) is True
        assert should_ignore_path(Path(".Trashes")) is True
        assert should_ignore_path(Path(".TemporaryItems")) is True
        assert should_ignore_path(Path(".fseventsd")) is True

    def test_ignores_macosx_zip_folder(self):
        """__MACOSX folder in paths should be ignored."""
        assert should_ignore_path(Path("__MACOSX/file.jpg")) is True
        assert should_ignore_path(Path("/extract/__MACOSX/metadata.json")) is True
        assert should_ignore_path(Path("path/__MACOSX/nested/file.mp4")) is True

    # Windows system files
    def test_ignores_thumbs_db_case_insensitive(self):
        """Thumbs.db should be ignored (case insensitive)."""
        assert should_ignore_path(Path("Thumbs.db")) is True
        assert should_ignore_path(Path("thumbs.db")) is True
        assert should_ignore_path(Path("THUMBS.DB")) is True
        assert should_ignore_path(Path("/path/Thumbs.db")) is True

    def test_ignores_windows_system_files(self):
        """Windows system files should be ignored."""
        assert should_ignore_path(Path("Desktop.ini")) is True
        assert should_ignore_path(Path("desktop.ini")) is True
        assert should_ignore_path(Path("ehthumbs.db")) is True

    def test_ignores_recycle_bin(self):
        """$RECYCLE.BIN folder should be ignored."""
        assert should_ignore_path(Path("$RECYCLE.BIN/file.jpg")) is True
        assert should_ignore_path(Path("/path/$RECYCLE.BIN/file.mp4")) is True

    # Linux system files
    def test_ignores_directory_file(self):
        """.directory files should be ignored."""
        assert should_ignore_path(Path(".directory")) is True
        assert should_ignore_path(Path("/path/.directory")) is True

    def test_ignores_nfs_files(self):
        """NFS temporary files should be ignored."""
        assert should_ignore_path(Path(".nfs12345")) is True
        assert should_ignore_path(Path(".nfsABCDE")) is True
        assert should_ignore_path(Path("/path/.nfs00001")) is True

    def test_ignores_trash_folders(self):
        """.Trash-* folders should be ignored."""
        assert should_ignore_path(Path(".Trash-1000/file.jpg")) is True
        assert should_ignore_path(Path("/home/user/.Trash-500/photo.mp4")) is True

    # Regular files should NOT be ignored
    def test_preserves_legitimate_media_files(self):
        """Regular media files should NOT be ignored."""
        assert should_ignore_path(Path("photo.jpg")) is False
        assert should_ignore_path(Path("IMG_1234.JPG")) is False
        assert should_ignore_path(Path("video.mp4")) is False
        assert should_ignore_path(Path("metadata.json")) is False

    def test_preserves_legitimate_paths(self):
        """Regular paths should NOT be ignored."""
        assert should_ignore_path(Path("/path/to/photo.jpg")) is False
        assert should_ignore_path(Path("2020/05/IMG_1234.JPG")) is False
