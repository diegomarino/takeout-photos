"""Regression: loose images with real embedded EXIF (and no JSON) get organized by date.

Reproduces the non-Takeout input scenario: images that carry a valid
``DateTimeOriginal`` tag but have no Google Takeout JSON sidecar. Before the fix,
``step_validate_formats`` read the EXIF date and then discarded it on the common
"extension already correct" path, so ``organize`` sent every such file to
``organized_media/no_date/`` instead of ``organized_media/YYYY/YYYY_MM/``.

These tests drive the real batch stages (validate → metadata → hash → organize)
against real files with real EXIF — no mocking of the exiftool read path.
"""

from __future__ import annotations

import logging
import shutil

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.hash import step_compute_hashes
from takeout_photos.stages.metadata import step_apply_metadata
from takeout_photos.stages.organize import step_organize_files_from_zip
from takeout_photos.stages.validate import step_validate_formats

# exiftool is required to write/read real embedded EXIF (make_jpeg_with_exif).
requires_exiftool = pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="exiftool not installed"
)


def _register_loose_images(config: Config, db: PipelineDB, make_jpeg_with_exif, dates: dict):
    """Create loose JPEGs with embedded EXIF in extracted/ and register them (no JSON)."""
    for d in (config.extracted_dir, config.organized_dir, config.duplicates_dir):
        d.mkdir(parents=True, exist_ok=True)

    db.register_zip("test.zip")
    db.update_zip_status("test.zip", "extracted")

    for name, date in dates.items():
        path = make_jpeg_with_exif(config.extracted_dir / name, date=date)
        db.register_file(
            zip_name="test.zip",
            original_path=str(path),
            file_size=path.stat().st_size,
        )
    db.commit()


def _run_batch_stages(config: Config, db: PipelineDB, log: logging.Logger) -> dict:
    """Run the same batch stages the pipeline runs for a single ZIP."""
    step_validate_formats(config, db, "test", log)
    step_apply_metadata(config, db, "test", log)
    step_compute_hashes(config, db, "test", log)
    return step_organize_files_from_zip(config, db, "test", log)


@requires_exiftool
def test_embedded_exif_files_organized_by_date(tmp_path, make_jpeg_with_exif):
    """Files with embedded EXIF dates and no JSON land in YYYY/YYYY_MM, not no_date/."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger("test")

    dates = {
        "a.jpg": "2021:07:15 09:30:00",
        "b.jpg": "2019:12:25 18:00:00",
        "c.jpg": "2020:01:02 03:04:05",
    }
    _register_loose_images(config, db, make_jpeg_with_exif, dates)

    stats = _run_batch_stages(config, db, log)

    assert stats["errors"] == 0
    assert stats["organized"] == 3

    # The core assertion: nothing fell through to no_date/
    no_date = config.organized_dir / "no_date"
    assert not no_date.exists() or not any(no_date.rglob("*")), "files wrongly bucketed in no_date/"

    # Each file is bucketed by its real embedded capture date
    assert (config.organized_dir / "2021" / "2021_07" / "a.jpg").exists()
    assert (config.organized_dir / "2019" / "2019_12" / "b.jpg").exists()
    assert (config.organized_dir / "2020" / "2020_01" / "c.jpg").exists()

    db.close()


@requires_exiftool
def test_embedded_exif_persisted_in_db_without_rename(tmp_path, make_jpeg_with_exif):
    """step_validate_formats stores exif_datetime even when no extension rename occurs.

    The files already have the correct .jpg extension, so the rename branch never
    runs — this pins the fix that moved the exif_datetime UPDATE out from under
    ``if new_path:``.
    """
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger("test")

    _register_loose_images(
        config,
        db,
        make_jpeg_with_exif,
        {"only.jpg": "2018:03:04 05:06:07"},
    )

    step_validate_formats(config, db, "test", log)

    row = db.conn.execute(
        "SELECT original_path, exif_datetime FROM files WHERE zip_name = 'test.zip'"
    ).fetchone()

    # No rename happened (extension already correct) ...
    assert row["original_path"].endswith("only.jpg")
    # ... but the embedded date was still persisted.
    assert row["exif_datetime"] == "2018:03:04 05:06:07"

    db.close()
