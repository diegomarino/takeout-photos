"""Regression: manual files dropped in extracted/ (no ZIP) are recovered AND organized.

docs/api.md documents "Manual files added to extracted/" as a supported recovery
scenario. Previously the orphan recovery registered those files under a synthetic
``zip_name="unknown"`` (no ``.zip`` suffix) and left the zip row ``status='pending'``.
As a result:

- every downstream stage queries via ``get_files_for_zip()`` which appends
  ``.zip``, so it silently found zero files for the "unknown" batch, and
- ``get_zips_needing_processing()`` only returns ``extracted``/``processing`` zips,
  so nothing advanced past registration anyway.

The fix registers the synthetic zip under a reserved sentinel name
(``RECOVERED_ORPHANS_ZIP``) with ``status='extracted'``. This test asserts the
files reach ``organized_media/`` — not merely that they get registered in the
database — and that a physical archive using the reserved name is ignored.
"""

from __future__ import annotations

import shutil

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.constants import RECOVERED_ORPHANS_ZIP
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline

# exiftool is required to write/read real embedded EXIF (make_jpeg_with_exif).
requires_exiftool = pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="exiftool not installed"
)


@requires_exiftool
def test_manual_files_in_extracted_are_organized(tmp_path, make_jpeg_with_exif):
    """A plain `process` run on loose files in extracted/ organizes them by date."""
    config = Config(workdir=tmp_path, skip_deps_check=True)

    # Drop loose images with real embedded EXIF directly into extracted/, no ZIP,
    # no JSON, no prior DB registration — exactly the "manual files" scenario.
    config.extracted_dir.mkdir(parents=True, exist_ok=True)
    dates = {
        "manual1.jpg": "2022:04:10 11:00:00",
        "manual2.jpg": "2017:11:30 23:59:00",
    }
    for name, date in dates.items():
        make_jpeg_with_exif(config.extracted_dir / name, date=date)

    # Recovery runs on Pipeline construction; run() then processes the batch.
    with Pipeline(config) as pipeline:
        pipeline.run()

    # The synthetic zip must be ".zip"-suffixed and fully processed.
    db = PipelineDB(config.db_path)
    try:
        status = db.get_zip_status(RECOVERED_ORPHANS_ZIP)
        assert status == "organized", f"expected recovered zip organized, got {status!r}"

        # Bare "unknown" must NOT exist (that was the bug).
        assert db.get_zip_status("unknown") is None

        # Files reached organized_media/, bucketed by their embedded dates.
        assert (config.organized_dir / "2022" / "2022_04" / "manual1.jpg").exists()
        assert (config.organized_dir / "2017" / "2017_11" / "manual2.jpg").exists()

        # Nothing stranded in no_date/ and none left unprocessed in the DB.
        no_date = config.organized_dir / "no_date"
        assert not no_date.exists() or not any(no_date.rglob("*"))

        unprocessed = db.conn.execute(
            "SELECT COUNT(*) FROM files WHERE zip_name = ? AND status != 'organized'",
            (RECOVERED_ORPHANS_ZIP,),
        ).fetchone()[0]
        assert unprocessed == 0
    finally:
        db.close()


def test_reserved_recovery_zip_name_is_ignored_in_discovery(tmp_path, caplog):
    """A physical ZIP using the reserved recovery name is skipped with a warning.

    Hardening for the (extremely unlikely) case where a user drops a real archive
    literally named like the internal orphan-recovery sentinel. It must not be
    conflated with the synthetic recovery batch: discovery skips it and warns,
    turning a would-be silent "real zip never extracted" into a visible message.
    """
    config = Config(workdir=tmp_path, skip_deps_check=True)

    with Pipeline(config) as pipeline:
        assert config.zips_dir is not None
        # A real archive colliding with the reserved name, plus a normal one.
        (config.zips_dir / RECOVERED_ORPHANS_ZIP).write_bytes(b"PK\x03\x04")
        (config.zips_dir / "takeout-001.zip").write_bytes(b"PK\x03\x04")

        with caplog.at_level("WARNING"):
            discovered = pipeline._discover_and_register_zips()

        names = {p.name for p in discovered}
        assert "takeout-001.zip" in names
        assert RECOVERED_ORPHANS_ZIP not in names

        # The reserved name is not registered as a real ZIP; the normal one is.
        assert pipeline.db.get_zip_status(RECOVERED_ORPHANS_ZIP) is None
        assert pipeline.db.get_zip_status("takeout-001.zip") == "pending"

        # The collision was surfaced loudly.
        assert any("reserved" in r.message.lower() for r in caplog.records)
