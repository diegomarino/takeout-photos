# Takeout Photos

**A modern Python package for processing Google Photos Takeout exports.**

Transform massive Google Photos Takeout exports into an organized, deduplicated photo library with accurate dates and metadata.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 Key Features

| Feature | Description |
| --- | --- |
| **Resumable Processing** | Database checkpoints per ZIP, automatic resume after failures |
| **Smart Metadata** | Extracts photoTakenTime and GPS from Google Takeout JSON |
| **Batch Operations** | exiftool batch mode (not per-file) for 10x+ speedup |
| **Global Deduplication** | Content-based hashing deduplicates across all ZIPs |
| **Format Detection** | Corrects mismatched extensions (.HEIC files that are actually JPEG) |
| **Quality Control** | Automatic detection of suspicious dates and missing metadata |
| **Flexible Organization** | YYYY/MM or YYYY directory layouts with optional date-prefixed names |

---

## 📦 Installation

### Option 1: macOS Binary (Apple Silicon) — Recommended

**No Python or exiftool installation required!** The binary bundles everything.

#### Via Homebrew (easiest)

```bash
brew tap diegomarino/tap
brew install takeout-photos
takeout-photos --help
```

Homebrew handles updates automatically: `brew upgrade takeout-photos`

#### Via Direct Download

1. Go to [Releases](https://github.com/diegomarino/takeout-photos/releases)
2. Download `takeout-photos-VERSION-macos-arm64.tar.gz`
3. Extract and run:

```bash
tar -xzf takeout-photos-1.0.0-macos-arm64.tar.gz
./takeout-photos --help
```

**⚠️ macOS Security Note:** macOS will block the unsigned binary on first run. See [macOS Binary Issues](docs/TROUBLESHOOTING.md#macos-binary-issues) for simple solutions.

### Option 2: Install from PyPI

**Quick Install:**

```bash
pip install takeout-photos
```

**With Performance Optimizations (Recommended):**

```bash
pip install takeout-photos[fast]
```

Includes:

- **xxhash**: 2-3x faster content hashing
- **tqdm**: Progress bars during processing

### Option 3: From Source (Development)

```bash
git clone https://github.com/diegomarino/takeout-photos.git
cd takeout-photos
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev,fast]"
```

### System Requirements (PyPI Installation)

**Required:**

- Python 3.8 or later
- [exiftool](https://exiftool.org/) for EXIF metadata operations

**Install exiftool:**

```bash
# macOS
brew install exiftool

# Debian/Ubuntu
sudo apt-get install libimage-exiftool-perl

# RHEL/Fedora
sudo yum install perl-Image-ExifTool

# Windows
# Download from https://exiftool.org/
```

---

## 🔄 Interruption and Recovery

The pipeline is **fully idempotent** and can be safely interrupted (Ctrl+C) and resumed:

```bash
# Start processing
takeout-photos --workdir ~/work process

# Press Ctrl+C to interrupt
^C

# Resume processing - continues where it left off
takeout-photos --workdir ~/work process
```

**What happens on resume:**

- ✅ Completed files are skipped automatically
- ✅ Files in progress are retried (metadata, hashing, organization)
- ✅ Database and filesystem are reconciled automatically
- ✅ No duplicates, no lost work

For details, see [Recovery and Retries](docs/recovery-and-retries.md).

---

## 🚀 Quick Start

### 1. Prepare Your Workspace

```bash
mkdir -p ~/google_takeout_work
mv takeout-*.zip ~/google_takeout_work/
```

### 2. Run the Pipeline

```bash
takeout-photos --workdir ~/google_takeout_work process
```

### 3. Access Your Organized Photos

```bash
ls ~/google_takeout_work/organized_media/
# 2019/
# 2020/
# 2021/
# ...
# no_date/
```

---

## 💻 Usage

### As a Command-Line Tool

**Process all ZIPs:**

```bash
takeout-photos --workdir ~/work process
```

**Check status:**

```bash
takeout-photos --workdir ~/work status
```

**Reset a specific ZIP:**

```bash
takeout-photos --workdir ~/work reset --zip takeout-001.zip
```

**Advanced options:**

```bash
takeout-photos \
  --workdir ~/work \
  --workers 8 \
  --layout yyyy \
  --verbose \
  process
```

**Organize with date-prefixed filenames:**

```bash
takeout-photos --workdir ~/work --dated-filenames process
```

This prefixes filenames with their capture date (`2023-05-15_IMG_1234.jpg`) for better chronological sorting. Files without EXIF dates get the `NO-DATE_` prefix.

**Available options:**

- `--doctor`: Run dependency + pipeline health checks
- `--workdir` (required): Base working directory
- `--workers N`: Parallel workers for hashing (default: 4)
- `--dry-run`: Simulate without making changes
- `--verbose`, `-v`: Enable debug logging
- `--dated-filenames`: Prefix filenames with date (YYYY-MM-DD\_) for better sorting
- `--organized-dir`: Custom output directory for organized photos
- `--keep-extracted-files`: Preserve `extracted/` after organizing
- `--delete-zips-after-extract`: ⚠️ Delete ZIPs after successful extraction (saves disk space)
- `--checkpoint-interval`: Commit database every N files/hashes
- `--skip-deps-check`: Skip dependency verification

### As a Python Library

```python
from takeout_photos import Config, Pipeline

# Configure pipeline
config = Config(
    workdir="/path/to/work",
    workers=8,
    dated_filenames=True  # Prefix filenames with YYYY-MM-DD_
)

# Run complete pipeline
with Pipeline(config) as pipeline:
    pipeline.run()

# Or run manual steps for inspection, then resume with run()
pipeline = Pipeline(config)
pipeline.extract_all_zips()
pipeline.validate_formats()
# ...inspect extracted files if needed...
pipeline.run()
```

[→ Full API Documentation](docs/api.md)

---

## 💾 Disk Space Management

### Delete ZIPs After Extraction

**⚠️ DESTRUCTIVE OPERATION** - Use with caution

If you have limited disk space, you can delete original ZIP files immediately after successful extraction:

```bash
takeout-photos --workdir ~/work --delete-zips-after-extract process
```

**How it works:**

- Each ZIP is deleted immediately after successful extraction (progressive)
- Only deleted if extraction succeeds - preserved on errors
- Deletion timestamp recorded in database for audit trail
- Works with `--dry-run` to preview deletions

**When to use:**

- ✅ Limited disk space (< 3x ZIP size available)
- ✅ You have backups of Takeout ZIPs elsewhere
- ✅ Processing incrementally and need space recovery

**When NOT to use:**

- ❌ First time processing (test without flag first)
- ❌ No backup of original Takeout export
- ❌ Disk space is not a constraint

**Example with dry-run:**

```bash
# Preview what would be deleted
takeout-photos --workdir ~/work --delete-zips-after-extract --dry-run process

# Output shows:
# [DRY RUN] Would delete: takeout-001.zip (4.2 GB) after extraction
# [DRY RUN] Would delete: takeout-002.zip (3.8 GB) after extraction

# If comfortable, run for real
takeout-photos --workdir ~/work --delete-zips-after-extract process
```

**Status display:**

Deleted ZIPs are marked with `[DELETED]`:

```text
ZIPs:
  takeout-001.zip    extracted      (12,543 files) [DELETED]
  takeout-002.zip    processing     (8,234 files)
  takeout-003.zip    pending        (0 files)
```

---

## 📁 Directory Structure

```text
~/google_takeout_work/
├── takeout-001.zip         # Place Google Takeout ZIPs in workdir root
├── takeout-002.zip
├── extracted/              # Temporary extraction (merged, auto-deleted after organizing)
├── duplicates/             # Duplicates moved here (safe to delete after verification)
├── organized_media/        # Final organized output
│   ├── 2019/
│   │   ├── 2019_01/
│   │   ├── 2019_02/
│   │   └── ...
│   ├── 2020/
│   └── no_date/           # Files without DateTimeOriginal
├── logs/                   # Run logs and QC reports
└── pipeline.db             # State database
```

---

## ⚙️ Processing Pipeline

The pipeline processes Google Takeout exports in two phases:

**Phase 1: Merge-Extract** — all ZIPs extracted to a shared `extracted/` directory so JSON sidecars from different ZIPs can be matched to their media files.

**Phase 2: Per-ZIP Batch Processing** — each ZIP's files go through:

1. **Validate** — fix mismatched extensions (e.g. `.HEIC` files that are actually JPEG)
2. **Metadata** — parse Google's JSON sidecars and write the real date + GPS into EXIF
3. **Hash** — fingerprint every file with content hashing (xxhash/SHA256)
4. **Organize** — sort into `organized_media/YYYY/YYYY_MM/` with inline deduplication

**Phase 3: Quality Control** — flag suspicious dates and generate a summary report to `logs/qc_*.txt`

[→ Detailed Pipeline Flow Diagrams](docs/pipeline-flow.md)

---

## 🔄 Resumability

The pipeline saves state in `pipeline.db`. If interrupted (Ctrl+C, crash, etc.):

1. Simply run the same command again
2. Pipeline resumes from last checkpoint
3. No duplicate work is performed

**Example recovery:**

```bash
# Pipeline interrupted during processing
^C
Interrupted by user. Pipeline state saved - run again to resume.

# Resume processing
takeout-photos --workdir ~/work process
# Continues from where it left off
```

---

## 📊 Status Command

View detailed processing state:

```bash
takeout-photos --workdir ~/work status
```

**Output:**

```text
============================================================
PIPELINE STATUS: /Users/you/google_takeout_work
============================================================

ZIPs:
  Name                     Status          Files
  ------------------------ --------------- ----------
  takeout-001.zip          organized       1234
  takeout-002.zip          organized       2345
  takeout-003.zip          processing      1456
  takeout-004.zip          pending         -

Files by status:
  organized: 3579
  meta_applied: 1456
  pending: 0

Duplicates found: 234

Last complete run: 2024-01-20 14:30:45

Disk space:
  extracted: 12.34 GB
  organized: 8.23 GB
  duplicates: 0.33 GB
```

---

## 📈 Performance

**For 200K photos (~50GB) on SSD:**

| Phase | Time | CPU/I/O |
| --- | --- | --- |
| Extraction | 30-60 min | I/O bound |
| Metadata + Hash | 1-2 hours | CPU bound |
| Deduplication | 10-20 min | I/O bound |
| Organization | 30-60 min | I/O bound |
| **Total** | **2-4 hours** | --- |

**Optimization tips:**

1. Install xxhash: `pip install takeout-photos[fast]` (2-3x faster hashing)
2. Use SSD storage (10x+ faster than HDD)
3. Adjust `--workers` to match CPU cores
4. Disable antivirus for working directory (temporary)

---

## 🔍 Quality Control

The QC report detects potential metadata issues:

| Issue | Description | Example |
| --- | --- | --- |
| **No Date** | Files without DateTimeOriginal | Moved to `no_date/` |
| **Very Old** | Dates before 1995 | `1980:05:15` (unlikely) |
| **Future Dates** | Dates after today | `2030:01:01` (incorrect clock) |
| **Suspicious** | Epoch/default dates | `1970:01:01`, `2000:01:01` |

QC reports are saved to `logs/YYYYMMDD_HHMMSS_qc.txt`.

---

## 🛡️ Safety Features

1. **Non-Destructive**: Original ZIP files never modified
2. **Duplicates Preserved**: Moved to `duplicates/`, not deleted
3. **Dry Run Mode**: Test with `--dry-run` before committing
4. **Comprehensive Logging**: Every operation logged with timestamps
5. **Database Checkpoints**: Resume from any interruption
6. **Dependency Checking**: Verifies all requirements before starting

---

## 🗂️ Google Takeout JSON Support

The pipeline extracts metadata from Google Takeout JSON files:

**JSON → EXIF mapping:**

```json
{
  "photoTakenTime": {
    "timestamp": "1234567890"    → DateTimeOriginal, CreateDate
  },
  "geoData": {
    "latitude": 40.4168,         → GPSLatitude
    "longitude": -3.7038          → GPSLongitude
  }
}
```

**Supported JSON patterns:**

- `photo.jpg.json` (standard)
- `photo.jpg.supplemental-metadata.json` (new format)
- `photo(1).jpg.json` (numbered duplicates)
- Truncated names (46+ character filenames)
- Global search across multiple ZIPs

**Why JSON metadata is prioritized:**

Google Takeout is known to export files with incorrect embedded EXIF dates. The pipeline ALWAYS prioritizes JSON `photoTakenTime` over embedded EXIF when available, following industry best practices.

Reference: <https://github.com/laurentlbm/google-photos-takeout-date-fixer>

**Fallback for non-Takeout input (no JSON):**

When a file has **no** Google Takeout JSON sidecar — for example, loose images
copied straight into `extracted/`, or any export that omits the `.json` metadata
— the pipeline falls back to the file's own embedded `DateTimeOriginal` EXIF tag.
During format validation the embedded date is read and stored, and organization
then buckets the file into `YYYY/YYYY_MM/` by that date. Only files with **no
JSON date and no readable embedded date** end up in `no_date/`.

In short, the date priority is:

1. JSON `photoTakenTime` (when a sidecar is present) — always wins
2. Embedded EXIF `DateTimeOriginal` (fallback when there is no JSON)
3. `no_date/` (neither available)

---

## Post-Processing Tools

The `tools/` directory contains standalone scripts for post-pipeline analysis and fixes. All require `--workdir` and run from the project root with the virtualenv active.

### Recommended post-processing order

```bash
# 1. Fix files that got wrong dates from cross-folder JSON mismatch
#    (requires extracted/ still present)
python tools/fix_wrong_year.py --workdir ~/work

# 2. Move no_date files to correct folders by reading EXIF dates
python tools/fix_no_date.py --workdir ~/work

# 3. Remove (N) suffix duplicates with identical hashes
python tools/dedup_organized.py --workdir ~/work           # dry-run first
python tools/dedup_organized.py --workdir ~/work --delete

# 4. Analyze remaining no_date files
python tools/analyze_no_date.py --workdir ~/work

# 5. Report cross-folder duplicates by filename + size
python tools/find_cross_dupes.py --workdir ~/work
```

| Tool | Purpose |
| --- | --- |
| `fix_wrong_year.py` | Fix files where JSON metadata came from a different year's folder |
| `fix_no_date.py` | Read EXIF/CreateDate from no_date files and move to correct YYYY/YYYY_MM |
| `dedup_organized.py` | Find/delete `filename(1).ext` duplicates by hash comparison (dry-run by default) |
| `analyze_no_date.py` | Categorize remaining no_date files as SAFE_DELETE, REVIEW, or ORPHAN |
| `find_cross_dupes.py` | Report files with same base name across different folders (0.1% size tolerance) |

### Cleanup

After verifying `organized_media/` is correct:

```bash
# Delete intermediate directories
rm -rf ~/work/extracted
rm -rf ~/work/duplicates
```

---

## 🐛 Troubleshooting

### "exiftool not found"

```bash
# macOS
brew install exiftool

# Verify installation
exiftool -ver
```

### Corrupted ZIP

```bash
# Check which ZIP has errors
takeout-photos --workdir ~/work status

# Reset the problematic ZIP
takeout-photos --workdir ~/work reset --zip takeout-003.zip

# Re-download or repair the ZIP, then retry
takeout-photos --workdir ~/work process
```

### Many files in `no_date/`

**Possible causes:**

1. JSON sidecar not matched (truncated filenames, missing suffix patterns)
2. JSON metadata missing `photoTakenTime`
3. No embedded EXIF dates
4. Cross-folder JSON mismatch applied wrong date

**Solutions:**

1. Run post-processing tools: `python tools/fix_no_date.py --workdir ~/work`
2. Check QC report: `cat logs/qc_*.txt`
3. Analyze remaining: `python tools/analyze_no_date.py --workdir ~/work`
4. Enable verbose mode: `--verbose` to see JSON matching details

### Running out of disk space

**Space requirements:** ~2x the total ZIP size during Phase 1 (all ZIPs extracted), then ~1x for the final organized library.

**Example:** 50GB of ZIPs → need ~100GB free during processing, ~50GB final.

**Large exports (>1TB):** Use `--delete-zips-after-extract` to free space progressively. Each ZIP is deleted after extraction, so you only need space for all extracted files + the remaining ZIPs.

**exFAT volumes:** exFAT uses large cluster sizes (up to 1MB on 4TB drives). Each small file (JSON sidecars, macOS `._` files) wastes nearly 1MB. This can add hundreds of GB of overhead. Consider using APFS/HFS+ or reformatting with smaller cluster sizes. Disable macOS resource forks on external drives:

```bash
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true
```

### Slow processing

**Check:**

1. Is xxhash installed? `pip install xxhash`
2. Using SSD? HDD is 10x+ slower
3. Correct worker count? Try `--workers 8`
4. Antivirus scanning? Temporarily disable for working directory

---

## 📚 Documentation

- **[API Reference](docs/api.md)** - Complete API documentation
- **[Pipeline Flow](docs/pipeline-flow.md)** - Visual flowcharts for each stage
- **[Architecture](docs/architecture.md)** - Design decisions and module structure

---

## 🔬 Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=takeout_photos --cov-report=html

# Run specific test modules
pytest tests/unit/test_database.py -v
pytest tests/integration/test_full_pipeline.py -v
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type checking
mypy src/

# Run pre-commit hooks
pre-commit run --all-files
```

### Building Package

```bash
# Build distribution
python -m build

# Install locally for testing
pip install dist/*.whl

# Verify CLI
takeout-photos --help

# Verify library
python -c "from takeout_photos import Pipeline; print('OK')"
```

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `pytest`
5. Follow code style: `black`, `ruff`, `mypy`
6. Submit a pull request

---

## 📜 License

MIT License - See LICENSE file for details.

---

## 🙏 Acknowledgments

- [exiftool](https://exiftool.org/) by Phil Harvey - The backbone of EXIF operations
- [Google Takeout](https://takeout.google.com/) - For providing photo export capability
- Community contributors and testers

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/diegomarino/takeout-photos/issues)
- **Questions**: [GitHub Discussions](https://github.com/diegomarino/takeout-photos/discussions)
- **Documentation**: [docs/](docs/)
