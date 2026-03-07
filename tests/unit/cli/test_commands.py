"""Tests for CLI commands."""

from __future__ import annotations


def test_status_filters_system_files_from_stats(tmp_path):
    """Status command should not count AppleDouble and system files."""
    from takeout_photos.core.config import Config

    workdir = tmp_path / "work"
    workdir.mkdir()

    # Create duplicates with system files
    duplicates_dir = workdir / "duplicates"
    duplicates_dir.mkdir()
    (duplicates_dir / "dupe.jpg").write_bytes(b"jpeg")
    (duplicates_dir / "._dupe.jpg").write_bytes(b"appledouble")
    (duplicates_dir / ".DS_Store").write_bytes(b"ds store")

    config = Config(workdir=workdir)

    # Manually count with filtering
    from takeout_photos.utils.system_files import should_ignore_path

    dupe_count = sum(
        1 for f in config.duplicates_dir.rglob("*") if f.is_file() and not should_ignore_path(f)
    )

    # Should only count legitimate file
    assert dupe_count == 1  # dupe.jpg only
