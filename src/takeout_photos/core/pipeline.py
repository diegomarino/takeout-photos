"""
Pipeline orchestrator.

Main entry point for running the Google Takeout photo processing pipeline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.extract import step_extract_zip
from takeout_photos.stages.hash import step_compute_hashes
from takeout_photos.stages.metadata import step_apply_metadata
from takeout_photos.stages.qc import step_qc
from takeout_photos.stages.validate import step_validate_formats
from takeout_photos.utils.dependencies import check_dependencies
from takeout_photos.utils.logging_setup import setup_logging
from takeout_photos.utils.timer import Timer


class Pipeline:
    """
    Main pipeline orchestrator for processing Google Takeout ZIPs.

    The Pipeline class coordinates all 6 core processing stages, provides
    resumability, and maintains state in an SQLite database. It can
    run the complete pipeline or individual phases.

    Attributes:
        config (Config): Pipeline configuration
        db (PipelineDB): Database connection for state management
        log (logging.Logger): Logger instance for pipeline operations

    Example (Complete Pipeline):
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.pipeline import Pipeline
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> pipeline = Pipeline(config)
        >>> pipeline.run()
        # Processes all ZIPs through all pipeline stages

    Example (Individual Phases):
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.pipeline import Pipeline
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> pipeline = Pipeline(config)
        >>>
        >>> # Run phases individually
        >>> pipeline.extract_all_zips()
        >>> pipeline.validate_formats()
        >>> pipeline.apply_metadata_phase()
        >>> pipeline.quality_control()

        # Note: Organization runs as part of the batch processing in run().

    Note:
        The pipeline is idempotent and resumable. If interrupted,
        rerun to continue from the last checkpoint. Each ZIP's state
        is saved in the database, allowing partial completion.

    Architecture (merge-extract):
        - Stateless design: All state in database
        - Two-phase processing: Extract all first, then batch process
        - Merge-extract: All ZIPs extract to same directory
        - ZIP-level tracking: Resume after interruption
        - Inline deduplication: Check duplicates during organization

    Pipeline Flow:
        Phase 1: Merge-Extract
            - Extract all ZIPs to extracted/ (merged, no per-ZIP subdirs)
            - Optionally delete ZIPs after extraction (progressive disk space reclaim)

        Phase 2: Batch Processing
            - Validate file formats and correct extensions
            - Apply JSON metadata to EXIF tags (JSONs all available!)
            - Compute content hashes for deduplication
            - Organize by EXIF date → organized_dir/YYYY/YYYY_MM/
            - Inline deduplication → duplicates/
            - Cleanup extracted/ at end (unless --keep-extracted-files)

        Phase 3: Quality control report → logs/qc_*.txt
    """

    def __init__(self, config: Config, verbose: bool | None = None):
        """
        Initialize pipeline with configuration.

        Args:
            config (Config): Pipeline configuration with directories and options
            verbose (bool | None): Override config.verbose for logging level.
                                    If None, uses config.verbose.

        Side Effects:
            - Creates database if it doesn't exist
            - Sets up logging to console and log file
            - Creates work directories if they don't exist
        """
        self.config = config

        # Override verbose if specified
        if verbose is not None:
            self.config.verbose = verbose

        # Type narrowing: Config.__post_init__ ensures these are not None
        assert self.config.db_path is not None
        assert self.config.zips_dir is not None
        assert self.config.extracted_dir is not None
        assert self.config.duplicates_dir is not None
        assert self.config.final_dir is not None
        assert self.config.logs_dir is not None

        # Set up logging
        self.log, run_timestamp = setup_logging(self.config)

        # Initialize exif_warnings_file with run timestamp
        self.config.exif_warnings_file = self.config.logs_dir / f"{run_timestamp}_exif_warnings.txt"

        # Check dependencies (after logging is configured)
        if not self.config.skip_deps_check:
            if not check_dependencies(verbose=self.config.verbose, log=self.log):
                self.log.error("Dependency check failed. Please install missing dependencies.")
                self.log.error("(Use --skip-deps-check to bypass this check at your own risk)")
                raise RuntimeError("Required dependencies not satisfied")

        # Initialize database
        self.db = PipelineDB(self.config.db_path)

        # Create necessary directories
        self._create_directories()

        # Acquire exclusive lock to prevent concurrent execution
        self._acquire_lock()

        # Run automatic recovery check
        self._run_recovery_check()

        self.log.debug(f"Pipeline initialized: workdir={self.config.workdir}")

    def _create_directories(self) -> None:
        """Create all required work directories."""
        # Type narrowing (already asserted in __init__ but needed for mypy flow analysis)
        assert self.config.zips_dir is not None
        assert self.config.extracted_dir is not None
        assert self.config.duplicates_dir is not None
        assert self.config.final_dir is not None
        assert self.config.logs_dir is not None

        for directory in [
            self.config.zips_dir,
            self.config.extracted_dir,
            self.config.duplicates_dir,
            self.config.final_dir,
            self.config.logs_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def _acquire_lock(self) -> None:
        """
        Acquire exclusive lock to prevent concurrent executions.

        Creates a lock file with the current process ID. If lock file exists,
        checks if the process is still running. If not, takes over the lock.

        Raises:
            RuntimeError: If another pipeline instance is already running
        """
        import os

        import psutil

        assert self.config.workdir is not None
        lock_file = self.config.workdir / ".pipeline.lock"

        if lock_file.exists():
            # Check if process is still running
            try:
                old_pid = int(lock_file.read_text().strip())

                # Check if process exists (cross-platform via psutil)
                if psutil.pid_exists(old_pid):
                    # Process exists - lock is valid
                    raise RuntimeError(
                        f"Pipeline already running (PID {old_pid}). "
                        f"If this is incorrect, delete: {lock_file}"
                    )
                else:
                    # Process doesn't exist - stale lock, take over
                    self.log.warning(f"Removing stale lock file (PID {old_pid} not found)")
                    lock_file.unlink()
            except (ValueError, OSError):
                # Invalid lock file, remove it
                self.log.warning("Removing invalid lock file")
                lock_file.unlink()

        # Create lock file with current PID
        lock_file.write_text(str(os.getpid()))
        self.log.debug(f"Acquired pipeline lock (PID {os.getpid()})")

    def _release_lock(self) -> None:
        """Release exclusive lock."""
        assert self.config.workdir is not None
        lock_file = self.config.workdir / ".pipeline.lock"

        try:
            lock_file.unlink(missing_ok=True)
            self.log.debug("Released pipeline lock")
        except Exception as e:
            self.log.warning(f"Failed to release lock: {e}")

    def _run_recovery_check(self) -> None:
        """
        Run automatic recovery check at pipeline startup.

        Detects and repairs inconsistencies from previous interruptions:
        - Intermediate ZIPs stuck in extracting/processing
        - Orphaned files in organized/ without DB entry
        - Orphaned files in extracted/ without DB entry
        - Missing file paths marked as error

        Recovery is fully automatic and idempotent. Failures are logged
        but do not prevent pipeline startup.
        """
        from takeout_photos.core.recovery import RecoveryManager

        try:
            self.log.info("Running automatic recovery check...")

            recovery_mgr = RecoveryManager(
                self.config, self.db, self.log, dry_run=self.config.dry_run
            )
            stats = recovery_mgr.check_and_recover()

            if stats.total == 0:
                self.log.info("✓ No recovery issues found")
            else:
                self.log.info(
                    f"✓ Recovery complete: {stats.total} issue(s) fixed "
                    f"({stats.intermediate_zips} ZIPs, "
                    f"{stats.orphaned_organized} organized/, "
                    f"{stats.orphaned_extracted} extracted/, "
                    f"{stats.missing_files} missing)"
                )
        except Exception as e:
            # Log but don't crash - recovery failure shouldn't prevent pipeline startup
            self.log.warning(f"Recovery check failed (continuing anyway): {e}")

    def _discover_and_register_zips(self) -> list[Path]:
        """
        Discover ZIPs in zips/ directory and register them in database.

        Returns:
            list[Path]: List of discovered ZIP paths, sorted by name

        Side Effects:
            - Registers any new ZIPs in database with 'pending' status
        """
        # Type narrowing (already asserted in __init__ but needed for mypy flow analysis)
        assert self.config.zips_dir is not None

        from takeout_photos.utils.system_files import should_ignore_path

        zips = sorted(self.config.zips_dir.glob("*.zip"))

        # Filter out system files
        zips = [z for z in zips if not should_ignore_path(z)]

        self.log.info(f"ZIPs found: {len(zips)}")

        # Register all ZIPs (no-op if already registered)
        for zip_path in zips:
            self.db.register_zip(zip_path.name)

        return zips

    def extract_all_zips(self) -> None:
        """
        Phase 1: Extract all pending ZIPs and register media files.

        Processes all ZIPs with status 'pending' or 'error'. Extracts
        contents to extracted/ (merged) and registers media files
        with associated JSON metadata in the database.

        Side Effects:
            - Extracts ZIPs to extracted/ directory
            - Registers JSON and media files in database
            - Updates ZIP status to 'extracted'

        Example:
            >>> pipeline = Pipeline(config)
            >>> pipeline.extract_all_zips()
            # Extracts all pending ZIPs
        """
        self.log.info("=== PHASE 1: Extraction ===")

        zips = self._discover_and_register_zips()

        for zip_path in zips:
            status = self.db.get_zip_status(zip_path.name)
            if status in ("pending", "error"):
                step_extract_zip(self.config, self.db, zip_path, self.log)

    def validate_formats(self) -> None:
        """
        Phase 1b: Validate file formats and correct mismatched extensions.

        Detects real file types using exiftool and corrects extensions
        if needed. Google Takeout often exports files with incorrect
        extensions (.HEIC files that are actually JPEG, etc.).

        Side Effects:
            - May rename files to correct extensions
            - Updates file paths in database
            - Stores existing EXIF datetime when an extension is corrected

        Example:
            >>> pipeline = Pipeline(config)
            >>> pipeline.extract_all_zips()
            >>> pipeline.validate_formats()
            # Corrects mismatched extensions
        """
        self.log.info("=== PHASE 1b: Format Validation ===")

        assert self.config.zips_dir is not None
        zips = list(self.config.zips_dir.glob("*.zip"))

        for zip_path in zips:
            status = self.db.get_zip_status(zip_path.name)
            if status in ("extracted", "processing"):
                step_validate_formats(self.config, self.db, zip_path.name, self.log)

    def apply_metadata_phase(self) -> None:
        """
        Phase 2: Apply metadata and compute hashes (per ZIP).

        For each ZIP in 'extracted' or 'processing' state:
        1. Apply JSON metadata to EXIF tags (batch operation)
        2. Compute content hashes for deduplication

        Side Effects:
            - Modifies EXIF data in extracted files
            - Computes and stores content hashes

        Example:
            >>> pipeline = Pipeline(config)
            >>> pipeline.extract_all_zips()
            >>> pipeline.validate_formats()
            >>> pipeline.apply_metadata_phase()
            # Processes all extracted ZIPs through metadata pipeline
        """
        self.log.info("=== PHASE 2: Metadata JSON → EXIF ===")

        assert self.config.zips_dir is not None
        zips = list(self.config.zips_dir.glob("*.zip"))

        for zip_path in zips:
            status = self.db.get_zip_status(zip_path.name)
            if status in ("extracted", "processing"):
                # Mark as processing
                self.db.update_zip_status(zip_path.name, "processing")

                # Run Phase 2 stages
                step_apply_metadata(self.config, self.db, zip_path.name, self.log)
                step_compute_hashes(self.config, self.db, zip_path.name, self.log)

    def quality_control(self) -> None:
        """
        Phase 5: Generate quality control report.

        Detects and reports potential metadata issues:
        - Files without DateTimeOriginal
        - Suspiciously old dates (< 1995)
        - Future dates
        - Suspicious epoch dates (1970-01-01, 2000-01-01)
        - Statistics by year

        Side Effects:
            - Creates timestamped QC report in logs/ directory

        Example:
            >>> pipeline = Pipeline(config)
            >>> # After organization...
            >>> pipeline.quality_control()
            # Generates QC report at logs/qc_*.txt

        Use Cases:
            - Identify files needing manual date correction
            - Verify pipeline processed files correctly
            - Generate statistics for reporting
            - Detect metadata corruption or export issues
        """
        # Skip QC in dry-run mode (nothing organized to check)
        if self.config.dry_run:
            self.log.info("[DRY RUN] Skipping quality control (no files organized)")
            return

        step_qc(self.config, self.db, self.log)

    def run(self) -> None:
        """
        Execute the complete pipeline in merge-extract mode.

        Two-phase processing to handle JSONs split across different ZIPs:
        - Phase 1: Extract all ZIPs to same directory (merge-extract)
        - Phase 2: Batch process all files (JSONs all available)

        Side Effects:
            - Extracts all ZIPs to extracted/ directory (merged)
            - Optionally deletes ZIPs after extraction
            - Processes all files: validate → metadata → hash → organize
            - Creates organized photo library in organized_dir/
            - Auto-cleans extracted/ at end (unless --keep-extracted-files)
            - Deduplicates against database (across all runs)
            - Records completion timestamp in database

        Example:
            >>> from takeout_photos.core.config import Config
            >>> from takeout_photos.core.pipeline import Pipeline
            >>>
            >>> config = Config(workdir="/path/to/work")
            >>> pipeline = Pipeline(config)
            >>> pipeline.run()
            # Processes complete pipeline in merge-extract mode

        Note:
            The pipeline is idempotent. If interrupted, rerun this
            method to resume from the last checkpoint. ZIPs marked as
            'organized' are skipped automatically.

        Architecture:
            - All ZIPs extract to same extracted/ directory (not per-ZIP subdirs)
            - This ensures JSONs are available even if split across different ZIPs
            - Batch processing after extraction (not per-ZIP incremental)

        Raises:
            Exception: If any stage fails, the exception is logged
                       and propagated. Rerun to resume from checkpoint.
        """
        self.log.info("Starting merge-extract pipeline")

        with Timer() as total_timer:
            try:
                # Discover and register any new physical ZIPs
                physical_zips = self._discover_and_register_zips()

                # PHASE 1: Extract new ZIPs (if any exist)
                if physical_zips:
                    self.log.info("=== PHASE 1: Merge-Extract ===")
                    with Timer() as phase1_timer:
                        self._extract_all_zips_merged(physical_zips)
                    self.log.info(f"=== Phase 1 complete ({phase1_timer.format_elapsed()}) ===")

                # PHASE 2: Batch process files from ALL extracted ZIPs
                # Query database for ZIPs needing processing (physical file not required)
                zip_names_to_process = self.db.get_zips_needing_processing()

                if zip_names_to_process:
                    self.log.info("=== PHASE 2: Batch Processing ===")
                    with Timer() as phase2_timer:
                        # Create Path objects for processing (only zip name matters for DB queries)
                        assert self.config.zips_dir is not None
                        zips_to_process = [
                            self.config.zips_dir / zip_name for zip_name in zip_names_to_process
                        ]

                        self._batch_process_all_files(zips_to_process)
                    self.log.info(f"=== Phase 2 complete ({phase2_timer.format_elapsed()}) ===")
                else:
                    self.log.info("No files need batch processing")

                # PHASE 3: Quality control report (global, run once at end)
                self.log.info("=== PHASE 3: Quality Control ===")
                with Timer() as phase3_timer:
                    self.quality_control()
                self.log.info(f"=== Phase 3 complete ({phase3_timer.format_elapsed()}) ===")

                # Record completion
                self.db.set_state("last_complete_run", datetime.now().isoformat())

                self.log.info(f"Pipeline complete ({total_timer.format_elapsed()})")

            except Exception as e:
                self.log.error(f"Pipeline failed: {e}")
                raise

    def _extract_all_zips_merged(self, zips: list[Path]) -> None:
        """
        Phase 1: Extract all ZIPs to the same extracted/ directory (merge-extract).

        Args:
            zips: List of ZIP file paths to extract

        Side Effects:
            - Extracts all ZIPs to extracted/ directory (merged, no per-ZIP subdirs)
            - Optionally deletes ZIPs after successful extraction
            - Updates ZIP status to 'extracted'

        Note:
            All ZIPs extract to the same directory so JSONs are available
            even if split across different ZIPs.
            ZIP deletion is handled inside step_extract_zip.
        """
        for zip_path in zips:
            # Check if already extracted
            status = self.db.get_zip_status(zip_path.name)
            if status in ("extracted", "processing", "organized"):
                self.log.info(f"Skipping extraction of {zip_path.name} (already extracted)")
                continue

            # Extract ZIP (deletion handled inside step_extract_zip)
            try:
                step_extract_zip(self.config, self.db, zip_path, self.log)
            except Exception as e:
                self.log.error(f"Failed to extract {zip_path.name}: {e}")
                self.db.update_zip_status(zip_path.name, "error", error_msg=str(e))
                # Continue with next ZIP
                continue

    def _batch_process_all_files(self, zips: list[Path]) -> None:
        """
        Phase 2: Batch process all files from all ZIPs.

        Processes all extracted files through validation, metadata application,
        hashing, and organization. This happens after ALL ZIPs are extracted,
        ensuring JSONs are available even if split across different ZIPs.

        Args:
            zips: List of ZIP file paths (for status tracking)

        Side Effects:
            - Validates all file formats
            - Applies metadata from JSONs to all files
            - Computes content hashes for all files
            - Organizes all files to organized_dir/ (with deduplication)
            - Cleans up extracted/ directory at end
            - Updates all ZIP statuses to 'organized'
        """
        from takeout_photos.stages.organize import step_organize_files_from_zip
        from takeout_photos.utils.cleanup import log_pipeline_summary, remove_empty_directories

        # In dry-run mode, skip batch processing since files weren't actually extracted
        if self.config.dry_run:
            self.log.info("[DRY RUN] Skipping batch processing (no files extracted)")
            return

        # Process each ZIP's files through the pipeline
        total_zips = len(zips)

        for zip_index, zip_path in enumerate(zips, start=1):
            zip_name = zip_path.stem

            # Check if already processed
            status = self.db.get_zip_status(zip_path.name)
            if status == "organized":
                self.log.info(f"Skipping {zip_name} (already organized)")
                continue

            # Skip if extraction failed
            if status == "error":
                self.log.warning(f"Skipping {zip_name} (extraction error)")
                continue

            self.log.info(f"  Processing files from {zip_path.name}...")

            with Timer() as zip_timer:
                try:
                    # 1. Validate formats
                    self.log.info("  [1/4] Validating formats...")
                    step_validate_formats(self.config, self.db, zip_name, self.log)

                    # 2. Apply metadata (JSONs all available now!)
                    self.log.info("  [2/4] Applying metadata...")
                    step_apply_metadata(self.config, self.db, zip_name, self.log)

                    # 3. Compute hashes
                    self.log.info("  [3/4] Computing hashes...")
                    step_compute_hashes(self.config, self.db, zip_name, self.log)

                    # 4. Organize files (includes deduplication)
                    self.log.info("  [4/4] Organizing files...")
                    stats = step_organize_files_from_zip(self.config, self.db, zip_name, self.log)

                    # Mark ZIP status based on errors
                    if stats["errors"] > 0:
                        error_msg = (
                            f"{stats['errors']} file(s) failed to organize. "
                            f"Fix issues and retry to process remaining files."
                        )
                        self.db.update_zip_status(zip_path.name, "error", error_msg=error_msg)
                        self.log.warning(f"⚠️  {zip_name}: {error_msg}")
                    else:
                        self.db.update_zip_status(zip_path.name, "organized")

                except Exception as e:
                    self.log.error(f"Failed to process files from {zip_name}: {e}")
                    self.db.update_zip_status(zip_path.name, "error", error_msg=str(e))
                    # Continue with next ZIP
                    continue

            self.log.info(
                f"  [{zip_index}/{total_zips}] {zip_path.name} processed "
                f"({zip_timer.format_elapsed()})"
            )

        # Cleanup: Remove empty directories conservatively
        self.log.info("Cleaning up empty directories...")

        # Type narrowing for mypy
        assert self.config.extracted_dir is not None
        assert self.config.duplicates_dir is not None
        assert self.config.organized_dir is not None

        cleanup_stats = {}

        # Clean extracted/ only if not keeping extracted files
        if not self.config.keep_extracted_files:
            cleanup_stats["extracted"] = remove_empty_directories(
                self.config.extracted_dir, self.log
            )
        else:
            self.log.info("Keeping extracted files (--keep-extracted-files)")
            cleanup_stats["extracted"] = 0

        # Always clean duplicates/ and organized/
        cleanup_stats["duplicates"] = remove_empty_directories(self.config.duplicates_dir, self.log)
        cleanup_stats["organized"] = remove_empty_directories(self.config.organized_dir, self.log)

        # Log pipeline summary
        log_pipeline_summary(self.config, self.db, self.log, cleanup_stats)

    def close(self) -> None:
        """
        Close database connection and release resources.

        Call this when done with the pipeline to properly clean up.
        Good practice especially in long-running scripts or when
        using Pipeline as a context manager.

        Example:
            >>> pipeline = Pipeline(config)
            >>> try:
            >>>     pipeline.run()
            >>> finally:
            >>>     pipeline.close()
        """
        self._release_lock()
        self.db.close()
        self.log.debug("Pipeline closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.close()
