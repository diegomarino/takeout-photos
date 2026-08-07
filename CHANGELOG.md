# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Fixed

- **Embedded-EXIF fallback for non-Takeout input.** Files that carry a valid
  embedded `DateTimeOriginal` but have no Google Takeout JSON sidecar (e.g. loose
  images dropped into `extracted/`) were all being organized into `no_date/`
  instead of `YYYY/YYYY_MM/`. Format validation already read each file's EXIF
  date but discarded it on the common "extension already correct" code path, and
  only persisted it when a rename happened. `_validate_worker` now returns the
  embedded date on every non-error path, and `step_validate_formats` stores it
  whenever present, independent of any extension correction. Date priority is
  now explicitly: JSON `photoTakenTime` → embedded `DateTimeOriginal` →
  `no_date/`.

- **"Manual files added to `extracted/`" recovery path.** Orphan recovery
  registered manually-added files under a synthetic `zip_name="unknown"` (no
  `.zip` suffix), but every downstream stage queries via `get_files_for_zip()`,
  which appends `.zip` — so the batch stages silently found zero files and never
  processed the orphans. The synthetic zip was also left `status='pending'`,
  which `get_zips_needing_processing()` skips. Recovery now registers the batch
  under a reserved synthetic ZIP name (`__recovered_orphans__.zip`) and sets it
  to `status='extracted'`, so a plain `process` run actually validates, hashes,
  and organizes those files — matching what the docs already claimed happens
  automatically. The reserved name cannot collide with a real Google Takeout
  archive, and ZIP discovery explicitly skips (with a warning) any physical file
  that uses it, so the no-collision guarantee is enforced rather than merely
  assumed. Orphan recovery additionally recovers only media files (leaving JSON
  sidecars and other files untouched) and defers while any ZIP is pending
  (re-)extraction, so partially-extracted files from a crashed run are not
  scooped into the synthetic batch and organized with stale dates ahead of their
  real Takeout JSON.

- **Homebrew/PyInstaller macOS binary crash on `validate`/`hash`.** In a frozen
  build, `sys.executable` is the bundled CLI itself, so `ProcessPoolExecutor`
  worker and resource-tracker subprocesses re-invoked the whole CLI, which then
  rejected the multiprocessing bootstrap arguments (e.g. `tracker_fd=11`) as an
  invalid command and tore down the pool ("A process in the process pool was
  terminated abruptly"). Added `multiprocessing.freeze_support()` as the first
  call in the entry points (`__main__.py`, `cli/main.py`) and listed the
  relevant `multiprocessing`/`concurrent.futures.process` modules as hidden
  imports in `pyinstaller.spec`. Non-frozen (`pip install -e .`) runs are
  unaffected.

### Tests

- Added regression coverage for all three fixes: a real-EXIF/no-JSON fixture
  proving loose images land in `YYYY/YYYY_MM/`, an end-to-end orphan-recovery
  test asserting manually-added files reach `organized_media/` (not merely the
  database), and unit tests asserting `freeze_support()` runs before argument
  parsing at both entry points.

---

## [1.0.0] - 2026-03-07

### Initial Public Release

**A modern Python package for processing Google Photos Takeout exports.**

Transform massive Google Photos Takeout exports into an organized, deduplicated photo library with accurate dates and metadata.

### ✨ Features

#### Core Functionality

- **Incremental ZIP-by-ZIP Processing**: Process each ZIP through all stages before moving to next
  - Extract → Validate → Metadata → Hash → Organize → Cleanup
  - Only 1 ZIP extracted at a time, reducing peak disk usage by 49%
  - Auto-cleanup of `extracted/` after each ZIP

- **Resumable Processing**: Database checkpoints per ZIP, automatic resume after failures

- **Smart Metadata Extraction**: Extracts `photoTakenTime` and GPS from Google Takeout JSON
  - Always prioritizes JSON dates over embedded EXIF
  - Supports multiple JSON patterns and filename variations
  - Global JSON search across multiple ZIPs

- **Content-Based Deduplication**:
  - Cross-run deduplication (automatically deduplicate against all previous runs)
  - O(1) hash lookups using database
  - Duplicates moved to `duplicates/`, not deleted

- **Format Detection & Correction**: Detects real file types using exiftool
  - Corrects mismatched extensions (e.g., `.HEIC` files that are actually JPEG)
  - Preserves existing EXIF metadata

#### Organization & Output

- **Flexible Organization Layouts**:
  - `YYYY/MM` (default) or `YYYY` directory structures
  - Files without dates moved to `no_date/`
  - Original filenames preserved
  - Automatic conflict resolution with `(1)`, `(2)` suffixes

- **Custom Output Directory**: `--organized-dir` flag to specify output location
  - Separate working and final directories
  - Organize directly to external drives

#### Performance & Optimization

- **Batch EXIF Operations**: Uses exiftool batch mode (not per-file) for 10x+ speedup

- **Parallel Hashing**: Multi-core CPU utilization for content hashing
  - xxhash support for 2-3x faster hashing (`pip install takeout-photos[fast]`)
  - Fallback to SHA256 if xxhash not available

- **Disk Space Optimization**:
  - `--delete-zips-after-extract`: Progressive ZIP deletion (optional)
  - `--keep-extracted-files`: Preserve extracted/ for debugging (optional)
  - Peak disk usage: ~2.55TB for 2.5TB of ZIPs (49% reduction from batch processing)

#### Quality Control & Safety

- **Quality Control Reports**: Automatic detection of suspicious dates
  - Files without DateTimeOriginal
  - Dates before 1995 (very old)
  - Future dates
  - Epoch/default dates (1970, 2000)

- **Safety Features**:
  - Non-destructive (original ZIPs never modified unless opted-in)
  - Duplicates preserved in `duplicates/`, not deleted
  - Dry-run mode (`--dry-run`) for safe testing
  - Comprehensive logging with timestamps
  - Dependency verification before starting

#### CLI & Developer Experience

- **Command-Line Interface**:
  - `takeout-photos process` - Process all ZIPs
  - `takeout-photos status` - Check pipeline state
  - `takeout-photos reset --zip NAME` - Reset specific ZIP
  - `takeout-photos doctor` - Diagnostic command
  - `takeout-photos recover` - Recover from interrupted state

- **Library API**: Use as Python library for programmatic control

  ```python
  from takeout_photos import Config, Pipeline

  config = Config(workdir="/path/to/work", workers=8)
  with Pipeline(config) as pipeline:
      pipeline.run()
  ```

- **Comprehensive Documentation**:
  - API reference with examples
  - Pipeline flow diagrams (Mermaid)
  - Architecture documentation
  - Troubleshooting guide

#### Testing & Quality

- **387 Tests**: Comprehensive test suite
  - ~290 unit tests
  - ~97 integration tests
  - 92%+ code coverage

- **Code Quality Tools**:
  - Black formatting (line-length=100)
  - Ruff linting
  - mypy type checking
  - Pre-commit hooks

### 📦 Installation

```bash
# Basic installation
pip install takeout-photos

# With performance optimizations (recommended)
pip install takeout-photos[fast]
```

### 🚀 Quick Start

```bash
# Place Google Takeout ZIPs in a working directory
mkdir -p ~/google_takeout_work
mv takeout-*.zip ~/google_takeout_work/

# Process all ZIPs
takeout-photos --workdir ~/google_takeout_work process

# Check status
takeout-photos --workdir ~/google_takeout_work status

# Access organized photos
ls ~/google_takeout_work/organized_media/
```

### 📊 Performance

For 200K photos (~50GB) on SSD:

- Extraction: 30-60 min
- Metadata + Hash: 1-2 hours
- Deduplication + Organization: 30-60 min
- **Total: 2-3.5 hours**

### 🧹 Disk Space

**Typical scenario (2.5TB of ZIPs):**

- Conservative (keep ZIPs): 5.05 TB
- Aggressive (delete ZIPs): 2.55 TB (49% savings)

### 📜 License

MIT License - See LICENSE file for details.

### 🙏 Acknowledgments

- [exiftool](https://exiftool.org/) by Phil Harvey - The backbone of EXIF operations
- [Google Takeout](https://takeout.google.com/) - For providing photo export capability

---

## Links

- [GitHub Repository](https://github.com/diegomarino/takeout-photos)
- [PyPI Package](https://pypi.org/project/takeout-photos/)
- [Documentation](https://github.com/diegomarino/takeout-photos/tree/main/docs)
- [Issue Tracker](https://github.com/diegomarino/takeout-photos/issues)

---

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.
