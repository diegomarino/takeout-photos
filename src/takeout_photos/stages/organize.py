"""
File organization stage with merge-extract mode.

All ZIPs extract to the same extracted/ directory (merge-extract).
This ensures JSONs are available even if split across different ZIPs.
Organization happens with inline deduplication after all files are processed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.exif.operations import run_exiftool
from takeout_photos.stages.dedupe import check_if_duplicate
from takeout_photos.utils.progress import progress_bar
from takeout_photos.utils.timer import Timer


def step_organize_files_from_zip(
    config: Config, db: PipelineDB, zip_name: str, log: logging.Logger
) -> dict[str, int]:
    """
    Organize files for a ZIP from extracted/ to organized/ or duplicates/.

    For each file:
    - Check if hash exists in organized_files (duplicate)
    - If duplicate: move to duplicates/ (preserving extracted/ relative path)
    - If unique: move to organized_dir/YYYY/MM/, insert into organized_files

    Args:
        config: Pipeline configuration
        db: Database connection
        zip_name: ZIP being processed (without .zip extension)
        log: Logger instance

    Returns:
        {
            'organized': count of files moved to organized/,
            'duplicates': count of files moved to duplicates/,
            'errors': count of files that failed,
            'skipped': count of files already organized
        }

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.organize import step_organize_files_from_zip
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> stats = step_organize_files_from_zip(config, db, "takeout-001", log)
        >>> print(f"Organized: {stats['organized']}, Duplicates: {stats['duplicates']}")

    Note:
        This replaces the global step_organize() batch operation.
        Deduplication happens inline during organization.
    """
    # Type narrowing
    assert config.organized_dir is not None
    assert config.duplicates_dir is not None
    assert config.extracted_dir is not None

    # Get all files with hashes for this ZIP
    files = db.get_files_with_hash_for_zip(zip_name)

    if not files:
        log.info(f"No files with hashes found for {zip_name}")
        return {"organized": 0, "duplicates": 0, "errors": 0, "skipped": 0}

    # Filter out files that are already organized or being staged (for retry support)
    files_to_process = [f for f in files if f.get("status") not in ("organized", "staged")]
    skipped_count = len(files) - len(files_to_process)

    if not files_to_process:
        log.info(f"All {len(files)} files already organized for {zip_name}")
        return {"organized": 0, "duplicates": 0, "errors": 0, "skipped": skipped_count}

    stats = {"organized": 0, "duplicates": 0, "errors": 0, "skipped": skipped_count}

    # Handle files stuck in 'staged' state (recovery case)
    staged_files = [f for f in files if f.get("status") == "staged"]
    if staged_files:
        log.info(f"  Recovering {len(staged_files)} staged files from previous run...")
        for f in staged_files:
            staged_path = f.get("staged_path")
            if staged_path:
                full_path = config.organized_dir / staged_path
                if full_path.exists():
                    # File was moved successfully, just update DB
                    db.insert_organized_file(
                        hash=f["content_hash"],
                        original_name=Path(f["original_path"]).name,
                        final_path=staged_path,
                        source_zip=f"{zip_name}.zip",
                        file_size=f["file_size"],
                    )
                    db.update_file(f["id"], status="organized", final_path=staged_path)
                    log.debug(f"Recovered staged: {staged_path}")
                else:
                    # File wasn't moved, revert to pending
                    db.update_file(f["id"], status="pending", staged_path=None)
                    log.warning(f"Reverted staged file to pending: {f['original_path']}")
        db.commit()

    with Timer() as timer:
        # Batch size for database commits (configurable via checkpoint_interval)
        batch_size = config.checkpoint_interval

        # Track created directories to avoid redundant mkdir calls
        created_dirs = set()

        # Process files in batches to reduce commit overhead
        for i in range(0, len(files_to_process), batch_size):
            batch = files_to_process[i : i + batch_size]

            for file in progress_bar(batch, desc=f"Organizing {zip_name}"):
                try:
                    source_path = Path(file["original_path"])

                    if not source_path.exists():
                        log.warning(f"File not found: {source_path}")
                        stats["errors"] += 1
                        continue

                    # Get file size before moving
                    file_size = source_path.stat().st_size

                    # Check if duplicate
                    if check_if_duplicate(file["content_hash"], db):
                        # Move to duplicates/
                        dest = _move_to_duplicates(source_path, zip_name, config)
                        # Mark file as organized (duplicates are considered "processed")
                        db.update_file_status(file["original_path"], "organized")
                        log.debug(f"Duplicate: {source_path.name} → {dest}")
                        stats["duplicates"] += 1
                    else:
                        # DB-before-move pattern with staged intermediate state
                        # This ensures crash-safety and enables recovery

                        # 1. Calculate destination path (no filesystem changes yet)
                        # Use exif_datetime from database (already loaded) instead of subprocess
                        exif_datetime = file.get("exif_datetime")
                        dest_dir, dest_filename = _compute_organized_dest(
                            source_path, config, exif_datetime
                        )
                        # Compute path relative to organized_dir to preserve year/month structure
                        relative_path = dest_dir.relative_to(config.organized_dir) / dest_filename
                        dest = dest_dir / dest_filename

                        # 2. Update DB to 'staged' state FIRST (crash-safe checkpoint)
                        db.update_file(file["id"], status="staged", staged_path=str(relative_path))
                        # Don't commit yet - will commit batch at end

                        # 3. Create directory if needed
                        if dest_dir not in created_dirs:
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            created_dirs.add(dest_dir)

                        # 4. Move file (if this fails, DB shows 'staged' but file not moved)
                        if not config.dry_run:
                            source_path.rename(dest)

                        # 5. Insert into organized_files and mark 'organized'
                        db.insert_organized_file(
                            hash=file["content_hash"],
                            original_name=source_path.name,
                            final_path=str(relative_path),
                            source_zip=f"{zip_name}.zip",
                            file_size=file_size,
                        )
                        db.update_file(
                            file["id"], status="organized", final_path=str(relative_path)
                        )

                        log.debug(f"Organized: {source_path.name} → {dest}")
                        stats["organized"] += 1

                except Exception as e:
                    log.error(f"Failed to organize {file['original_path']}: {e}")
                    stats["errors"] += 1

            # Commit once per batch (performance optimization)
            db.commit()

    log.info(
        f"  Files organized: {stats['organized']:,} moved, "
        f"{stats['duplicates']:,} duplicates ({timer.format_elapsed()})"
    )

    return stats


def _move_to_duplicates(source_path: Path, zip_name: str, config: Config) -> Path:
    """
    Move file to duplicates/ preserving directory structure (merge-extract).

    Example:
        source: extracted/Google Photos/2020/IMG_1234.jpg
        dest:   duplicates/Google Photos/2020/IMG_1234.jpg

    Args:
        source_path: Path to source file
        zip_name: ZIP name (without .zip extension) - kept for API compatibility but unused
        config: Pipeline configuration

    Returns:
        Path to destination file

    Note:
        All ZIPs extract to the same extracted/ directory (merge-extract).
        Duplicates preserve the relative structure from extracted/ root.
    """
    # Type narrowing
    assert config.extracted_dir is not None
    assert config.duplicates_dir is not None

    # Get path relative to extracted/ root (merge-extract)
    relative_path = source_path.relative_to(config.extracted_dir)

    # Destination in duplicates/ (simplified, no per-ZIP subdirectories)
    dest = config.duplicates_dir / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not config.dry_run:
        source_path.rename(dest)

    return dest


def _compute_organized_dest(
    source_path: Path, config: Config, exif_datetime: str | None
) -> tuple[Path, str]:
    """
    Compute organized destination WITHOUT moving file.

    Determines where a file should go based on EXIF date and handles
    filename conflicts, but does not perform the actual move.

    Args:
        source_path: Path to source file
        config: Pipeline configuration
        exif_datetime: EXIF datetime from database (YYYY:MM:DD HH:MM:SS) or None

    Returns:
        Tuple of (dest_dir, filename) where file should go

    Example:
        >>> dest_dir, filename = _compute_organized_dest(
        ...     Path("photo.jpg"), config, "2020:05:15 14:30:22"
        ... )
        >>> print(dest_dir)
        /work/organized/2020/05
        >>> print(filename)
        2020-05-15_photo.jpg  # If dated_filenames=True

    Note:
        Files without EXIF dates go to organized_dir/no_date/
        Filename collisions are resolved by appending (1), (2), etc.
        Date prefix applied when config.dated_filenames is True.
        Uses database value instead of subprocess for performance.
    """
    # Type narrowing
    assert config.organized_dir is not None

    # Use EXIF date from database (already loaded, no subprocess needed)
    date_str = exif_datetime

    if date_str:
        # Parse YYYY:MM:DD to path
        year, month = date_str[:4], date_str[5:7]
        dest_dir = config.organized_dir / year / month
    else:
        # No date - use no_date/
        dest_dir = config.organized_dir / "no_date"

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Determine final filename with conflict resolution
    # NEW: Compute filename with optional date prefix
    base_filename = _build_filename(source_path.name, date_str, config)
    filename = base_filename

    counter = 1
    while (dest_dir / filename).exists():
        stem = Path(base_filename).stem
        suffix = Path(base_filename).suffix
        filename = f"{stem}({counter}){suffix}"
        counter += 1

    return dest_dir, filename


def _move_to_organized(
    source_path: Path, config: Config, db: PipelineDB, exif_datetime: str | None
) -> Path:
    """
    Move file to organized_dir/YYYY/MM/ based on EXIF date.

    Preserves original filename.

    Args:
        source_path: Path to source file
        config: Pipeline configuration
        db: Database connection (unused, kept for consistency)
        exif_datetime: EXIF datetime from database (YYYY:MM:DD HH:MM:SS) or None

    Returns:
        Path to destination file

    Note:
        Files without EXIF dates go to organized_dir/no_date/
        Filename conflicts are resolved by appending (1), (2), etc.
    """
    # Type narrowing
    assert config.organized_dir is not None

    # Compute destination using helper
    dest_dir, filename = _compute_organized_dest(source_path, config, exif_datetime)
    dest = dest_dir / filename

    if not config.dry_run:
        source_path.rename(dest)

    return dest


def _read_exif_date(
    file_path: Path,
    exif_warnings_file: Path | None = None,
    log: logging.Logger | None = None,
) -> str | None:
    """
    Read DateTimeOriginal from EXIF using exiftool.

    Args:
        file_path: Path to media file
        exif_warnings_file: Optional path to append stderr warnings
        log: Optional logger to log critical errors to console

    Returns:
        Date string in YYYY:MM:DD HH:MM:SS format, or None if no date

    Example:
        >>> _read_exif_date(Path("/path/to/IMG_1234.jpg"))
        '2020:05:15 14:30:22'
    """
    try:
        result = run_exiftool(
            ["-DateTimeOriginal", "-s3", str(file_path)],
            exif_warnings_file=exif_warnings_file,
            log=log,
        )
        date_str = result.stdout.strip()
        return date_str if date_str else None
    except Exception:
        return None


def _build_filename(original_name: str, date_str: str | None, config: Config) -> str:
    """
    Build filename with optional date prefix.

    Args:
        original_name: Original filename (e.g., "IMG_1234.jpg")
        date_str: EXIF date string "YYYY:MM:DD HH:MM:SS" or None
        config: Pipeline configuration

    Returns:
        Filename with prefix if config.dated_filenames is True

    Examples:
        >>> _build_filename("photo.jpg", "2023:05:15 14:30:22", config_with_dates)
        '2023-05-15_photo.jpg'

        >>> _build_filename("photo.jpg", None, config_with_dates)
        'NO-DATE_photo.jpg'

        >>> _build_filename("photo.jpg", "2023:05:15 14:30:22", config_without_dates)
        'photo.jpg'
    """
    if not config.dated_filenames:
        # Feature disabled - return original name
        return original_name

    if date_str:
        # Extract YYYY-MM-DD from "YYYY:MM:DD HH:MM:SS"
        date_prefix = date_str[:10].replace(":", "-")  # "2023-05-15"
    else:
        # No date available
        date_prefix = "NO-DATE"

    return f"{date_prefix}_{original_name}"
