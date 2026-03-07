"""
Pipeline stages module.

This module contains the 7 pipeline stages that process Google Takeout ZIPs:

Phase 1: Extraction & Validation
    - step_extract_zip: Extract ZIP and register media files
    - step_validate_formats: Validate and correct file extensions

Phase 2: Metadata & Hashing
    - step_apply_metadata: Apply JSON metadata to EXIF tags
    - step_compute_hashes: Compute content hashes for deduplication

Phase 3-5: Organization (incremental mode)
    - step_organize: Organize files by EXIF date into YYYY/MM structure (with inline dedup)
    - step_qc: Quality control and reporting

Each stage is a pure function with signature:
    (config: Config, db: PipelineDB, [zip_name|zip_path], log: logging.Logger) -> None

Stages are stateless and idempotent - they can be safely re-run.
State is persisted in the SQLite database between stages.
"""

from __future__ import annotations

from takeout_photos.stages.extract import step_extract_zip
from takeout_photos.stages.hash import step_compute_hashes
from takeout_photos.stages.metadata import step_apply_metadata
from takeout_photos.stages.qc import step_qc
from takeout_photos.stages.validate import step_validate_formats

__all__ = [
    "step_extract_zip",
    "step_validate_formats",
    "step_apply_metadata",
    "step_compute_hashes",
    "step_qc",
]
