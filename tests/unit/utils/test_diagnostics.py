"""Tests for diagnostics (doctor command)."""

from __future__ import annotations

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.utils.diagnostics import cmd_doctor


def test_doctor_without_workdir():
    """Test doctor command without workdir (dependencies only)."""
    exit_code = cmd_doctor(config=None)
    assert exit_code in [0, 2], "Should check dependencies and return 0 or 2"


def test_doctor_with_clean_workdir(tmp_path):
    """Test doctor command with clean workdir."""
    config = Config(workdir=tmp_path)

    exit_code = cmd_doctor(config=config)
    assert exit_code == 0, "Clean workdir should return 0"


def test_doctor_with_recovery_issues(tmp_path):
    """Test doctor command detects recovery issues."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)

    # Create recovery issue
    db.register_zip("test")
    db.update_zip_status("test", "extracting")

    exit_code = cmd_doctor(config=config)
    assert exit_code == 1, "Recovery issues should return 1 (warning)"
