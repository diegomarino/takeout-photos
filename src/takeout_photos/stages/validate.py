"""
File format validation stage.

Phase 1b of the pipeline: Validate file formats and correct extensions if needed.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.exif.operations import get_file_type_and_exif
from takeout_photos.utils.progress import progress_bar
from takeout_photos.utils.timer import Timer


def _validate_worker(file_record: dict) -> tuple:
    """
    Worker function for parallel file validation.

    Args:
        file_record: Dictionary with 'id', 'original_path' keys

    Returns:
        Tuple of (file_id, new_path, exif_datetime, error_message or None)

    Note:
        This function is designed to be used with ProcessPoolExecutor
        for I/O-bound parallel validation operations (exiftool calls).
        Does NOT rename files - returns the target path for main thread to handle.
    """
    try:
        original_path = Path(file_record["original_path"])

        if not original_path.exists():
            return (file_record["id"], None, None, f"File not found: {original_path}")

        # Detect real file type and read existing EXIF in one call
        real_type, existing_exif = get_file_type_and_exif(original_path)
        if not real_type:
            # Not an error - just no type detection possible
            return (file_record["id"], None, None, None)

        # Determine if correction is needed (but don't rename yet)
        # We'll return the target path for the main thread to handle renaming
        current_ext = original_path.suffix.lower().lstrip(".")
        real_type_lower = real_type.lower()

        # Handle jpeg/jpg equivalence
        if (current_ext == real_type_lower) or (
            current_ext in ["jpg", "jpeg"] and real_type_lower in ["jpg", "jpeg"]
        ):
            # No correction needed - extension matches
            return (file_record["id"], None, None, None)
        else:
            # Extension needs correction - return target path
            new_path = original_path.parent / f"{original_path.name}.{real_type_lower}"
            exif_datetime = existing_exif.get("DateTimeOriginal")
            return (file_record["id"], str(new_path), exif_datetime, None)

    except Exception as e:
        return (file_record["id"], None, None, str(e))


def step_validate_formats(
    config: Config, db: PipelineDB, zip_name: str, log: logging.Logger
) -> None:
    """
    Validate file formats and correct extensions if needed, preserving EXIF metadata.

    This is Phase 1b (inserted between extraction and metadata application).

    Google Takeout exports often have incorrect file extensions:
    - .HEIC files that are actually JPEG
    - .PNG files that are actually JPEG

    This step:
    1. Detects the real file type using exiftool
    2. Reads existing EXIF metadata
    3. Corrects file extension if needed (appending correct extension)
    4. Updates database with corrected paths
    5. Stores existing EXIF datetime if present

    Args:
        config: Pipeline configuration
        db: Database connection
        zip_name: Name of ZIP being processed
        log: Logger instance

    Side Effects:
        - May rename files to correct extensions
        - Updates original_path in database if files are renamed
        - Stores exif_datetime in database when an extension is corrected

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.validate import step_validate_formats
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> step_validate_formats(config, db, "takeout-001.zip", log)
        # Corrects 15 mismatched extensions

    Note:
        Uses optimized get_file_type_and_exif() to detect format and read
        EXIF in a single exiftool call, reducing overhead by 50%.

        Extensions are corrected by appending (not replacing) to avoid
        filename collisions: IMG_6486.HEIC → IMG_6486.HEIC.jpg
    """
    files = db.get_files_for_zip(zip_name, status="pending")

    if not files:
        log.info(f"No files to validate in {zip_name}")
        return

    # Dry-run mode: log what would be done but don't validate
    if config.dry_run:
        log.info(f"[DRY RUN] Would validate {len(files)} files")
        return

    with Timer() as timer:
        corrected_count = 0
        errors = []

        # Use parallel processing for validation (I/O-bound task - exiftool calls)
        with ProcessPoolExecutor(max_workers=config.workers) as executor:
            # Submit all validation jobs
            futures = {executor.submit(_validate_worker, f): f for f in files}

            # Process results as they complete
            for future in progress_bar(
                as_completed(futures), total=len(futures), desc="Validating formats"
            ):
                file_id, new_path, exif_datetime, error = future.result()

                if error:
                    file_record = futures[future]
                    log.warning(f"Error validating {file_record['original_path']}: {error}")
                    errors.append((file_id, error))
                    continue

                # If validation determined extension correction is needed
                if new_path:
                    original_path = Path(futures[future]["original_path"])
                    target_path = Path(new_path)

                    # Rename file (main thread handles file operations to avoid race conditions)
                    try:
                        original_path.rename(target_path)

                        # Update database with corrected path
                        db.conn.execute(
                            "UPDATE files SET original_path = ? WHERE id = ?",
                            (new_path, file_id),
                        )
                        corrected_count += 1

                        # Store EXIF datetime if present
                        if exif_datetime:
                            db.conn.execute(
                                "UPDATE files SET exif_datetime = ? WHERE id = ?",
                                (exif_datetime, file_id),
                            )
                    except Exception as e:
                        log.warning(f"Failed to rename {original_path} to {target_path}: {e}")
                        errors.append((file_id, str(e)))

        # Commit database changes only if there were corrections
        if corrected_count > 0:
            db.commit()

        if errors:
            log.warning(f"Encountered {len(errors)} errors during validation")

    log.info(f"  Formats validated: {corrected_count:,} corrections ({timer.format_elapsed()})")
