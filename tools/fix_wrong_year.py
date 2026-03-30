#!/usr/bin/env python3
"""Fix files that got wrong JSON metadata from a different year's folder.

Queries the pipeline DB to find files where the JSON sidecar came from a
different year's folder. Finds the correct JSON in the original extraction
folder, re-applies EXIF, and moves the file to the correct YYYY/YYYY_MM/ folder.
Files without a correct JSON are moved to no_date/.

Requires: extracted/ directory still present (for correct JSON lookup).

Usage:
    python tools/fix_wrong_year.py --workdir /path/to/workdir
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from takeout_photos.core.database import PipelineDB
from takeout_photos.exif.operations import ts_to_exif_date

YEAR_PATTERN = re.compile(r"(?:Photos from )?(\d{4})")
JSON_SUFFIXES = [".supplemental-metadata.json", ".json"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workdir", type=Path, required=True, help="Pipeline working directory")
    parser.add_argument("--organized-dir", type=Path, help="Override organized media directory")
    args = parser.parse_args()

    organized = args.organized_dir or args.workdir / "organized_media"
    db_path = args.workdir / "pipeline.db"

    if not db_path.exists():
        print(f"No pipeline.db found at {db_path}")
        sys.exit(1)

    db = PipelineDB(db_path)

    rows = db.conn.execute("""
        SELECT id, original_path, json_path, exif_datetime, final_path
        FROM files
        WHERE has_json = 1 AND json_path IS NOT NULL AND status = 'organized' AND final_path IS NOT NULL
    """).fetchall()

    # Filter to wrong-year cross-folder matches
    wrong_year = []
    for r in rows:
        orig_folder = Path(r["original_path"]).parent.name
        json_folder = Path(r["json_path"]).parent.name
        if orig_folder == json_folder:
            continue
        m_orig = YEAR_PATTERN.search(orig_folder)
        m_json = YEAR_PATTERN.search(json_folder)
        if m_orig and m_json and m_orig.group(1) != m_json.group(1):
            wrong_year.append(r)

    total = len(wrong_year)
    print(f"Wrong-year files to fix: {total}")
    sys.stdout.flush()

    if total == 0:
        print("Nothing to fix.")
        db.close()
        return

    fixed = 0
    to_no_date = 0
    skipped = 0
    errors = 0

    for r in wrong_year:
        try:
            full_path = organized / r["final_path"]
            if not full_path.exists():
                skipped += 1
                continue

            filename = Path(r["original_path"]).name
            orig_dir = Path(r["original_path"]).parent

            # Find correct JSON
            correct_json = None
            for suffix in JSON_SUFFIXES:
                candidate = orig_dir / (filename + suffix)
                if candidate.exists():
                    correct_json = candidate
                    break

            if not correct_json:
                db_json = db.conn.execute(
                    """
                    SELECT full_path FROM json_files
                    WHERE base_media_name = ? AND full_path LIKE ?
                    LIMIT 1
                """,
                    (filename, f"%{orig_dir.name}%"),
                ).fetchone()
                if db_json and Path(db_json["full_path"]).exists():
                    correct_json = Path(db_json["full_path"])

            if correct_json:
                with open(correct_json) as f:
                    meta = json.load(f)
                correct_ts = meta.get("photoTakenTime", {}).get("timestamp")

                if correct_ts:
                    correct_ts = int(correct_ts)
                    exif_date = ts_to_exif_date(correct_ts)
                    correct_dt = datetime.fromtimestamp(correct_ts)
                    year = str(correct_dt.year)
                    month = f"{correct_dt.month:02d}"

                    subprocess.run(
                        [
                            "exiftool",
                            f"-DateTimeOriginal={exif_date}",
                            f"-CreateDate={exif_date}",
                            "-overwrite_original",
                            "-P",
                            "-ignoreMinorErrors",
                            str(full_path),
                        ],
                        capture_output=True,
                    )

                    dest_dir = organized / year / f"{year}_{month}"
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    dest = dest_dir / full_path.name
                    counter = 1
                    while dest.exists():
                        dest = dest_dir / f"{full_path.stem}({counter}){full_path.suffix}"
                        counter += 1

                    full_path.rename(dest)
                    fixed += 1
                    print(f"  Fixed: {full_path.name} -> {year}/{year}_{month}/")
                    sys.stdout.flush()
                    continue

            # No correct JSON — move to no_date/
            no_date_dir = organized / "no_date"
            no_date_dir.mkdir(parents=True, exist_ok=True)
            dest = no_date_dir / full_path.name
            counter = 1
            while dest.exists():
                dest = no_date_dir / f"{full_path.stem}({counter}){full_path.suffix}"
                counter += 1
            full_path.rename(dest)
            to_no_date += 1
            print(f"  No JSON: {full_path.name} -> no_date/")
            sys.stdout.flush()

        except Exception as e:
            errors += 1
            print(f"  ERROR: {Path(r['original_path']).name}: {e}")
            sys.stdout.flush()

    db.close()

    print(f"\n{'='*60}")
    print("DONE")
    print(f"  Fixed (correct date):   {fixed}")
    print(f"  Moved to no_date/:      {to_no_date}")
    print(f"  Skipped (not on disk):  {skipped}")
    print(f"  Errors:                 {errors}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
