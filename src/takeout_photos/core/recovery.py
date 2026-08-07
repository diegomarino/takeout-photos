"""Recovery system for detecting and fixing pipeline inconsistencies."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from takeout_photos.core.config import Config
from takeout_photos.core.constants import RECOVERED_ORPHANS_ZIP
from takeout_photos.core.database import PipelineDB
from takeout_photos.utils.system_files import should_ignore_path


@dataclass
class RecoveryStats:
    """Statistics collected during recovery."""

    intermediate_zips: int = 0
    orphaned_organized: int = 0
    orphaned_extracted: int = 0
    missing_files: int = 0
    staged_files: int = 0

    @property
    def total(self) -> int:
        """Total number of issues found."""
        return (
            self.intermediate_zips
            + self.orphaned_organized
            + self.orphaned_extracted
            + self.missing_files
            + self.staged_files
        )


class RecoveryManager:
    """
    Handles detection and recovery of pipeline inconsistencies.

    This class runs at pipeline startup to detect and automatically resolve
    state inconsistencies caused by interruptions (Ctrl+C, crashes, etc).

    Recovery is fully automatic and idempotent - safe to run multiple times.

    Dry-Run Mode:
        When dry_run=True, only detects issues without fixing them.
        Useful for diagnostics (doctor command) or testing.

    Architecture Note (v3.0.1):
        All ZIPs extract to the same extracted/ directory (merge-extract).
        Recovery logic is architecture-agnostic and works for both single
        and merged extraction directories.
    """

    def __init__(self, config: Config, db: PipelineDB, log: logging.Logger, dry_run: bool = False):
        """
        Initialize RecoveryManager.

        Args:
            config: Pipeline configuration
            db: Database connection
            log: Logger instance
            dry_run: If True, only detect issues without fixing (default: False)
        """
        self.config = config
        self.db = db
        self.log = log
        self.dry_run = dry_run
        self.stats = RecoveryStats()

        # Type narrowing
        assert self.config.organized_dir is not None
        assert self.config.duplicates_dir is not None
        assert self.config.extracted_dir is not None

    def check_and_recover(self) -> RecoveryStats:
        """
        Main entry point: detect and optionally recover inconsistencies.

        Runs automatically at pipeline startup. Performs full consistency
        check and repairs any issues found (unless dry_run=True).

        Returns:
            RecoveryStats with counts of each inconsistency type found

        Performance:
            ~30-45s for detection with 300k files
            Recovery time varies based on issues found

        Dry-Run Mode:
            If dry_run=True, only detects issues without making any changes.
            Useful for diagnostics and testing.
        """
        if self.dry_run:
            self.log.info("=== Recovery Check (Dry-Run Mode) ===")
        else:
            self.log.info("=== Recovery Check ===")

        start_time = time.time()

        # Detection and Recovery (combined for efficiency)
        self._detect_and_recover_intermediate_zips()
        self._detect_and_recover_staged_files()
        self._detect_and_recover_orphaned_organized()
        self._detect_and_recover_orphaned_extracted()
        self._detect_and_recover_missing_files()

        # Reporting
        elapsed = time.time() - start_time
        if not self.dry_run:
            self._write_recovery_log()
        self._print_summary(elapsed)

        return self.stats

    def _detect_and_recover_intermediate_zips(self):
        """
        Detect and reset ZIPs stuck in intermediate states.

        Intermediate states occur when process crashes during:
        - 'extracting': Process crashed during ZIP extraction
        - 'processing': Process crashed during file processing

        Recovery action:
        - extracting → pending (needs re-extraction)
        - processing → extracted (files extracted, need re-processing)

        Dry-run mode: Only counts, does not modify statuses.
        """
        # Get ZIPs stuck in intermediate states
        intermediate_zips = self.db.get_intermediate_zips()

        for row in intermediate_zips:
            zip_name = row["name"]
            old_status = row["status"]

            # Determine new status
            if old_status == "extracting":
                new_status = "pending"
            elif old_status == "processing":
                new_status = "extracted"
            else:
                continue  # Should not happen

            if self.dry_run:
                self.log.info(f"[DRY-RUN] Would reset {zip_name}: {old_status} → {new_status}")
            else:
                self.db.update_zip_status(zip_name, new_status)
                self.log.info(f"Reset {zip_name}: {old_status} → {new_status}")

            self.stats.intermediate_zips += 1

    def _detect_and_recover_staged_files(self):
        """
        Detect and recover files stuck in 'staged' state.

        Staged files occur when:
        - Process crashes between DB update (staged) and final update (organized)
        - File may or may not have been moved to organized/

        Recovery action:
        - If staged_path exists: complete staging → status='organized'
        - If staged_path missing: revert → status='pending'

        Dry-run mode: Only counts, does not modify state.
        """
        # Type narrowing for mypy
        assert self.config.organized_dir is not None

        # Get all files in 'staged' state
        staged_files = self.db.conn.execute(
            "SELECT id, original_path, staged_path, content_hash, file_size FROM files WHERE status = 'staged'"
        ).fetchall()

        if not staged_files:
            return

        for row in staged_files:
            file_id = row["id"]
            staged_path = row["staged_path"]

            if not staged_path:
                # Malformed staged record, revert to pending
                if self.dry_run:
                    self.log.info(
                        f"[DRY-RUN] Would revert staged file (no path): {row['original_path']}"
                    )
                else:
                    self.db.update_file(file_id, status="pending", staged_path=None)
                    self.log.info(f"Reverted staged file (no path): {row['original_path']}")
                self.stats.staged_files += 1
                continue

            # Check if file exists at staged location
            from pathlib import Path

            full_path = self.config.organized_dir / staged_path

            if full_path.exists():
                # File was moved successfully, complete the staging
                if self.dry_run:
                    self.log.info(f"[DRY-RUN] Would complete staging: {staged_path}")
                else:
                    # Insert into organized_files if not already there
                    existing = self.db.conn.execute(
                        "SELECT hash FROM organized_files WHERE hash = ?", (row["content_hash"],)
                    ).fetchone()

                    if not existing:
                        self.db.insert_organized_file(
                            hash=row["content_hash"],
                            original_name=Path(row["original_path"]).name,
                            final_path=staged_path,
                            source_zip="unknown",  # Lost in crash
                            file_size=row["file_size"],
                        )

                    # Mark as organized
                    self.db.update_file(file_id, status="organized", final_path=staged_path)
                    self.log.info(f"Completed staging: {staged_path}")
            else:
                # File wasn't moved, revert to pending for retry
                if self.dry_run:
                    self.log.info(f"[DRY-RUN] Would revert to pending: {row['original_path']}")
                else:
                    self.db.update_file(file_id, status="pending", staged_path=None)
                    self.log.info(f"Reverted to pending: {row['original_path']}")

            self.stats.staged_files += 1

        if not self.dry_run:
            self.db.conn.commit()

    def _detect_and_recover_orphaned_organized(self):
        """
        Detect and register files in organized/ without database entry.

        Orphaned files occur when:
        - File was moved to organized/ but DB insert failed
        - This is prevented by Task 4 (DB-before-move), but may exist from old runs

        Recovery action:
        - Scan organized/ directory
        - Check each file against organized_files table
        - Register orphans with placeholder metadata

        Dry-run mode: Only counts, does not register files.
        """
        # Type narrowing for mypy
        assert self.config.organized_dir is not None

        if not self.config.organized_dir.exists():
            return

        # Get all organized files from DB (hash as key for fast lookup)
        db_files = self.db.conn.execute("SELECT final_path FROM organized_files").fetchall()
        db_paths = {row["final_path"] for row in db_files}

        # Scan organized/ directory
        orphans = []
        for file_path in self.config.organized_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # Filter system files
            if should_ignore_path(file_path):
                continue

            # Get relative path from organized/ root
            try:
                relative_path = file_path.relative_to(self.config.organized_dir)
            except ValueError:
                continue

            # Check if in DB
            if str(relative_path) not in db_paths:
                orphans.append((file_path, relative_path))

        # Register orphans
        for file_path, relative_path in orphans:
            if self.dry_run:
                self.log.info(f"[DRY-RUN] Would register orphan: {relative_path}")
            else:
                # Register with placeholder values (no hash available)
                from takeout_photos.hashing.hasher import compute_hash

                file_hash = compute_hash(file_path)
                file_size = file_path.stat().st_size

                self.db.insert_organized_file(
                    hash=file_hash,
                    original_name=file_path.name,
                    final_path=str(relative_path),
                    source_zip="unknown",
                    file_size=file_size,
                )
                self.log.info(f"Registered orphan: {relative_path}")

                # Also update files table if record exists
                file_record = self.db.conn.execute(
                    'SELECT id FROM files WHERE content_hash = ? AND status != "organized"',
                    (file_hash,),
                ).fetchone()

                if file_record:
                    self.db.update_file(
                        file_record["id"], status="organized", final_path=str(relative_path)
                    )
                    self.log.info(f"Updated files table for orphan: {relative_path}")

            self.stats.orphaned_organized += 1

    def _detect_and_recover_orphaned_extracted(self):
        """
        Detect and register files in extracted/ without database entry.

        Orphaned files occur when:
        - Files extracted but not registered (rare, extraction is atomic)
        - Manual files added to extracted/

        Recovery action:
        - Scan extracted/ directory
        - Check each file against files table
        - Register orphans under a reserved synthetic ZIP name
          (constants.RECOVERED_ORPHANS_ZIP)
        - Set that synthetic ZIP's status to 'extracted' so the next `process` run
          validates, hashes, and organizes them (matching the "Manual files
          added to extracted/" recovery scenario documented in docs/api.md)

        Dry-run mode: Only counts, does not register files.
        """
        # Type narrowing for mypy
        assert self.config.extracted_dir is not None

        if not self.config.extracted_dir.exists():
            return

        # Get all extracted files from DB
        db_files = self.db.conn.execute("SELECT original_path FROM files").fetchall()
        db_paths = {row["original_path"] for row in db_files}

        # Scan extracted/ directory
        orphans = []
        for file_path in self.config.extracted_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # Filter system files
            if should_ignore_path(file_path):
                continue

            # Check if in DB
            if str(file_path) not in db_paths:
                orphans.append(file_path)

        # Synthetic ZIP name for orphaned files. It MUST carry the ".zip"
        # suffix that every downstream reader expects: get_files_for_zip()
        # (used by validate/metadata/hash) appends ".zip" to the name it
        # queries with, so registering files under a bare "unknown" makes those
        # stages silently find zero files and never process the orphans. The
        # reserved sentinel name (see constants.RECOVERED_ORPHANS_ZIP) also
        # cannot collide with a real Takeout archive.
        recovered_zip = RECOVERED_ORPHANS_ZIP

        # Ensure the synthetic ZIP row exists for orphans
        if orphans and not self.dry_run:
            zip_exists = self.db.conn.execute(
                "SELECT COUNT(*) FROM zips WHERE name = ?", (recovered_zip,)
            ).fetchone()[0]

            if zip_exists == 0:
                self.db.register_zip(recovered_zip)

        # Register orphans
        for file_path in orphans:
            if self.dry_run:
                self.log.info(f"[DRY-RUN] Would register orphan: {file_path.name}")
            else:
                file_size = file_path.stat().st_size

                self.db.register_file(
                    zip_name=recovered_zip,
                    original_path=str(file_path),
                    file_size=file_size,
                )
                self.log.info(f"Registered orphan: {file_path.name}")

            self.stats.orphaned_extracted += 1

        # Advance the synthetic ZIP to 'extracted' so a subsequent `process`
        # run actually picks it up. register_zip() leaves status='pending', but
        # get_zips_needing_processing() only returns 'extracted'/'processing',
        # so without this the orphans would be registered and then stall
        # forever. update_zip_status() commits, which also flushes the
        # register_file() inserts above.
        if orphans and not self.dry_run:
            self.db.update_zip_status(recovered_zip, "extracted")

    def _detect_and_recover_missing_files(self):
        """
        Detect files with invalid paths and mark as error.

        Missing files occur when:
        - File path in DB no longer exists on filesystem
        - Manual deletion of extracted/ or organized/ files

        Recovery action:
        - Sample files table (checking all would be slow)
        - Verify paths exist on filesystem
        - Mark missing files with status='error'

        Dry-run mode: Only counts, does not mark as error.

        Performance:
        - For datasets >10k files, samples 500 random files
        - For smaller datasets, checks all files
        """
        from pathlib import Path

        # Get file count
        total_files = self.db.conn.execute(
            "SELECT COUNT(*) FROM files WHERE status NOT IN ('error', 'organized')"
        ).fetchone()[0]

        # Decide on sampling
        if total_files > 10000:
            # Large dataset: sample 500 random files
            sample_size = 500
            rows = self.db.conn.execute(
                """
                SELECT id, original_path
                FROM files
                WHERE status NOT IN ('error', 'organized')
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (sample_size,),
            ).fetchall()
            self.log.info(f"Sampling {sample_size} of {total_files} files for verification")
        else:
            # Small dataset: check all files
            rows = self.db.conn.execute("""
                SELECT id, original_path
                FROM files
                WHERE status NOT IN ('error', 'organized')
                """).fetchall()

        # Check each file
        missing_ids = []
        for row in rows:
            file_id = row["id"]
            original_path = Path(row["original_path"])

            if not original_path.exists():
                missing_ids.append(file_id)

        # Mark as error
        if missing_ids:
            if self.dry_run:
                self.log.info(f"[DRY-RUN] Would mark {len(missing_ids)} missing file(s) as error")
            else:
                # Batch update for performance
                placeholders = ",".join("?" * len(missing_ids))
                self.db.conn.execute(
                    f"UPDATE files SET status = 'error' WHERE id IN ({placeholders})",
                    missing_ids,
                )
                self.db.conn.commit()
                self.log.info(f"Marked {len(missing_ids)} missing file(s) as error")

            self.stats.missing_files = len(missing_ids)

    def _write_recovery_log(self):
        """Write recovery summary to recovery_log table."""
        if self.stats.total == 0:
            return

        # Log each recovery type that had issues
        if self.stats.intermediate_zips > 0:
            self.db.log_recovery(
                "intermediate_zips",
                self.stats.intermediate_zips,
                {"message": "Reset ZIPs in intermediate state"},
            )

        if self.stats.orphaned_organized > 0:
            self.db.log_recovery(
                "orphaned_organized",
                self.stats.orphaned_organized,
                {"message": "Registered orphaned files in organized/"},
            )

        if self.stats.orphaned_extracted > 0:
            self.db.log_recovery(
                "orphaned_extracted",
                self.stats.orphaned_extracted,
                {"message": "Registered orphaned files in extracted/"},
            )

        if self.stats.missing_files > 0:
            self.db.log_recovery(
                "missing_files",
                self.stats.missing_files,
                {"message": "Marked files with missing paths as error"},
            )

        if self.stats.staged_files > 0:
            self.db.log_recovery(
                "staged_files",
                self.stats.staged_files,
                {"message": "Recovered files stuck in staged state"},
            )

    def _print_summary(self, elapsed: float):
        """Print recovery summary."""
        if self.stats.total == 0:
            self.log.info(f"✓ No issues found ({elapsed:.1f}s)")
        else:
            mode = "[DRY-RUN] " if self.dry_run else ""
            self.log.info(f"{mode}Recovery complete: {self.stats.total} issue(s) ({elapsed:.1f}s)")

            if self.stats.intermediate_zips > 0:
                self.log.info(f"  - {self.stats.intermediate_zips} intermediate ZIP(s) reset")
            if self.stats.staged_files > 0:
                self.log.info(f"  - {self.stats.staged_files} staged file(s) recovered")
            if self.stats.orphaned_organized > 0:
                self.log.info(f"  - {self.stats.orphaned_organized} orphaned file(s) in organized/")
            if self.stats.orphaned_extracted > 0:
                self.log.info(f"  - {self.stats.orphaned_extracted} orphaned file(s) in extracted/")
            if self.stats.missing_files > 0:
                self.log.info(f"  - {self.stats.missing_files} missing file(s) marked as error")
