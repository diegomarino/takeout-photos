#!/usr/bin/env python3
"""Find potential cross-folder duplicates by base filename and size.

Strips (N) suffixes and date prefixes to find files that likely represent
the same photo across different folders (e.g. no_date/ vs 2024/).
Only flags groups where file sizes are within 0.1% tolerance.

Output: a parseable log with groups of potential duplicates.

Usage:
    python tools/find_cross_dupes.py --workdir /path/to/workdir
    python tools/find_cross_dupes.py --workdir /path/to/workdir --output /tmp/report.log
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
SIZE_TOLERANCE = 0.001  # 0.1%


def base_name(filename: str) -> str:
    """Normalize filename to base form for comparison."""
    name = filename
    name = DUPE_SUFFIX.sub("", name)
    name = DATE_PREFIX.sub("", name)
    name = NO_DATE_PREFIX.sub("", name)
    return name


def has_similar_sizes(entries: list) -> bool:
    """Check if any pair of entries across different folders have similar sizes."""
    by_folder = defaultdict(list)
    for folder, _name, size, _rel in entries:
        by_folder[folder].append(size)

    if len(by_folder) < 2:
        return False

    all_sizes = [size for _, _, size, _ in entries]
    min_size = min(all_sizes)
    max_size = max(all_sizes)
    if min_size == 0:
        return False
    return bool((max_size - min_size) / max_size <= SIZE_TOLERANCE)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workdir", type=Path, required=True, help="Pipeline working directory")
    parser.add_argument("--organized-dir", type=Path, help="Override organized media directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/cross_dupes_report.log"),
        help="Output report path",
    )
    args = parser.parse_args()

    organized = args.organized_dir or args.workdir / "organized_media"

    print("Scanning organized_media/...")
    sys.stdout.flush()

    index: dict[str, list] = defaultdict(list)
    count = 0

    for f in organized.rglob("*"):
        if f.is_file() and not f.name.startswith("._") and f.suffix != ".json":
            rel = f.relative_to(organized)
            folder = str(rel.parent)
            base = base_name(f.name)
            size = f.stat().st_size
            index[base].append((folder, f.name, size, str(rel)))
            count += 1
            if count % 10000 == 0:
                print(f"  Scanned {count:,} files...")
                sys.stdout.flush()

    print(f"Scanned {count:,} files total")

    cross_dupes = {
        base: entries
        for base, entries in index.items()
        if len({e[0] for e in entries}) > 1 and has_similar_sizes(entries)
    }

    print(f"Found {len(cross_dupes):,} base names with files in multiple folders")

    with open(args.output, "w") as report:
        report.write("# Cross-folder duplicate report\n")
        report.write(f"# {len(cross_dupes):,} groups found\n")
        report.write("#\n")
        report.write("# Format: FOLDER | FILENAME | SIZE_MB | RELATIVE_PATH\n")
        report.write("# Groups separated by blank lines\n\n")

        for base in sorted(cross_dupes, key=lambda b: len(cross_dupes[b]), reverse=True):
            entries = cross_dupes[base]
            report.write(f"## {base} ({len(entries)} copies)\n")
            for folder, name, size, rel_path in sorted(entries, key=lambda e: e[0]):
                size_mb = size / 1024 / 1024
                report.write(f"  {folder:<20} | {name:<50} | {size_mb:>8.1f} MB | {rel_path}\n")
            report.write("\n")

    print(f"\nReport written to: {args.output}")
    print(f"  Total groups:    {len(cross_dupes):,}")

    no_date_groups = sum(
        1 for entries in cross_dupes.values() if any(e[0] == "no_date" for e in entries)
    )
    print(f"  Involving no_date/: {no_date_groups:,}")


if __name__ == "__main__":
    main()
