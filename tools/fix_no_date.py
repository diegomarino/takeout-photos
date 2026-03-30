#!/usr/bin/env python3
"""Move no_date files to correct YYYY/YYYY_MM folders by reading EXIF dates.

Reads DateTimeOriginal/CreateDate from each file in no_date/, falls back to
filename date patterns. Moves files to the correct dated folder.

Usage:
    python tools/fix_no_date.py --workdir /path/to/workdir
    python tools/fix_no_date.py --workdir /path/to/workdir --organized-dir /custom/output
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DATE_PATTERN = re.compile(r"(20\d{2})[_-]?(\d{2})[_-]?(\d{2})")


def get_date(filepath: Path) -> str | None:
    """Try DateTimeOriginal, CreateDate, then filename pattern."""
    result = subprocess.run(
        ["exiftool", "-DateTimeOriginal", "-CreateDate", "-s3", str(filepath)],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.strip().split("\n"):
        date_str = line.strip()
        if date_str and date_str != "0000:00:00 00:00:00":
            return date_str

    m = DATE_PATTERN.search(filepath.name)
    if m:
        return f"{m.group(1)}:{m.group(2)}:{m.group(3)} 00:00:00"

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workdir", type=Path, required=True, help="Pipeline working directory")
    parser.add_argument("--organized-dir", type=Path, help="Override organized media directory")
    args = parser.parse_args()

    organized = args.organized_dir or args.workdir / "organized_media"
    no_date = organized / "no_date"

    if not no_date.exists():
        print(f"No no_date/ directory found at {no_date}")
        sys.exit(0)

    files = [
        f
        for f in no_date.rglob("*")
        if f.is_file() and not f.name.startswith("._") and f.suffix != ".json"
    ]
    total = len(files)
    print(f"Total no_date files to process: {total:,}")
    sys.stdout.flush()

    if total == 0:
        print("Nothing to do.")
        return

    moved = 0
    no_date_found = 0
    errors = 0

    for i, f in enumerate(files):
        try:
            date_str = get_date(f)
            if not date_str:
                no_date_found += 1
            else:
                year = date_str[:4]
                month = date_str[5:7]

                dest_dir = organized / year / f"{year}_{month}"
                dest_dir.mkdir(parents=True, exist_ok=True)

                dest = dest_dir / f.name
                counter = 1
                while dest.exists():
                    dest = dest_dir / f"{f.stem}({counter}){f.suffix}"
                    counter += 1

                f.rename(dest)
                moved += 1

        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"ERROR: {f.name}: {e}")
                sys.stdout.flush()

        if (i + 1) % 200 == 0:
            pct = (i + 1) * 100 // total
            print(
                f"[{i+1:,}/{total:,}] {pct}% — moved: {moved:,}, no date: {no_date_found:,}, errors: {errors:,}"
            )
            sys.stdout.flush()

    print(f"\n{'='*60}")
    print("DONE")
    print(f"  Moved:         {moved:,}")
    print(f"  No date found: {no_date_found:,}")
    print(f"  Errors:        {errors:,}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
