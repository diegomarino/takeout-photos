"""
Content hashing stage.

Phase 2b of the pipeline: Compute content hashes for deduplication.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.hashing.hasher import compute_hash
from takeout_photos.utils.progress import progress_bar
from takeout_photos.utils.timer import Timer


def _compute_hash_worker(file_record: dict) -> tuple:
    """
    Worker function for parallel hash computation.

    Args:
        file_record: Dictionary with 'id' and 'original_path' keys

    Returns:
        Tuple of (file_id, hash_value, error_message or None)

    Note:
        This function is designed to be used with ProcessPoolExecutor
        for CPU-bound parallel hashing operations.
    """
    try:
        h = compute_hash(Path(file_record["original_path"]))
        return (file_record["id"], h, None)
    except Exception as e:
        return (file_record["id"], None, str(e))


def step_compute_hashes(config: Config, db: PipelineDB, zip_name: str, log: logging.Logger) -> None:
    """
    Compute content hashes for deduplication using parallel workers.

    This is Phase 2b of the pipeline:
    1. Identify files without content hashes
    2. Compute hash for each file in parallel (xxhash or SHA256)
    3. Store hash in database

    Args:
        config: Pipeline configuration
        db: Database connection
        zip_name: Name of ZIP being processed
        log: Logger instance

    Side Effects:
        - Updates content_hash field in files table
        - Marks files as status="error" with error_msg when hashing fails

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.hash import step_compute_hashes
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work", workers=8)
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> step_compute_hashes(config, db, "takeout-001.zip", log)
        # Computes hashes for 1234 files using 8 parallel workers

    Note:
        Hash is based purely on file content, not filename or metadata.
        This enables detection of identical files across different ZIPs
        even if they have different names or paths.

        Uses ProcessPoolExecutor for parallel processing, significantly
        speeding up hash computation for large collections.

    Performance:
        For 1000 files @ 2MB each with 8 workers:
        - With xxhash: ~30 seconds
        - With SHA256: ~90 seconds
    """
    files = db.get_files_for_zip(zip_name)
    files_to_hash = [f for f in files if not f["content_hash"]]

    if not files_to_hash:
        log.info(f"All files in {zip_name} already have hashes")
        return

    # Dry-run mode: log what would be done but don't compute hashes
    if config.dry_run:
        log.info(f"[DRY RUN] Would compute hashes for {len(files_to_hash)} files")
        return

    with Timer() as timer:
        # Use parallel processing for hash computation (CPU-bound task)
        with ProcessPoolExecutor(max_workers=config.workers) as executor:
            # Submit all hash jobs
            futures = {executor.submit(_compute_hash_worker, f): f for f in files_to_hash}

            # Process results as they complete
            for future in progress_bar(as_completed(futures), total=len(futures), desc="Hashing"):
                file_id, hash_value, error = future.result()

                if error:
                    file_record = futures[future]
                    log.warning(f"Error computing hash for {file_record['original_path']}: {error}")
                    # Mark file as error so it's visible in status/QC reports
                    db.update_file(
                        file_id, status="error", error_msg=f"Hash computation failed: {error}"
                    )
                elif hash_value:
                    db.update_file(file_id, content_hash=hash_value)

        db.commit()

    log.info(f"  Hashes computed: {len(files_to_hash):,} files ({timer.format_elapsed()})")
