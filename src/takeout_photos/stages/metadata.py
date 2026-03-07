"""
Metadata application stage.

Phase 2a of the pipeline: Apply JSON metadata to EXIF tags using batch exiftool.
"""

from __future__ import annotations

import logging
import os
import tempfile

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.exif.operations import run_exiftool, ts_to_exif_date
from takeout_photos.utils.timer import Timer


def step_apply_metadata(config: Config, db: PipelineDB, zip_name: str, log: logging.Logger) -> None:
    """
    Apply metadata from JSON files to photo EXIF tags using exiftool batch mode.

    This is Phase 2a of the pipeline. For all pending files in this ZIP:
    1. Retrieve all pending files for this ZIP
    2. Generate exiftool arguments file for batch processing:
       - DateTimeOriginal and CreateDate from photoTakenTime (ALWAYS overwrites embedded EXIF)
       - GPSLatitude, GPSLongitude, and reference directions from geoData
    3. Execute exiftool once for all files (much faster than per-file)
    4. Mark files as 'meta_applied'

    Args:
        config: Pipeline configuration
        db: Database connection
        zip_name: Name of ZIP being processed
        log: Logger instance

    Side Effects:
        - Modifies EXIF data in extracted files (overwrites existing dates)
        - Updates file status in database

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.metadata import step_apply_metadata
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> step_apply_metadata(config, db, "takeout-001.zip", log)
        # Applies metadata to 1234 files

    Note:
        Uses exiftool's -@ flag to read commands from a file, enabling
        efficient batch processing instead of one exiftool process per file.

        Google Takeout is known to export files with incorrect embedded EXIF dates.
        This function ALWAYS prioritizes JSON photoTakenTime over any embedded EXIF
        when JSON metadata is available, following industry best practices.

        Files without JSON metadata are left unchanged, but still marked
        as meta_applied to advance the pipeline.

        See: https://github.com/laurentlbm/google-photos-takeout-date-fixer
    """
    files = db.get_files_for_zip(zip_name, status="pending")

    if not files:
        log.info(f"No pending metadata files in {zip_name}")
        return

    with Timer() as timer:
        # Prepare argument file for exiftool (more efficient than file-by-file)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as argfile:
            argfile_path = argfile.name

            for f in files:
                if not f["photo_taken_ts"] and not f["geo_lat"]:
                    continue

                path = f["original_path"]
                args = []

                # Timestamp - always prioritize JSON photoTakenTime over embedded EXIF
                # Google Takeout is known to export files with incorrect EXIF dates.
                # Industry standard: always use JSON photoTakenTime when available.
                # See: https://github.com/laurentlbm/google-photos-takeout-date-fixer
                if f["photo_taken_ts"]:
                    exif_date = ts_to_exif_date(f["photo_taken_ts"])
                    args.append(f"-DateTimeOriginal={exif_date}")
                    args.append(f"-CreateDate={exif_date}")

                # GPS coordinates - always apply if available from JSON
                if f["geo_lat"] and f["geo_lon"]:
                    lat, lon = f["geo_lat"], f["geo_lon"]
                    lat_ref = "N" if lat >= 0 else "S"
                    lon_ref = "E" if lon >= 0 else "W"
                    args.append(f"-GPSLatitude={abs(lat)}")
                    args.append(f"-GPSLatitudeRef={lat_ref}")
                    args.append(f"-GPSLongitude={abs(lon)}")
                    args.append(f"-GPSLongitudeRef={lon_ref}")

                if args:
                    for arg in args:
                        argfile.write(arg + "\n")
                    argfile.write(path + "\n")
                    argfile.write("-execute\n")

        # Execute exiftool in batch mode and ensure cleanup
        try:
            if not config.dry_run:
                result = run_exiftool(
                    [
                        "-@",
                        argfile_path,
                        "-overwrite_original",
                        "-P",  # Preserve file modification date
                        "-ignoreMinorErrors",
                    ],
                    exif_warnings_file=config.exif_warnings_file,
                    log=log,
                )

                # Only update if exiftool succeeded
                if result.returncode == 0:
                    for f in files:
                        # Populate exif_datetime for organize phase optimization
                        # (avoid subprocess calls by reading from database instead)
                        if f["photo_taken_ts"]:
                            exif_date = ts_to_exif_date(f["photo_taken_ts"])
                            db.update_file(f["id"], status="meta_applied", exif_datetime=exif_date)
                        else:
                            db.update_file(f["id"], status="meta_applied")
                    db.commit()
                    log.info(f"  Metadata applied: {len(files):,} files ({timer.format_elapsed()})")
                else:
                    # Leave files in 'pending' for automatic retry
                    log.error(f"  Exiftool failed for {zip_name} (returncode={result.returncode})")
                    log.error(f"    Return code: {result.returncode}")
                    log.error(f"    File count: {len(files)}")
                    log.error(f"    Argfile: {argfile_path}")
                    log.error(f"    Check warnings: {config.exif_warnings_file}")
                    log.error("  Files remain 'pending' for retry on next run")
            else:
                log.info(f"[DRY RUN] Would apply metadata to {len(files)} files")
        finally:
            # Ensure argfile is always cleaned up, even if there's an exception
            if os.path.exists(argfile_path):
                os.unlink(argfile_path)
