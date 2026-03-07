"""
Deduplication utilities for incremental processing.

Deduplication happens per-file during organization, not as a global batch.
This module provides the check function used during incremental processing.
"""

from __future__ import annotations

from takeout_photos.core.database import PipelineDB


def check_if_duplicate(hash: str, db: PipelineDB) -> bool:
    """
    Check if file with this hash was already organized.

    This is used during incremental ZIP processing to determine if a file
    should go to organized/ (unique) or duplicates/ (duplicate).

    Args:
        hash: Content hash of file
        db: Database connection

    Returns:
        True if duplicate (hash exists in organized_files), False if unique

    Example:
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.dedupe import check_if_duplicate
        >>>
        >>> db = PipelineDB("/path/to/pipeline.db")
        >>> if check_if_duplicate("abc123def456", db):
        ...     print("This file is a duplicate")
        ... else:
        ...     print("This is a unique file - organize it")

    Note:
        This replaces the global step_deduplicate() batch operation.
        Deduplication now happens incrementally as each ZIP is processed.
    """
    return db.check_duplicate(hash)
