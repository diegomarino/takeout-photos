"""
Quality control stage.

Phase 5 of the pipeline: Detect and report potential metadata issues.
"""

from __future__ import annotations

import logging
from datetime import datetime

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.exif.operations import run_exiftool
from takeout_photos.utils.system_files import should_ignore_path
from takeout_photos.utils.timer import Timer


def step_qc(config: Config, db: PipelineDB, log: logging.Logger) -> None:
    """
    Quality control: detect and report potential issues.

    This is Phase 5 of the pipeline:
    1. Find files without DateTimeOriginal
    2. Detect suspiciously old dates (< 1995)
    3. Detect future dates (> today)
    4. Detect suspicious epoch dates (1970-01-01, 2000-01-01)
    5. Generate statistics by year
    6. Write comprehensive report to logs/

    Args:
        config: Pipeline configuration
        db: Database connection
        log: Logger instance

    Side Effects:
        - Creates QC report in logs/ directory

    Example:
        >>> from takeout_photos.core.config import Config
        >>> from takeout_photos.core.database import PipelineDB
        >>> from takeout_photos.stages.qc import step_qc
        >>> import logging
        >>>
        >>> config = Config(workdir="/path/to/work")
        >>> db = PipelineDB(config.db_path)
        >>> log = logging.getLogger(__name__)
        >>>
        >>> step_qc(config, db, log)
        # Generates QC report at logs/qc_20240115_143022.txt

    Note:
        This generates a human-readable report for manual review.
        The QC checks help identify metadata issues that may need
        manual correction.

        The report includes:
        - Files without DateTimeOriginal (in no_date/)
        - Very old dates (< 1995) - may be incorrect
        - Future dates - definitely incorrect
        - Suspicious dates (1970-01-01, 2000-01-01) - likely default values
        - File count statistics by year

    Report Format:
        # QC Report - 2024-01-15 14:30:22
        # Final directory: /path/to/work/organized_media

        ## Files without DateTimeOriginal: 15
          abc123def.jpg
          def456ghi.mp4
          ... and 13 more

        ## Very old dates (< 1995)
        1985:03:12 12:34:56 - 1985/03/jkl789mno.jpg

        ## Future dates
        2027:06:18 09:15:30 - 2027/06/pqr012stu.heic

        ## Suspicious dates (1970-01-01 or 2000-01-01)
        1970:01:01 00:00:00 - 1970/01/vwx345yz.png
        2000:01:01 00:00:00 - 2000/01/abc678def.jpg

        ## Statistics
        Total files in final: 5678
          2018: 234
          2019: 456
          2020: 789
          2021: 1234
          2022: 987
          2023: 543
          2024: 321
          no_date: 15

    Use Cases:
        - Identify files needing manual date correction
        - Verify pipeline processed files correctly
        - Generate statistics for reporting
        - Detect metadata corruption or export issues
    """
    assert config.logs_dir is not None
    assert config.organized_dir is not None

    config.logs_dir.mkdir(parents=True, exist_ok=True)
    qc_report = config.logs_dir / f"{datetime.now():%Y%m%d_%H%M%S}_qc.txt"

    with Timer() as timer:
        with open(qc_report, "w") as report:
            report.write(f"# QC Report - {datetime.now()}\n")
            report.write(f"# Organized directory: {config.organized_dir}\n\n")

            # Files without dates
            no_date = config.organized_dir / "no_date"
            if no_date.exists():
                files = list(no_date.rglob("*"))  # Use rglob to get files in subdirs too
                files = [f for f in files if f.is_file() and not should_ignore_path(f)]
                report.write(f"## Files without DateTimeOriginal: {len(files)}\n")
                for f in files[:50]:  # Limit output
                    # Show path relative to organized directory
                    rel_path = f.relative_to(config.organized_dir)
                    report.write(f"  {rel_path}\n")
                if len(files) > 50:
                    report.write(f"  ... and {len(files) - 50} more\n")
                report.write("\n")

            # Suspiciously old dates (< 1995)
            result = run_exiftool(
                [
                    "-r",
                    "-q",
                    "-q",
                    "-if",
                    '$DateTimeOriginal lt "1995:01:01"',
                    "-p",
                    "$DateTimeOriginal - $Directory/$FileName",
                    str(config.organized_dir),
                ]
            )
            if result.stdout.strip():
                report.write("## Very old dates (< 1995)\n")
                report.write(result.stdout)
                report.write("\n")

            # Future dates
            result = run_exiftool(
                [
                    "-r",
                    "-q",
                    "-q",
                    "-if",
                    "$DateTimeOriginal gt $now",
                    "-p",
                    "$DateTimeOriginal - $Directory/$FileName",
                    str(config.organized_dir),
                ]
            )
            if result.stdout.strip():
                report.write("## Future dates\n")
                report.write(result.stdout)
                report.write("\n")

            # Suspicious dates (1970 or 2000 - likely epoch/default values)
            result = run_exiftool(
                [
                    "-r",
                    "-q",
                    "-q",
                    "-if",
                    "$DateTimeOriginal =~ /^(1970|2000):01:01/",
                    "-p",
                    "$DateTimeOriginal - $Directory/$FileName",
                    str(config.organized_dir),
                ]
            )
            if result.stdout.strip():
                report.write("## Suspicious dates (1970-01-01 or 2000-01-01)\n")
                report.write(result.stdout)
                report.write("\n")

            # Statistics
            total_organized = sum(
                1
                for _ in config.organized_dir.rglob("*")
                if _.is_file() and not should_ignore_path(_)
            )
            report.write("\n## Statistics\n")
            report.write(f"Total files organized: {total_organized}\n")

            # By year
            for year_dir in sorted(config.organized_dir.iterdir()):
                if year_dir.is_dir() and year_dir.name.isdigit():
                    count = sum(
                        1 for _ in year_dir.rglob("*") if _.is_file() and not should_ignore_path(_)
                    )
                    report.write(f"  {year_dir.name}: {count}\n")

    log.info(f"  QC report generated: {qc_report.name} ({timer.format_elapsed()})")
