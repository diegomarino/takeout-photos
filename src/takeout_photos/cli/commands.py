"""
CLI command implementations.

Functions for process, status, and reset commands.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline
from takeout_photos.utils.system_files import should_ignore_path


def cmd_process(config: Config) -> None:
    """
    Main command: process all ZIPs through the complete pipeline.

    Executes the full pipeline:
    1. Extract all pending ZIPs (merge-extract)
    2. Validate and correct file formats
    3. Apply metadata
    4. Compute content hashes
    5. Organize by date with inline deduplication
    6. Quality control report

    Args:
        config: Pipeline configuration

    Side Effects:
        - Creates all work directories
        - Processes all ZIPs in zips/
        - Generates final organized photo library
        - Creates QC report

    Note:
        This command is idempotent and resumable. If interrupted,
        it will resume from the last completed checkpoint when rerun.

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.cli.commands import cmd_process
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> cmd_process(config)
        # Processes complete pipeline
    """
    with Pipeline(config) as pipeline:
        pipeline.run()


def cmd_status(config: Config) -> None:
    """
    Display current pipeline state and statistics.

    Shows:
    - Processing state of each ZIP
    - File counts by processing status
    - Number of duplicates found
    - Disk space usage by directory
    - Last successful run timestamp

    Args:
        config: Pipeline configuration

    Side Effects:
        - Prints status information to console

    Note:
        This is a read-only operation, safe to run at any time.

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.cli.commands import cmd_status
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> cmd_status(config)
        # Displays pipeline status
    """
    assert config.db_path is not None
    if not config.db_path.exists():
        print("No pipeline started yet. Run 'process' first.")
        return

    db = PipelineDB(config.db_path)

    print(f"\n{'='*60}")
    print(f"PIPELINE STATUS: {config.workdir}")
    print(f"{'='*60}\n")

    # ZIP status
    zips = db.conn.execute("""SELECT name, status, file_count, extracted_at, deleted_at, error_msg
           FROM zips ORDER BY name""").fetchall()

    print("ZIPs:")
    print(f"  {'Name':<40} {'Status':<15} {'Files':<10}")
    print(f"  {'-'*40} {'-'*15} {'-'*10}")
    for z in zips:
        fc = z["file_count"] or "-"
        status_line = f"  {z['name']:<40} {z['status']:<15} {fc:<10}"
        if z["deleted_at"]:
            status_line += " [DELETED]"
        print(status_line)
        if z["error_msg"]:
            print(f"    ERROR: {z['error_msg']}")

    # File summary
    stats = db.conn.execute("""
        SELECT status, COUNT(*) as cnt
        FROM files
        GROUP BY status
    """).fetchall()

    if stats:
        print("\nFiles by status:")
        for s in stats:
            print(f"  {s['status']}: {s['cnt']}")

    # Duplicates (count files in duplicates/ directory)
    if config.duplicates_dir and config.duplicates_dir.exists():
        dupe_count = sum(
            1 for _ in config.duplicates_dir.rglob("*") if _.is_file() and not should_ignore_path(_)
        )
    else:
        dupe_count = 0
    print(f"\nDuplicates found: {dupe_count}")

    # Last run
    last_run = db.get_state("last_complete_run")
    if last_run:
        print(f"\nLast complete run: {last_run}")

    # Disk space
    print("\nDisk space:")
    assert config.extracted_dir is not None
    assert config.organized_dir is not None
    assert config.duplicates_dir is not None
    for name, path in [
        ("extracted", config.extracted_dir),
        ("organized", config.organized_dir),
        ("duplicates", config.duplicates_dir),
    ]:
        if path.exists():
            size = sum(
                f.stat().st_size
                for f in path.rglob("*")
                if f.is_file() and not should_ignore_path(f)
            )
            print(f"  {name}: {size / (1024**3):.2f} GB")

    db.close()


def cmd_reset(config: Config, zip_name: str | None = None) -> None:
    """
    Reset pipeline state for a specific ZIP or entire pipeline.

    For a specific ZIP:
    - Reset status to 'pending'
    - Remove all file records
    - Delete extracted directory
    - Clear duplicate records

    For full reset:
    - Clear entire database
    - Delete all work directories (extracted, duplicates)
    - Organized photos directory is never deleted

    Args:
        config: Pipeline configuration
        zip_name: Optional ZIP name to reset (if None, resets everything)

    Side Effects:
        - Modifies/clears database tables
        - Deletes work directories

    Warning:
        Full reset requires confirmation as it's destructive.
        Final organized_media/ directory is never deleted.

    Example (reset specific ZIP):
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.cli.commands import cmd_reset
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> cmd_reset(config, zip_name="takeout-001.zip")
        # Resets one ZIP

    Example (reset all):
        >>> config = Config(workdir="/path/to/work")
        >>> cmd_reset(config)
        # Prompts for confirmation, then resets everything
    """
    assert config.db_path is not None
    assert config.extracted_dir is not None
    assert config.duplicates_dir is not None

    if not config.db_path.exists():
        print("No pipeline to reset.")
        return

    db = PipelineDB(config.db_path)

    if zip_name:
        # Reset specific ZIP
        print(f"Resetting ZIP: {zip_name}")
        db.conn.execute(
            "UPDATE zips SET status = 'pending', error_msg = NULL WHERE name = ?",
            (zip_name,),
        )
        db.conn.execute("DELETE FROM files WHERE zip_name = ?", (zip_name,))
        db.conn.execute("DELETE FROM json_files WHERE zip_name = ?", (zip_name,))

        # Delete extracted directory
        extract_dir = config.extracted_dir / Path(zip_name).stem
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
            print(f"  Deleted: {extract_dir}")

    else:
        # Reset entire pipeline
        confirm = input("Reset ENTIRE pipeline? (type 'YES' to confirm): ")
        if confirm != "YES":
            print("Cancelled.")
            db.close()
            return

        print("Resetting entire pipeline...")
        db.conn.execute("DELETE FROM zips")
        db.conn.execute("DELETE FROM files")
        db.conn.execute("DELETE FROM json_files")
        db.conn.execute("DELETE FROM pipeline_state")

        # Delete work directories (but NOT organized_dir)
        for d in [config.extracted_dir, config.duplicates_dir]:
            if d.exists():
                shutil.rmtree(d)
                print(f"  Deleted: {d}")

    db.commit()
    db.close()
    print("Reset complete.")


def cmd_recovery(config: Config, dry_run: bool = False) -> None:
    """
    Run recovery check to detect and fix pipeline inconsistencies.

    Detects and fixes:
    - Intermediate ZIPs (stuck in extracting/processing)
    - Orphaned files in organized/ (not in database)
    - Orphaned files in extracted/ (not in database)
    - Missing files (database references non-existent paths)

    Args:
        config: Pipeline configuration
        dry_run: If True, only detect issues without fixing (diagnostic mode)

    Side Effects:
        - Updates database to fix inconsistencies (unless dry_run=True)
        - Logs recovery actions to recovery_log table
        - Prints summary of issues detected/fixed

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.cli.commands import cmd_recovery
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> cmd_recovery(config, dry_run=True)  # Diagnostic mode
        >>> cmd_recovery(config)  # Fix mode
    """

    from takeout_photos.core.recovery import RecoveryManager
    from takeout_photos.utils.logging_setup import setup_logging

    # Setup logging
    log, _timestamp = setup_logging(config)

    # Open database (type narrowing: db_path is never None after __post_init__)
    assert config.db_path is not None
    db = PipelineDB(config.db_path)

    # Run recovery
    mode = " (dry-run mode)" if dry_run else ""
    print(f"\n{'='*60}")
    print(f"RECOVERY CHECK{mode}")
    print(f"{'='*60}\n")

    recovery_mgr = RecoveryManager(config, db, log, dry_run=dry_run)
    stats = recovery_mgr.check_and_recover()

    # Print summary
    print(f"\n{'='*60}")
    if stats.total == 0:
        print("✓ No issues found")
        print("Pipeline state is consistent")
    else:
        action = "detected" if dry_run else "fixed"
        print(f"✓ {stats.total} issue(s) {action}:")
        if stats.intermediate_zips > 0:
            print(f"  - {stats.intermediate_zips} intermediate ZIP(s)")
        if stats.orphaned_organized > 0:
            print(f"  - {stats.orphaned_organized} orphaned file(s) in organized/")
        if stats.orphaned_extracted > 0:
            print(f"  - {stats.orphaned_extracted} orphaned file(s) in extracted/")
        if stats.missing_files > 0:
            print(f"  - {stats.missing_files} missing file(s)")

        if dry_run:
            print("\nRun 'recovery' without --dry-run to fix these issues")

    print(f"{'='*60}\n")

    db.close()
