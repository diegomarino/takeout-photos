"""
ZIP extraction stage.

Phase 1 of the pipeline: Extract ZIP files and register media files with metadata.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.takeout.json_parser import parse_takeout_json
from takeout_photos.utils.progress import is_media_file, progress_bar
from takeout_photos.utils.system_files import should_ignore_path
from takeout_photos.utils.timer import Timer


def _compute_file_hash(filepath: Path) -> str:
    """
    Compute SHA256 hash of a file for collision detection.

    Args:
        filepath: Path to the file

    Returns:
        Hex digest of the file's SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _is_safe_path(member_name: str, extract_dir: Path) -> bool:
    """
    Validate that a ZIP member path is safe to extract.

    Prevents path traversal attacks (Zip Slip) by ensuring the resolved
    path stays within the extraction directory.

    Args:
        member_name: ZIP member name/path
        extract_dir: Target extraction directory

    Returns:
        True if the path is safe to extract, False otherwise

    Example:
        >>> _is_safe_path("photos/img.jpg", Path("/work/extracted"))
        True
        >>> _is_safe_path("../../../etc/passwd", Path("/work/extracted"))
        False
        >>> _is_safe_path("/etc/passwd", Path("/work/extracted"))
        False
    """
    # Resolve the target path
    target_path = (extract_dir / member_name).resolve()

    # Ensure the resolved path is within extract_dir
    try:
        target_path.relative_to(extract_dir.resolve())
        return True
    except ValueError:
        # Path is outside extract_dir
        return False


def _format_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "4.2 GB", "512 MB")
    """
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def delete_zip_after_extraction(
    zip_path: Path, zip_name: str, db: PipelineDB, log: logging.Logger, dry_run: bool = False
) -> None:
    """
    Delete a ZIP file after successful extraction and record it in the database.

    Args:
        zip_path: Path to the ZIP file
        zip_name: ZIP filename
        db: Database connection
        log: Logger instance
        dry_run: If True, only log what would be deleted

    Side effects:
        Deletes ZIP file from filesystem and updates database with deletion timestamp.
    """
    try:
        # Get file size before deletion (for logging)
        zip_size = zip_path.stat().st_size

        if dry_run:
            log.info(f"[DRY RUN] Would delete: {zip_name} ({_format_size(zip_size)})")
            return

        # Delete the file
        zip_path.unlink()

        # Mark as deleted in database
        db.mark_zip_deleted(zip_name)

        # Log the deletion
        log.info(f"Deleted ZIP: {zip_name} ({_format_size(zip_size)})")

    except FileNotFoundError:
        # ZIP already deleted (edge case: manual deletion)
        log.warning(f"ZIP already deleted: {zip_name}")
        if not dry_run:
            db.mark_zip_deleted(zip_name)

    except Exception as e:
        # Deletion failed but extraction succeeded
        # Log error but don't fail the pipeline
        log.error(f"Failed to delete ZIP {zip_name}: {e}")


def step_extract_zip(config: Config, db: PipelineDB, zip_path: Path, log: logging.Logger) -> None:
    """
    Extract a ZIP file and register media files in the database.

    This is Phase 1 of the pipeline. For each ZIP:
    1. Extract all contents to extracted/ (merged)
    2. Scan for media files by extension
    3. For each media file, search for associated JSON metadata
    4. Parse JSON to extract initial metadata
    5. Register file in database with metadata
    6. Update ZIP status to 'extracted'

    Args:
        config: Pipeline configuration
        db: Database connection
        zip_path: Path to ZIP file to extract
        log: Logger instance

    Raises:
        Exception: If extraction fails, ZIP is marked with 'error' status

    Side Effects:
        - Creates extracted/ directory (merge-extract)
        - Populates files table in database
        - Updates zips table status

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.extract import step_extract_zip
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> zip_file = config.zips_dir / "takeout-001.zip"
        >>> step_extract_zip(config, db, zip_file, log)
        # Extracts ZIP and registers 1234 media files

    Note:
        Uses database-based JSON lookup which is much faster than filesystem
        search for large collections. JSON files are registered first to enable
        fast lookups during media file registration.
    """
    zip_name = zip_path.name

    # Dry-run mode: log what would be done but don't modify filesystem or database
    if config.dry_run:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                media_count = sum(1 for m in members if is_media_file(Path(m)))
                json_count = sum(1 for m in members if m.lower().endswith(".json"))
            log.info(
                f"[DRY RUN] Would extract {zip_name}: "
                f"{len(members)} files ({json_count} JSON, {media_count} media)"
            )
            return
        except Exception as e:
            log.error(f"[DRY RUN] Failed to inspect {zip_name}: {e}")
            return

    log.info(f"  Extracting: {zip_name}")

    db.update_zip_status(zip_name, "extracting")

    # Extract all ZIPs to same directory (merge-extract)
    # This allows JSONs and media files from different ZIPs to be matched
    assert config.extracted_dir is not None
    extract_dir = config.extracted_dir
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()

            for member in progress_bar(members, desc=f"Extracting {zip_name}"):
                # Validate path to prevent Zip Slip attacks
                if not _is_safe_path(member, extract_dir):
                    log.error(
                        f"Security: Rejecting unsafe path '{member}' from {zip_name} "
                        f"(potential path traversal attack)"
                    )
                    continue

                target = extract_dir / member

                # Skip directories
                if member.endswith("/"):
                    if not target.exists():
                        target.mkdir(parents=True, exist_ok=True)
                    continue

                if not target.exists():
                    # No collision - extract normally
                    zf.extract(member, extract_dir)
                else:
                    # Path collision - compare checksums
                    # Extract to temp location first
                    import tempfile

                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmpdir_path = Path(tmpdir)
                        zf.extract(member, tmpdir_path)
                        temp_file = tmpdir_path / member

                        # Compare checksums
                        existing_hash = _compute_file_hash(target)
                        new_hash = _compute_file_hash(temp_file)

                        if existing_hash == new_hash:
                            # Same content - skip extraction
                            log.info(
                                f"Skipping {member} from {zip_name} "
                                f"(identical content already exists)"
                            )
                        else:
                            # Different content - rename and keep both
                            stem = target.stem
                            suffix = target.suffix
                            conflict_num = 1
                            while True:
                                conflict_name = f"{stem}_conflict_{conflict_num}{suffix}"
                                conflict_path = target.parent / conflict_name
                                if not conflict_path.exists():
                                    break
                                conflict_num += 1

                            # Move temp file to conflict path
                            import shutil

                            shutil.move(str(temp_file), str(conflict_path))
                            log.warning(
                                f"Path collision for {member}: existing file differs from {zip_name}. "
                                f"Saved new file as: {conflict_path.name}"
                            )

        # Register JSON files from THIS ZIP only (merge-extract)
        # Only register JSONs that were in this ZIP's member list
        with Timer() as json_timer:
            json_count = 0
            for member in members:
                if member.endswith(".json"):
                    json_path = extract_dir / member
                    if json_path.is_file():
                        db.register_json_file(zip_name=zip_name, full_path=str(json_path))
                        json_count += 1

            if json_count > 0:
                db.commit()

        log.info(f"  JSON files registered: {json_count:,} ({json_timer.format_elapsed()})")

        # Register media files from THIS ZIP only (merge-extract)
        with Timer() as extract_timer:
            file_count = 0
            for member in members:
                path = extract_dir / member
                if path.is_file() and is_media_file(path):
                    # Filter system files
                    if should_ignore_path(path):
                        continue

                    # Use database to find JSON (MUCH faster than filesystem search)
                    # Pass full path to correctly match JSONs in same directory
                    json_path_str = db.find_json_for_media_db(str(path))
                    media_json_path: Path | None = Path(json_path_str) if json_path_str else None
                    json_meta = parse_takeout_json(media_json_path) if media_json_path else {}

                    db.register_file(
                        zip_name=zip_name,
                        original_path=str(path),
                        file_size=path.stat().st_size,
                        has_json=1 if media_json_path else 0,
                        json_path=str(media_json_path) if media_json_path else None,
                        **json_meta,
                    )
                    file_count += 1

            db.commit()
            db.update_zip_status(
                zip_name,
                "extracted",
                file_count=file_count,
                extracted_at=datetime.now().isoformat(),
            )

        log.info(
            f"  {zip_name} extracted: {json_count:,} JSON, "
            f"{file_count:,} media files ({extract_timer.format_elapsed()})"
        )

        # Delete ZIP if flag is enabled
        if config.delete_zips_after_extract:
            delete_zip_after_extraction(zip_path, zip_name, db, log, config.dry_run)

    except Exception as e:
        db.update_zip_status(zip_name, "error", error_msg=str(e))
        log.error(f"Error extracting {zip_name}: {e}")
        raise
