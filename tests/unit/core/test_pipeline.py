"""Tests for Pipeline class."""

from __future__ import annotations


def test_discover_zips_filters_system_files(tmp_path):
    """_discover_and_register_zips should filter AppleDouble and other system files."""
    from takeout_photos.core.config import Config
    from takeout_photos.core.database import PipelineDB
    from takeout_photos.core.pipeline import Pipeline

    # Create workdir with ZIPs and system files
    workdir = tmp_path / "work"
    workdir.mkdir()
    zips_dir = workdir

    # Create legitimate ZIP
    (zips_dir / "takeout-001.zip").touch()

    # Create system files that should be ignored
    (zips_dir / "._takeout-001.zip").touch()  # AppleDouble
    (zips_dir / ".DS_Store").touch()  # macOS

    config = Config(workdir=workdir)
    db = PipelineDB(config.db_path)

    pipeline = Pipeline(config)
    zips = pipeline._discover_and_register_zips()

    # Only legitimate ZIP should be discovered
    assert len(zips) == 1
    assert zips[0].name == "takeout-001.zip"

    # Verify system files are NOT in database
    all_zips = db.conn.execute("SELECT name FROM zips").fetchall()
    zip_names = [row["name"] for row in all_zips]
    assert "._takeout-001.zip" not in zip_names
    assert ".DS_Store" not in zip_names

    pipeline.close()
