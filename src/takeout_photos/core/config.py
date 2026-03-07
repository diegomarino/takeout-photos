"""
Pipeline configuration management.

This module provides the Config dataclass that holds all configuration
parameters for the takeout_photos pipeline, including directory paths,
processing options, and feature flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """
    Pipeline configuration container.

    This dataclass holds all configuration parameters for the pipeline,
    including directory paths, processing options, and feature flags.
    All directory paths are derived from the base workdir and initialized
    in __post_init__.

    Args:
        workdir: Base working directory (all other paths derived from this)
        zips_dir: Directory containing input ZIP files (default: workdir root)
        extracted_dir: Temporary directory for extracted ZIP contents (default: workdir/extracted)
        duplicates_dir: Directory for duplicate files (default: workdir/duplicates)
        final_dir: Final output directory for organized photos (default: workdir/organized_media)
        organized_dir: Alias for final_dir, can be customized (default: workdir/organized_media)
        logs_dir: Directory for log files and QC reports (default: workdir/logs)
        db_path: Path to SQLite database file (default: workdir/pipeline.db)
        exif_warnings_file: Path to exiftool warnings file (set during logging setup, default: None)
        workers: Number of parallel workers for CPU-bound tasks (default: 4)
        batch_size: Batch size for bulk operations (default: 500)
        checkpoint_interval: Commit database every N files/hashes (default: 100)
        organize_layout: Directory layout 'yyyy_mm' or 'yyyy' (default: yyyy_mm)
        dated_filenames: Prefix filenames with date YYYY-MM-DD_ (default: False)
        qc_min_year: Minimum valid year for QC checks (default: 1995)
        qc_max_year: Maximum valid year for QC checks (default: 2030)
        dry_run: If True, simulate operations without making changes (default: False)
        verbose: Enable verbose logging (default: False)
        delete_zips_after_extract: If True, delete ZIPs after successful extraction (default: False)
        keep_extracted_files: If True, preserve extracted/ after organizing (default: False)
        skip_deps_check: If True, skip dependency verification (default: False)

    Example:
        >>> config = Config(workdir="/path/to/work")
        >>> config.zips_dir
        PosixPath('/path/to/work')
        >>> config.workers
        4
    """

    workdir: Path
    zips_dir: Path | None = None
    extracted_dir: Path | None = None
    duplicates_dir: Path | None = None
    final_dir: Path | None = None
    organized_dir: Path | None = None
    logs_dir: Path | None = None
    db_path: Path | None = None
    exif_warnings_file: Path | None = None  # Set during logging setup

    # Processing options
    workers: int = 4
    batch_size: int = 500
    checkpoint_interval: int = 100  # Commit every N files/hashes
    organize_layout: str = "yyyy_mm"  # yyyy_mm or yyyy
    dated_filenames: bool = False

    # QC thresholds
    qc_min_year: int = 1995
    qc_max_year: int = 2030

    # Flags
    dry_run: bool = False
    verbose: bool = False
    delete_zips_after_extract: bool = False
    keep_extracted_files: bool = False
    skip_deps_check: bool = False

    def __post_init__(self):
        """
        Initialize derived paths from base workdir.

        Expands user home directory (~) and resolves to absolute paths.
        Sets default values for all optional directory paths.

        Side effects:
            Sets all directory attributes to absolute Path objects.
            Creates organized_dir if it doesn't exist (for incremental pipeline).
        """
        self.workdir = Path(self.workdir).expanduser().resolve()
        self.zips_dir = self.zips_dir or self.workdir
        self.extracted_dir = self.extracted_dir or self.workdir / "extracted"
        self.duplicates_dir = self.duplicates_dir or self.workdir / "duplicates"
        self.final_dir = self.final_dir or self.workdir / "organized_media"
        self.logs_dir = self.logs_dir or self.workdir / "logs"
        self.db_path = self.db_path or self.workdir / "pipeline.db"

        # Set organized_dir default (alias for final_dir, can be overridden)
        if self.organized_dir is None:
            self.organized_dir = self.final_dir
        else:
            self.organized_dir = Path(self.organized_dir).expanduser().resolve()

        # Ensure organized_dir exists
        self.organized_dir.mkdir(parents=True, exist_ok=True)

        # Type narrowing: after initialization, these are never None
        assert self.zips_dir is not None
        assert self.extracted_dir is not None
        assert self.duplicates_dir is not None
        assert self.final_dir is not None
        assert self.organized_dir is not None
        assert self.logs_dir is not None
        assert self.db_path is not None
