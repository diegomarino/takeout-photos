"""Integration tests for system files filtering across pipeline."""

import logging
import zipfile

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline


def test_full_pipeline_filters_system_files(tmp_path):
    """
    Full pipeline should filter AppleDouble and system files at all stages.

    Creates a realistic ZIP with media, JSON, and various OS system files,
    then verifies they are filtered throughout the pipeline.
    """
    workdir = tmp_path / "work"
    workdir.mkdir()

    # Create ZIP with mixed content
    zip_path = workdir / "takeout-001.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Legitimate media + JSON
        zf.writestr("Takeout/Google Photos/photo.jpg", b"fake jpeg data")
        zf.writestr(
            "Takeout/Google Photos/photo.jpg.json",
            '{"photoTakenTime": {"timestamp": "1609459200"}}',
        )
        zf.writestr("Takeout/Google Photos/_7A_0520.jpg", b"legitimate underscore file")
        zf.writestr(
            "Takeout/Google Photos/_7A_0520.jpg.json",
            '{"photoTakenTime": {"timestamp": "1609459200"}}',
        )

        # AppleDouble files (should be filtered)
        zf.writestr("Takeout/Google Photos/._photo.jpg", b"appledouble resource fork")
        zf.writestr("Takeout/Google Photos/._photo.jpg.json", b"appledouble json")
        zf.writestr("Takeout/._Google Photos", b"appledouble folder")

        # Other system files (should be filtered)
        zf.writestr("Takeout/Google Photos/.DS_Store", b"finder metadata")
        zf.writestr("Takeout/Google Photos/Thumbs.db", b"windows thumbnail cache")
        zf.writestr("__MACOSX/Takeout/photo.jpg", b"macos zip metadata")

    # Configure and run pipeline
    config = Config(workdir=workdir)
    db = PipelineDB(config.db_path)

    with Pipeline(config) as pipeline:
        # Phase 1: Extract
        pipeline.extract_all_zips()

        # Verify only legitimate files in database
        files = db.conn.execute("SELECT original_path FROM files").fetchall()
        paths = [row["original_path"] for row in files]

        # Should have 2 files: photo.jpg and _7A_0520.jpg
        assert len(paths) == 2
        assert any("photo.jpg" in p and "._" not in p for p in paths)
        assert any("_7A_0520.jpg" in p for p in paths)

        # Should NOT have system files
        assert not any("._photo.jpg" in p for p in paths)
        assert not any(".DS_Store" in p for p in paths)
        assert not any("Thumbs.db" in p for p in paths)
        assert not any("__MACOSX" in p for p in paths)

    db.close()


def test_recovery_ignores_manually_added_system_files(tmp_path):
    """
    Recovery should not register manually added system files as orphans.

    Simulates user manually copying files to extracted/ directory.
    """
    workdir = tmp_path / "work"
    workdir.mkdir()
    extracted_dir = workdir / "extracted"
    extracted_dir.mkdir()

    # Create extracted files (not in database)
    (extracted_dir / "photo.jpg").write_bytes(b"jpeg")
    (extracted_dir / "._photo.jpg").write_bytes(b"appledouble")
    (extracted_dir / ".DS_Store").write_bytes(b"ds store")

    config = Config(workdir=workdir)
    db = PipelineDB(config.db_path)

    # Run recovery
    from takeout_photos.core.recovery import RecoveryManager

    log = logging.getLogger(__name__)
    recovery = RecoveryManager(config, db, log, dry_run=False)
    recovery.check_and_recover()

    # Verify only legitimate file was registered
    files = db.conn.execute("SELECT original_path FROM files").fetchall()
    paths = [row["original_path"] for row in files]

    assert len(paths) == 1
    assert "photo.jpg" in paths[0]
    assert not any("._" in p for p in paths)
    assert not any(".DS_Store" in p for p in paths)

    db.close()


def test_qc_excludes_system_files_from_reports(tmp_path):
    """QC reports should not include AppleDouble files in statistics."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    organized_dir = workdir / "organized_media"
    organized_dir.mkdir()

    # Create no_date folder with mixed files
    no_date = organized_dir / "no_date"
    no_date.mkdir()
    (no_date / "photo1.jpg").write_bytes(b"jpeg")
    (no_date / "photo2.jpg").write_bytes(b"jpeg")
    (no_date / "._photo1.jpg").write_bytes(b"appledouble")
    (no_date / ".DS_Store").write_bytes(b"ds store")

    config = Config(workdir=workdir)

    # Run QC
    from takeout_photos.stages.qc import step_qc

    log = logging.getLogger(__name__)
    step_qc(config, None, log)

    # Read generated QC report
    qc_files = list(config.logs_dir.glob("*_qc.txt"))
    assert len(qc_files) == 1

    content = qc_files[0].read_text()

    # Report should show 2 files in no_date (not 4)
    # Check that "Files without DateTimeOriginal: 2" is in the report
    assert "Files without DateTimeOriginal: 2" in content
    # Check that total count is also 2 (not 4)
    assert "Total files organized: 2" in content
