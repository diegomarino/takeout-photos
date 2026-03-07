"""Pipeline cleanup utilities."""

from __future__ import annotations

import logging
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB


def remove_empty_directories(root_dir: Path, log: logging.Logger) -> int:
    """
    Recursively remove empty directories from root_dir.

    Args:
        root_dir: Root directory to scan
        log: Logger instance

    Returns:
        Count of directories removed

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.utils.cleanup import remove_empty_directories
        >>> import logging
        >>> log = logging.getLogger(__name__)
        >>> count = remove_empty_directories(Path("/path/to/extracted"), log)
        >>> print(f"Removed {count} empty directories")
    """
    if not root_dir.exists():
        return 0

    removed_count = 0

    # Bottom-up traversal: process deepest directories first
    for dirpath in sorted(root_dir.rglob("*"), key=lambda p: -len(p.parts)):
        if dirpath.is_dir():
            try:
                # Check if directory is empty (no files, no subdirs)
                if not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    removed_count += 1
                    log.debug(f"Removed empty directory: {dirpath}")
            except OSError as e:
                # Directory not empty or permission issue
                log.debug(f"Could not remove {dirpath}: {e}")

    return removed_count


def log_pipeline_summary(
    config: Config, db: PipelineDB, log: logging.Logger, cleanup_stats: dict[str, int]
) -> None:
    """
    Log final pipeline completion summary.

    Args:
        config: Pipeline configuration
        db: Database connection
        log: Logger instance
        cleanup_stats: Dict with 'extracted', 'duplicates', etc. cleanup counts

    Example:
        >>> cleanup_stats = {'extracted': 15, 'duplicates': 3}
        >>> log_pipeline_summary(config, db, log, cleanup_stats)
        # Logs completion summary to console and file
    """
    # Get statistics from database via SQL queries
    organized_count = db.conn.execute(
        "SELECT COUNT(*) FROM files WHERE status = 'organized'"
    ).fetchone()[0]

    # Count duplicates by checking files that have hash in organized_files
    # but were not actually organized (ended up in duplicates/ dir)
    duplicate_count = db.conn.execute("""
        SELECT COUNT(*) FROM files
        WHERE content_hash IN (SELECT hash FROM organized_files)
        AND status != 'organized'
    """).fetchone()[0]

    total_zips = db.conn.execute("SELECT COUNT(DISTINCT name) FROM zips").fetchone()[0]

    # Count errors from exif warnings file if it exists
    error_count = 0
    if config.exif_warnings_file and config.exif_warnings_file.exists():
        with open(config.exif_warnings_file) as f:
            error_count = sum(1 for line in f if line.startswith("Error:"))

    # Build summary message
    summary_lines = [
        "",
        "=" * 60,
        "PIPELINE COMPLETED",
        "=" * 60,
        f"ZIPs processed: {total_zips}",
        f"Files organized: {organized_count}",
        f"Duplicates found: {duplicate_count}",
        f"Errors encountered: {error_count}",
        "",
        "Cleanup:",
    ]

    total_cleaned = 0
    for dir_name, count in cleanup_stats.items():
        if count > 0:
            summary_lines.append(f"  {dir_name}: {count} empty directories removed")
            total_cleaned += count

    if total_cleaned == 0:
        summary_lines.append("  No empty directories found")

    summary_lines.extend(
        [
            "",
            f"Logs: {config.logs_dir}",
            f"Organized media: {config.organized_dir}",
            "=" * 60,
            "",
        ]
    )

    # Log to console
    for line in summary_lines:
        log.info(line)
