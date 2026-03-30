#!/usr/bin/env python3
"""Analyze remaining no_date files against organized folders.

Produces a report with actionable categories:
  - SAFE_DELETE: non-generic filename or video >5MB with similar-sized dated copy
  - REVIEW: generic IMG_NNNN with similar-sized dated copy — needs visual check
  - ORPHAN: no match in any dated folder, or very different sizes

Usage:
    python tools/analyze_no_date.py --workdir /path/to/workdir
    python tools/analyze_no_date.py --workdir /path/to/workdir --output /tmp/report.log
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

DUPE_SUFFIX = re.compile(r"\(\d+\)(?=\.[^.]+$)")
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}_")
NO_DATE_PREFIX = re.compile(r"^NO-DATE_")
GENERIC_NAME = re.compile(r"^IMG_\d{4}", re.IGNORECASE)
VIDEO_EXTS = {".mov", ".mp4", ".avi", ".mkv", ".m4v", ".3gp"}
SIZE_THRESHOLD = 5 * 1024 * 1024  # 5MB
SIZE_TOLERANCE = 0.001  # 0.1%


def base_name(filename: str) -> str:
    name = filename
    name = DUPE_SUFFIX.sub("", name)
    name = DATE_PREFIX.sub("", name)
    name = NO_DATE_PREFIX.sub("", name)
    return name


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workdir", type=Path, required=True, help="Pipeline working directory")
    parser.add_argument("--organized-dir", type=Path, help="Override organized media directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/analyze_no_date_report.log"),
        help="Output report path",
    )
    args = parser.parse_args()

    organized = args.organized_dir or args.workdir / "organized_media"
    no_date = organized / "no_date"

    if not no_date.exists():
        print(f"No no_date/ directory found at {no_date}")
        sys.exit(0)

    # Index all dated files by base name
    print("Indexing dated folders...")
    sys.stdout.flush()

    dated_index: dict[str, list] = defaultdict(list)
    for d in organized.iterdir():
        if d.is_dir() and d.name != "no_date":
            for f in d.rglob("*"):
                if f.is_file() and not f.name.startswith("._") and f.suffix != ".json":
                    bn = base_name(f.name)
                    dated_index[bn].append((str(f.relative_to(organized)), f.stat().st_size))

    print(f"  Indexed {len(dated_index):,} unique base names in dated folders")

    # Analyze no_date files
    print("Analyzing no_date files...")
    sys.stdout.flush()

    no_date_files = [
        f
        for f in no_date.rglob("*")
        if f.is_file() and not f.name.startswith("._") and f.suffix != ".json"
    ]
    print(f"  {len(no_date_files):,} files in no_date/")

    safe_delete: list[tuple] = []
    review: list[tuple] = []
    orphans: list[tuple] = []

    for f in no_date_files:
        bn = base_name(f.name)
        size = f.stat().st_size
        ext = f.suffix.lower()
        is_video = ext in VIDEO_EXTS
        is_generic = bool(GENERIC_NAME.match(bn))

        if bn in dated_index:
            matches = dated_index[bn]

            has_similar_size = any(
                abs(size - m_size) / max(size, m_size, 1) <= SIZE_TOLERANCE for _, m_size in matches
            )

            if has_similar_size:
                if is_video and size > SIZE_THRESHOLD:
                    safe_delete.append((f, bn, size, matches))
                elif not is_generic:
                    safe_delete.append((f, bn, size, matches))
                else:
                    review.append((f, bn, size, matches))
            else:
                orphans.append((f, bn, size))
        else:
            orphans.append((f, bn, size))

    # Write report
    safe_size = sum(s for _, _, s, _ in safe_delete)
    review_size = sum(s for _, _, s, _ in review)
    orphan_size = sum(s for _, _, s in orphans)

    with open(args.output, "w") as report:
        report.write("# no_date analysis report\n")
        report.write(f"# Total no_date files: {len(no_date_files):,}\n")
        report.write(
            f"#   SAFE_DELETE: {len(safe_delete):,} (video >5MB or unique filename with dated copy)\n"
        )
        report.write(
            f"#   REVIEW:     {len(review):,} (generic IMG_NNNN name, needs visual check)\n"
        )
        report.write(f"#   ORPHAN:     {len(orphans):,} (no match in dated folders)\n\n")
        report.write(
            f"# Space: SAFE_DELETE {safe_size/1024**3:.1f}GB, REVIEW {review_size/1024**3:.1f}GB, ORPHAN {orphan_size/1024**3:.1f}GB\n\n"
        )

        for label, items in [("SAFE_DELETE", safe_delete), ("REVIEW", review)]:
            size_total = sum(s for _, _, s, _ in items)
            report.write(f"{'='*80}\n")
            report.write(f"{label} ({len(items):,} files, {size_total/1024**3:.1f} GB)\n")
            report.write(f"{'='*80}\n\n")
            for f, _bn, size, matches in sorted(items, key=lambda x: -x[2]):
                report.write(f"  {f.name:<55} {size/1024/1024:>8.1f} MB\n")
                for m_path, m_size in matches[:2]:
                    report.write(f"    -> {m_path:<50} {m_size/1024/1024:>8.1f} MB\n")
                if len(matches) > 2:
                    report.write(f"    ... +{len(matches)-2} more copies\n")
                report.write("\n")

        report.write(f"{'='*80}\n")
        report.write(f"ORPHAN ({len(orphans):,} files, {orphan_size/1024**3:.1f} GB)\n")
        report.write(f"{'='*80}\n\n")
        for f, _bn, size in sorted(orphans, key=lambda x: -x[2]):
            report.write(f"  {f.name:<55} {size/1024/1024:>8.1f} MB\n")

    print(f"\nReport written to: {args.output}")
    print(f"  SAFE_DELETE: {len(safe_delete):,} files ({safe_size/1024**3:.1f} GB)")
    print(f"  REVIEW:      {len(review):,} files ({review_size/1024**3:.1f} GB)")
    print(f"  ORPHAN:      {len(orphans):,} files ({orphan_size/1024**3:.1f} GB)")


if __name__ == "__main__":
    main()
