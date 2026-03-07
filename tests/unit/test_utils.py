"""
Unit tests for utility modules.

Tests cover logging setup, progress bar wrapper, media file detection,
and dependency checking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from takeout_photos.utils.dependencies import check_dependencies
from takeout_photos.utils.logging_setup import setup_logging
from takeout_photos.utils.progress import is_media_file, progress_bar


class TestLoggingSetup:
    """Test logging configuration."""

    def test_setup_logging_creates_log_file(self, test_config, temp_dir):
        """Should create timestamped log file in logs directory."""
        _log, _timestamp = setup_logging(test_config)

        assert test_config.logs_dir.exists()
        log_files = list(test_config.logs_dir.glob("*_run.log"))
        assert len(log_files) == 1
        assert log_files[0].name.endswith("_run.log")

    def test_setup_logging_returns_logger(self, test_config):
        """Should return configured logger instance."""
        log, timestamp = setup_logging(test_config)

        assert isinstance(log, logging.Logger)

    def test_setup_logging_verbose_mode(self, temp_dir):
        """Should work with verbose mode enabled."""
        from takeout_photos.core.config import Config

        config = Config(workdir=temp_dir, verbose=True)
        log, timestamp = setup_logging(config)

        # Should create log file and return logger
        assert isinstance(log, logging.Logger)
        assert config.logs_dir.exists()

    def test_setup_logging_normal_mode(self, temp_dir):
        """Should work with verbose mode disabled."""
        from takeout_photos.core.config import Config

        config = Config(workdir=temp_dir, verbose=False)
        log, timestamp = setup_logging(config)

        # Should create log file and return logger
        assert isinstance(log, logging.Logger)
        assert config.logs_dir.exists()

    def test_setup_logging_creates_logs_dir_if_missing(self, temp_dir):
        """Should create logs directory if it doesn't exist."""
        from takeout_photos.core.config import Config

        config = Config(workdir=temp_dir)
        # Ensure logs_dir doesn't exist
        if config.logs_dir.exists():
            config.logs_dir.rmdir()

        log, timestamp = setup_logging(config)

        assert config.logs_dir.exists()

    def test_setup_logging_returns_timestamp(self, tmp_path):
        """Test that setup_logging returns both logger and timestamp."""
        from takeout_photos.core.config import Config

        config = Config(workdir=tmp_path, verbose=True)

        result = setup_logging(config)

        # Should return tuple of (logger, timestamp)
        assert isinstance(result, tuple)
        assert len(result) == 2
        logger, timestamp = result
        assert isinstance(logger, logging.Logger)
        assert isinstance(timestamp, str)
        assert len(timestamp) == 15  # YYYYMMDD_HHMMSS


class TestProgressBar:
    """Test progress bar wrapper."""

    def test_progress_bar_with_tqdm_available(self):
        """Should return tqdm-wrapped iterable when tqdm is available."""
        items = [1, 2, 3, 4, 5]

        result = progress_bar(items, desc="Test")

        # Result should be iterable
        assert hasattr(result, "__iter__")
        # Should still return all items
        assert list(result) == items

    def test_progress_bar_returns_iterable_when_disabled(self):
        """Should return plain iterable when explicitly disabled."""
        items = [1, 2, 3, 4, 5]

        result = progress_bar(items, disable=True)

        # Should return original iterable
        assert result == items

    def test_progress_bar_with_total_parameter(self):
        """Should accept total parameter for progress tracking."""
        items = [1, 2, 3, 4, 5]

        result = progress_bar(items, total=5, desc="Test")

        # Should not raise
        assert list(result) == items

    def test_progress_bar_with_description(self):
        """Should accept description parameter."""
        items = [1, 2, 3]

        result = progress_bar(items, desc="Processing items")

        # Should not raise
        assert list(result) == items

    @patch("takeout_photos.utils.progress.use_tqdm", False)
    def test_progress_bar_fallback_when_tqdm_unavailable(self):
        """Should return plain iterable when tqdm is not available."""
        items = [1, 2, 3, 4, 5]

        result = progress_bar(items, desc="Test")

        # Should return original iterable when tqdm not available
        assert result == items


class TestMediaFileDetection:
    """Test media file type detection."""

    def test_is_media_file_recognizes_jpg(self):
        """Should recognize .jpg files as media."""
        assert is_media_file(Path("photo.jpg")) is True
        assert is_media_file(Path("photo.JPG")) is True
        assert is_media_file(Path("photo.JPEG")) is True

    def test_is_media_file_recognizes_png(self):
        """Should recognize .png files as media."""
        assert is_media_file(Path("image.png")) is True
        assert is_media_file(Path("image.PNG")) is True

    def test_is_media_file_recognizes_heic(self):
        """Should recognize .heic files as media."""
        assert is_media_file(Path("photo.heic")) is True
        assert is_media_file(Path("photo.HEIC")) is True
        assert is_media_file(Path("photo.heif")) is True

    def test_is_media_file_recognizes_videos(self):
        """Should recognize video formats as media."""
        assert is_media_file(Path("video.mp4")) is True
        assert is_media_file(Path("video.mov")) is True
        assert is_media_file(Path("video.avi")) is True
        assert is_media_file(Path("video.mkv")) is True
        assert is_media_file(Path("video.mpg")) is True

    def test_is_media_file_recognizes_raw_formats(self):
        """Should recognize RAW photo formats as media."""
        assert is_media_file(Path("photo.raw")) is True
        assert is_media_file(Path("photo.cr2")) is True
        assert is_media_file(Path("photo.nef")) is True
        assert is_media_file(Path("photo.arw")) is True

    def test_is_media_file_rejects_non_media(self):
        """Should reject non-media file types."""
        assert is_media_file(Path("document.pdf")) is False
        assert is_media_file(Path("spreadsheet.xlsx")) is False
        assert is_media_file(Path("text.txt")) is False
        assert is_media_file(Path("archive.zip")) is False
        assert is_media_file(Path("metadata.json")) is False

    def test_is_media_file_case_insensitive(self):
        """Should be case-insensitive for extensions."""
        assert is_media_file(Path("photo.JpG")) is True
        assert is_media_file(Path("video.Mp4")) is True
        assert is_media_file(Path("image.PnG")) is True

    def test_is_media_file_with_path_components(self):
        """Should work with full paths, not just filenames."""
        assert is_media_file(Path("/path/to/photo.jpg")) is True
        assert is_media_file(Path("/path/to/document.txt")) is False


class TestDependencyChecking:
    """Test dependency verification."""

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_all_satisfied(self, mock_print, mock_run, mock_which):
        """Should return True when all dependencies are satisfied."""
        # Mock exiftool available
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=False)

        assert result is True

    @patch("shutil.which")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_missing_exiftool(self, mock_print, mock_which):
        """Should return False when exiftool is missing."""
        # Mock exiftool not available
        mock_which.return_value = None

        result = check_dependencies(verbose=False)

        assert result is False

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_verbose_mode(self, mock_print, mock_run, mock_which):
        """Should show detailed info in verbose mode."""
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=True)

        assert result is True
        # Verify print was called (verbose output)
        assert mock_print.called

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_handles_exiftool_version_error(
        self, mock_print, mock_run, mock_which
    ):
        """Should handle errors when checking exiftool version."""
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.side_effect = Exception("Command failed")

        # Should still return True (exiftool is available, just version check failed)
        result = check_dependencies(verbose=False)

        assert result is True

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("sys.platform", "darwin")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_shows_macos_instructions(self, mock_print, mock_run, mock_which):
        """Should show macOS-specific install instructions."""
        mock_which.return_value = None  # exiftool missing

        result = check_dependencies(verbose=False)

        assert result is False
        # Check that print was called with brew install instruction
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("brew install" in str(call) for call in print_calls)

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("sys.platform", "linux")
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_shows_linux_instructions(self, mock_print, mock_run, mock_which):
        """Should show Linux-specific install instructions."""
        mock_which.return_value = None  # exiftool missing

        result = check_dependencies(verbose=False)

        assert result is False
        # Check that print was called with apt-get instruction
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("apt-get" in str(call) for call in print_calls)

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.use_xxhash", False)
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_missing_xxhash(self, mock_print, mock_run, mock_which):
        """Should show warning when xxhash is not available."""
        # Mock exiftool available
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=False)

        # Should still return True (xxhash is optional)
        assert result is True

        # Check that warning message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("xxhash" in str(call).lower() for call in print_calls)
        assert any("optional" in str(call).lower() for call in print_calls)

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.use_tqdm", False)
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_missing_tqdm(self, mock_print, mock_run, mock_which):
        """Should show warning when tqdm is not available."""
        # Mock exiftool available
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=False)

        # Should still return True (tqdm is optional)
        assert result is True

        # Check that warning message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("tqdm" in str(call).lower() for call in print_calls)
        assert any("progress bar" in str(call).lower() for call in print_calls)

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.use_xxhash", False)
    @patch("takeout_photos.utils.dependencies.use_tqdm", False)
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_missing_both_optional(self, mock_print, mock_run, mock_which):
        """Should show warnings when both optional packages are missing."""
        # Mock exiftool available
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=False)

        # Should still return True (both are optional)
        assert result is True

        # Check that both warnings were printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("xxhash" in str(call).lower() for call in print_calls)
        assert any("tqdm" in str(call).lower() for call in print_calls)
        assert any("2 optional package" in str(call).lower() for call in print_calls)

    @patch("shutil.which")
    @patch("subprocess.run")
    @patch("takeout_photos.utils.dependencies.use_xxhash", False)
    @patch("takeout_photos.utils.dependencies.sys.version_info", (3, 10, 0))
    @patch("builtins.print")
    def test_check_dependencies_shows_install_instructions(self, mock_print, mock_run, mock_which):
        """Should show pip install instructions for missing optional packages."""
        # Mock exiftool available
        mock_which.return_value = "/usr/local/bin/exiftool"
        mock_run.return_value = MagicMock(stdout="12.50\n")

        result = check_dependencies(verbose=False)

        assert result is True

        # Check that pip install instruction is shown
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any("pip install" in str(call) for call in print_calls)


class TestUtilityIntegration:
    """Integration tests for utility modules."""

    def test_logging_and_progress_together(self, test_config):
        """Should be able to use logging and progress bar together."""
        log, timestamp = setup_logging(test_config)

        items = [1, 2, 3, 4, 5]
        for item in progress_bar(items, desc="Processing"):
            log.debug(f"Processing item: {item}")

        # Should not raise

    def test_media_detection_with_real_paths(self, temp_dir):
        """Should correctly identify media files in directory structure."""
        # Create test files
        media_files = [
            temp_dir / "photo.jpg",
            temp_dir / "video.mp4",
            temp_dir / "image.png",
        ]
        non_media_files = [
            temp_dir / "metadata.json",
            temp_dir / "readme.txt",
        ]

        for f in media_files + non_media_files:
            f.touch()

        # Check detection
        media_count = sum(1 for f in temp_dir.iterdir() if is_media_file(f))
        assert media_count == 3
