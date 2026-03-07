"""Test version display functionality."""

from __future__ import annotations

import subprocess
import sys

from takeout_photos import __version__


def test_version_import():
    """Test that __version__ is defined and valid."""
    assert __version__
    assert isinstance(__version__, str)
    # Semver format: major.minor.patch
    parts = __version__.split(".")
    assert len(parts) == 3
    # Each part should be numeric
    for part in parts:
        assert part.isdigit()


def test_version_flag_cli():
    """Test --version flag via CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "takeout_photos.cli.main", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
    assert "takeout-photos" in result.stdout
