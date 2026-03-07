"""Tests for Config dataclass."""

from __future__ import annotations

from pathlib import Path

from takeout_photos.core.config import Config


class TestConfig:
    """Test suite for Config dataclass."""

    def test_config_checkpoint_interval_default(self):
        """Test checkpoint_interval defaults to 100."""
        config = Config(workdir=Path("/tmp/test"))
        assert config.checkpoint_interval == 100

    def test_config_checkpoint_interval_custom(self):
        """Test checkpoint_interval can be customized."""
        config = Config(workdir=Path("/tmp/test"), checkpoint_interval=50)
        assert config.checkpoint_interval == 50

    def test_config_dated_filenames_default(self):
        """Test dated_filenames defaults to False."""
        config = Config(workdir=Path("/tmp/test"))
        assert config.dated_filenames is False

    def test_config_dated_filenames_enabled(self):
        """Test dated_filenames can be set to True."""
        config = Config(workdir=Path("/tmp/test"), dated_filenames=True)
        assert config.dated_filenames is True

    def test_config_exif_warnings_file_defaults_to_none(self, tmp_path):
        """Test that exif_warnings_file defaults to None."""
        config = Config(workdir=tmp_path)
        assert config.exif_warnings_file is None

    def test_config_exif_warnings_file_can_be_set(self, tmp_path):
        """Test that exif_warnings_file can be set."""
        warnings_file = tmp_path / "logs" / "20260130_120000_exif_warnings.txt"
        config = Config(workdir=tmp_path, exif_warnings_file=warnings_file)
        assert config.exif_warnings_file == warnings_file
