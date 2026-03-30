#!/usr/bin/env python3
"""Find and delete (N) duplicate files in organized_media/.

Scans for files with (1), (2) etc. suffix, compares hash with the original
file (without suffix), and deletes if identical.

Usage:
    python tools/dedup_organized.py --workdir /path/to/workdir             # dry-run
    python tools/dedup_organized.py --workdir /path/to/workdir --delete    # delete
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

try:
    import xxhash

    USE_XXHASH = True
except ImportError:
    USE_XXHASH = False

DUPE_PATTERN = re.compile(r"^(.+)\((\d+)\)(\.[^.]+)$")


def compute_hash(filepath: Path, chunk_size: int = 65536) -> str:
    h = xxhash.xxh64() if USE_XXHASH else hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workdir", type=Path, required=True, help="Pipeline working directory")
    parser.add_argument("--organized-dir", type=Path, help="Override organized media directory")
    parser.add_argument(
        "--delete", action="store_true", help="Actually delete duplicates (default: dry-run)"
    )
    args = parser.parse_args()

    organized = args.organized_dir or args.workdir / "organized_media"

    print("Scanning for (N) files...")
    sys.stdout.flush()

    candidates = []
    has_original = 0
    total_size = 0

    for f in organized.rglob("*"):
        if f.is_file() and not f.name.startswith("._"):
            m = DUPE_PATTERN.match(f.name)
            if m:
                stem, num, ext = m.groups()
                original = f.parent / f"{stem}{ext}"
                candidates.append((f, original))
                if original.exists():
                    has_original += 1
                    total_size += f.stat().st_size

    total = len(candidates)
    print(f"\n{'='*60}")
    print(f"Candidate (N) files:        {total:,}")
    print(f"  With matching original:   {has_original:,}")
    print(f"  Without original:         {total - has_original:,}")
    print(f"  Potential space savings:   {total_size / 1024**3:.1f} GB (if all are identical)")
    print(f"{'='*60}")

    if not args.delete:
        print("\nDry-run mode. Add --delete to actually remove duplicates.")
        sys.exit(0)

    print("\nComparing hashes...")
    sys.stdout.flush()

    deleted = 0
    deleted_size = 0
    kept = 0
    no_original = 0
    errors = 0

    for i, (dupe, original) in enumerate(candidates):
        try:
            if not original.exists():
                no_original += 1
                continue

            hash_dupe = compute_hash(dupe)
            hash_orig = compute_hash(original)

            if hash_dupe == hash_orig:
                size = dupe.stat().st_size
                dupe.unlink()
                deleted += 1
                deleted_size += size
            else:
                kept += 1

        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"ERROR: {dupe.name}: {e}")
                sys.stdout.flush()

        if (i + 1) % 200 == 0:
            pct = (i + 1) * 100 // total
            print(
                f"[{i+1:,}/{total:,}] {pct}% — deleted: {deleted:,} ({deleted_size/1024**3:.1f} GB),"
                f" kept: {kept:,}, no original: {no_original:,}"
            )
            sys.stdout.flush()

    print(f"\n{'='*60}")
    print("DONE")
    print(f"  Deleted (identical):       {deleted:,} ({deleted_size/1024**3:.1f} GB)")
    print(f"  Kept (different content):  {kept:,}")
    print(f"  No original found:         {no_original:,}")
    print(f"  Errors:                    {errors:,}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
