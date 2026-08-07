# Takeout Photos API Reference

**Last Updated:** 2026-01-29

This document describes the public API of the `takeout_photos` package.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core API](#core-api)
  - [Config](#config)
  - [PipelineDB](#pipelinedb)
  - [Pipeline](#pipeline)
- [Takeout Module](#takeout-module)
  - [JSON Parser](#json-parser)
  - [JSON Finder](#json-finder)
- [EXIF Module](#exif-module)
- [Hashing Module](#hashing-module)
- [Stages Module](#stages-module)
- [CLI Module](#cli-module)
- [Utilities](#utilities)

---

## Installation

**macOS (Apple Silicon) via Homebrew:**

```bash
brew tap diegomarino/tap
brew install takeout-photos
```

**Via PyPI (all platforms):**

```bash
# Basic installation
pip install takeout-photos

# With performance optimizations (recommended)
pip install takeout-photos[fast]

# For development
pip install takeout-photos[dev]
```

## Quick Start

### As a CLI Tool

```bash
# Process all ZIPs in workdir
takeout-photos --workdir ~/google_takeout_work process

# Check status
takeout-photos --workdir ~/google_takeout_work status

# Reset a ZIP with errors
takeout-photos --workdir ~/google_takeout_work reset --zip takeout-001.zip
```

### As a Library

```python
from takeout_photos import Config, Pipeline

# Configure pipeline
config = Config(
    workdir="/path/to/work",
    workers=8,
    organize_layout="yyyy_mm"
)

# Run complete pipeline
pipeline = Pipeline(config)
pipeline.run()
```

---

## Core API

The core module provides the main building blocks for the pipeline.

### Config

**Module:** `takeout_photos.core.config`

Configuration dataclass for the pipeline. All paths and processing options are defined here.

**Example:**

```python
from pathlib import Path
from takeout_photos.core.config import Config

config = Config(
    workdir=Path("/path/to/work"),
    workers=4,
    batch_size=500,
    organize_layout="yyyy_mm",  # or "yyyy"
    qc_min_year=1995,
    qc_max_year=2030,
    dry_run=False,
    verbose=False
)
```

**Attributes:**

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `workdir` | `Path` | **required** | Base working directory |
| `zips_dir` | `Path` | `workdir` | Directory containing input ZIP files |
| `extracted_dir` | `Path` | `workdir/extracted` | Temporary extraction directory |
| `duplicates_dir` | `Path` | `workdir/duplicates` | Duplicates moved here |
| `final_dir` | `Path` | `workdir/organized_media` | Final organized output |
| `organized_dir` | `Path` | `workdir/organized_media` | Effective output directory (alias of final_dir, can be overridden) |
| `logs_dir` | `Path` | `workdir/logs` | Log files and QC reports |
| `db_path` | `Path` | `workdir/pipeline.db` | SQLite database |
| `workers` | `int` | `4` | Number of parallel workers |
| `batch_size` | `int` | `500` | Batch size for bulk operations |
| `checkpoint_interval` | `int` | `100` | Commit database every N files/hashes |
| `organize_layout` | `str` | `"yyyy_mm"` | Layout: `"yyyy_mm"` or `"yyyy"` |
| `qc_min_year` | `int` | `1995` | Minimum valid year for QC |
| `qc_max_year` | `int` | `2030` | Maximum valid year for QC |
| `dry_run` | `bool` | `False` | Simulate without changes |
| `verbose` | `bool` | `False` | Enable verbose logging |
| `delete_zips_after_extract` | `bool` | `False` | Delete ZIPs after successful extraction |
| `keep_extracted_files` | `bool` | `False` | Keep extracted/ after organizing |
| `skip_deps_check` | `bool` | `False` | Skip dependency checks |

---

### PipelineDB

**Module:** `takeout_photos.core.database`

SQLite database for pipeline state management and deduplication.

**Schema:**

The database maintains six main tables:

- **zips**: Tracks processing state of each ZIP file
- **files**: Records every media file with metadata and status
- **json_files**: Fast lookup table for JSON metadata files (indexed)
- **pipeline_state**: Key-value store for global pipeline state
- **organized_files**: Records organized files for deduplication across runs
- **recovery_log**: Audit log for automatic recovery actions

**Key Schema Columns (files table):**

- `status`: File processing state (see File Status Transitions below)
- `staged_path`: Relative path during organize staging (DB-before-move pattern)
- `final_path`: Final relative path in organized_dir after organization
- `error_msg`: Error description for failed files (status='error')
- `exif_datetime`: Capture date used for organizing (cached for performance).
  Populated from JSON `photoTakenTime` when a Takeout sidecar exists, otherwise
  from the file's embedded `DateTimeOriginal` during format validation.
- `content_hash`: File content hash for deduplication

#### Constructor

```python
PipelineDB(db_path: Path)
```

Creates or opens database and initializes schema. Schema creation is idempotent.

**Parameters:**

- `db_path` (Path): Path to SQLite database file (created if doesn't exist)

**Example:**

```python
from pathlib import Path
from takeout_photos.core.database import PipelineDB

db = PipelineDB(Path("/path/to/pipeline.db"))
```

#### ZIP Operations

**register_zip(name: str)**

Register a new ZIP file with initial `'pending'` status.

```python
db.register_zip("takeout-001.zip")
```

**update_zip_status(name: str, status: str, \*\*kwargs)**

Update ZIP status and optional metadata fields. Auto-commits.

Status values: `'pending'`, `'extracting'`, `'extracted'`, `'processing'`, `'organized'`, `'error'`

```python
db.update_zip_status(
    "takeout-001.zip",
    "extracted",
    file_count=1500,
    extracted_at="2024-01-20 10:30"
)
```

**get_zip_status(name: str) -> str | None**

Get current status of a ZIP file. Returns `None` if not registered.

**get_pending_zips() -> list[str]**

Get list of ZIPs needing extraction (status: `'pending'` or `'error'`).

#### File Operations

**register_file(zip_name: str, original_path: str, \*\*kwargs)**

Register a media file in the database. Does not auto-commit (use `commit()` after batch).

Common kwargs: `file_size`, `has_json`, `json_path`, `content_hash`, `status`

```python
db.register_file(
    "takeout-001.zip",
    "/extracted/Takeout/Google Photos/IMG_1234.jpg",
    file_size=1024000,
    has_json=1,
    json_path="/extracted/Takeout/Google Photos/IMG_1234.jpg.json"
)
db.commit()
```

**get_files_for_zip(zip_name: str, status: str | None = None) -> list[dict[str, Any]]**

Retrieve all files from a ZIP, optionally filtered by status.

```python
all_files = db.get_files_for_zip("takeout-001.zip")
meta_files = db.get_files_for_zip("takeout-001.zip", status="meta_applied")
```

**update_file(file_id: int, \*\*kwargs)**

Update file record fields. Does not auto-commit.

Common kwargs: `status`, `content_hash`, `final_path`, `staged_path`, `error_msg`, `exif_datetime`

```python
# Mark file as organized
db.update_file(
    file_id=123,
    status="organized",
    content_hash="abc123def",
    final_path="2020/01/IMG_1234.jpg"
)
db.commit()

# Stage file for organization (DB-before-move pattern)
db.update_file(
    file_id=456,
    status="staged",
    staged_path="2023/05/photo.jpg"
)
db.commit()

# Mark file as error
db.update_file(
    file_id=789,
    status="error",
    error_msg="File not found on filesystem"
)
db.commit()
```

#### JSON Metadata Operations

**register_json_file(zip_name: str, full_path: str)**

Register a JSON metadata file. Automatically derives base media name by removing JSON suffixes. Does not auto-commit.

```python
db.register_json_file(
    "takeout-001.zip",
    "/extracted/Takeout/Google Photos/IMG_1234.HEIC.supplemental-metadata.json"
)
db.commit()
# base_media_name: IMG_1234.HEIC
```

**find_json_for_media_db(media_path: str) -> str | None**

Find JSON file for a media file path using indexed database queries (much faster than filesystem search).

Uses four strategies:

1. Exact match in the same directory (most accurate)
2. Exact match globally (fallback)
3. Numbered suffix search: `(1)`, `(2)`, etc. in same directory
4. Truncated filename search (46+ character filenames) in same directory

```python
json_path = db.find_json_for_media_db("/extracted/Google Photos/IMG_1234.HEIC")
if json_path:
    print(f"Found: {json_path}")
```

#### Hash Operations

**get_all_hashes() -> dict[str, int]**

Get mapping of content hashes to first (lowest) file ID for deduplication.

Returns: `{hash: first_file_id}` dictionary

```python
hashes = db.get_all_hashes()
for hash_val, first_id in hashes.items():
    # Keep file with first_id, mark others as duplicates
```

#### Pipeline State

**get_state(key: str, default=None) -> Any**

Retrieve global pipeline state value.

```python
last_run = db.get_state("last_run_timestamp", default="never")
```

**set_state(key: str, value: str)**

Store global pipeline state value. Auto-commits.

```python
db.set_state("last_run_timestamp", "2024-01-20 14:30")
```

#### Database Lifecycle

**commit()**

Commit pending transactions. Call after batch operations.

Note: `register_zip()`, `update_zip_status()`, and `set_state()` auto-commit. Methods like `register_file()` and `update_file()` do not.

**close()**

Close database connection. Call when done to release resources.

```python
db = PipelineDB(Path("/tmp/pipeline.db"))
try:
    db.register_zip("takeout-001.zip")
    # ... operations ...
finally:
    db.close()
```

---

### Pipeline

**Module:** `takeout_photos.core.pipeline`

Main pipeline orchestrator. Coordinates the merge-extract pipeline, provides resumability, and maintains state in an SQLite database.

The Pipeline class is the primary entry point for using takeout_photos. It can run the complete pipeline or individual phases, and handles all directory creation, database initialization, and logging setup.

#### Constructor

```python
Pipeline(config: Config, verbose: bool | None = None)
```

Initialize pipeline with configuration.

**Parameters:**

- `config` (Config): Pipeline configuration with directories and options
- `verbose` (bool | None): Override `config.verbose` for logging level. If None, uses `config.verbose`

**Side Effects:**

- Creates database if it doesn't exist
- Sets up logging to console and log file
- Creates all work directories

**Example:**

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work", workers=8)
pipeline = Pipeline(config, verbose=True)

# Use pipeline
pipeline.run()

# Clean up when done
pipeline.close()
```

**As Context Manager:**

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work")
with Pipeline(config) as pipeline:
    pipeline.run()
# Database automatically closed
```

---

#### run

```python
def run(self) -> None
```

Execute the complete pipeline from start to finish.

Runs the merge-extract pipeline in sequence:

1. Extract all ZIPs to a shared `extracted/` directory
2. Validate file formats
3. Apply metadata (JSON → EXIF)
4. Compute content hashes
5. Organize files per ZIP with inline deduplication
6. Quality control

**Side Effects:**

- Processes all ZIPs in workdir root directory
- Creates organized photo library in `organized_dir/`
- Generates QC report in `logs/`
- Records completion timestamp in database

**Example:**

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work")
with Pipeline(config) as pipeline:
    pipeline.run()
# Processes complete pipeline
```

**Resumability:**

The pipeline is idempotent and resumable. If interrupted, rerun `run()` to continue from the last checkpoint. Each ZIP's state is saved in the database, allowing partial completion:

```python
# First run (interrupted)
try:
    pipeline.run()
except KeyboardInterrupt:
    print("Interrupted!")

# Resume later - will continue from checkpoint
pipeline2 = Pipeline(config)
pipeline2.run()  # Resumes where it left off
```

**Raises:**

- `Exception`: If any stage fails, the exception is logged and propagated. Rerun to resume from checkpoint.

---

#### extract_all_zips

```python
def extract_all_zips(self) -> None
```

Phase 1: Extract all pending ZIPs and register media files.

Processes all ZIPs with status `'pending'` or `'error'`. Extracts contents to `extracted/` (merge-extract) and registers media files with associated JSON metadata in the database.

**Side Effects:**

- Extracts ZIPs to `extracted/` directory
- Registers JSON files for fast lookup
- Registers media files with metadata in database
- Updates ZIP status to `'extracted'`

**Example:**

```python
pipeline = Pipeline(config)
pipeline.extract_all_zips()
# Extracts all pending ZIPs
```

---

#### validate_formats

```python
def validate_formats(self) -> None
```

Phase 1b: Validate file formats and correct mismatched extensions.

Detects real file types using exiftool and corrects extensions if needed. Google Takeout often exports files with incorrect extensions (.HEIC files that are actually JPEG, etc.).

**Side Effects:**

- May rename files to correct extensions (appending: `IMG_6486.HEIC` → `IMG_6486.HEIC.jpg`)
- Updates file paths in database
- Stores the embedded `DateTimeOriginal` in `files.exif_datetime` **whenever a
  file has one**, regardless of whether its extension was corrected. This is the
  fallback that lets non-Takeout input (loose images with no JSON sidecar) be
  organized by their real capture date instead of landing in `no_date/`.

**Example:**

```python
pipeline = Pipeline(config)
pipeline.extract_all_zips()
pipeline.validate_formats()
# Corrects mismatched extensions and records embedded EXIF dates for files
# that have no JSON sidecar
```

---

#### apply_metadata_phase

```python
def apply_metadata_phase(self) -> None
```

Phase 2: Apply metadata and compute hashes (per ZIP).

For each ZIP in `'extracted'` or `'processing'` state:

1. Apply JSON metadata to EXIF tags (batch operation)
2. Compute content hashes for deduplication (parallel)

**Side Effects:**

- Modifies EXIF data in extracted files (ALWAYS overwrites embedded EXIF dates with JSON metadata)
- Computes and stores content hashes

**Example:**

```python
pipeline = Pipeline(config)
pipeline.extract_all_zips()
pipeline.validate_formats()
pipeline.apply_metadata_phase()
# Processes all extracted ZIPs through metadata pipeline
```

**Note:** Google Takeout is known to export files with incorrect embedded EXIF dates. This function ALWAYS prioritizes JSON photoTakenTime over any embedded EXIF when JSON metadata is available.

---

#### organize

```python
def organize(self) -> None
```

Deprecated in incremental merge-extract mode.

Organization is performed per ZIP via `step_organize_files_from_zip()` inside `Pipeline.run()`.

**Side Effects:**

- None in current flow (deprecated)

**Organization Layouts:**

- **yyyy_mm**: `organized_dir/2023/05/abc123def.jpg`
- **yyyy**: `organized_dir/2023/abc123def.jpg`
- **no_date**: `organized_dir/no_date/abc123def.jpg`

**Example:**

```python
# Prefer pipeline.run(), which handles organization and deduplication
pipeline = Pipeline(config)
pipeline.run()
```

---

#### quality_control

```python
def quality_control(self) -> None
```

Phase 5: Generate quality control report.

Detects and reports potential metadata issues:

- Files without DateTimeOriginal (in `no_date/`)
- Suspiciously old dates (< 1995)
- Future dates
- Suspicious epoch dates (1970-01-01, 2000-01-01)
- Statistics by year

**Side Effects:**

- Creates timestamped QC report in `logs/` directory

**Example:**

```python
pipeline = Pipeline(config)
# After organization...
pipeline.quality_control()
# Generates QC report at logs/qc_*.txt
```

**Use Cases:**

- Identify files needing manual date correction
- Verify pipeline processed files correctly
- Generate statistics for reporting
- Detect metadata corruption or export issues

---

#### close

```python
def close(self) -> None
```

Close database connection and release resources.

Call this when done with the pipeline to properly clean up. Good practice especially in long-running scripts.

**Example:**

```python
pipeline = Pipeline(config)
try:
    pipeline.run()
finally:
    pipeline.close()
```

**Note:** Not needed when using Pipeline as a context manager - cleanup is automatic.

---

### Pipeline Architecture

**Design Principles:**

- **Stateless**: All state stored in database, no in-memory state
- **Phase isolation**: Each phase can run independently
- **ZIP-level checkpointing**: Resume per-ZIP if interrupted
- **Two-phase flow**: Merge-extract all ZIPs, then process per ZIP with inline deduplication
- **Idempotent**: Safe to re-run any phase multiple times

**Pipeline Flow:**

```
Phase 1:  Merge-extract all ZIPs → extracted/
Phase 1b: Validate formats and correct extensions
Phase 2a: Apply JSON metadata to EXIF (per ZIP, batch)
Phase 2b: Compute content hashes (per ZIP, parallel)
Phase 2c: Organize per ZIP with inline deduplication → organized_dir/
Phase 3:  Quality control report → logs/qc_*.txt
```

**State Management:**

The database tracks processing state:

- ZIP status: `pending`, `extracting`, `extracted`, `processing`, `organized`, `error`
- File status: `pending`, `meta_applied`, `staged`, `organized`, `error`
- Global state: `last_complete_run` timestamp

**File Status Transitions:**

```
pending → meta_applied → staged → organized
   ↓           ↓           ↓
error ← ────────────────────
```

- **pending**: File extracted, awaiting metadata application
- **meta_applied**: Metadata written to EXIF, ready for hashing
- **staged**: Database updated with destination path, ready for move (crash-safe checkpoint)
- **organized**: File moved to final location and registered
- **error**: File failed processing (requires manual intervention)

**Example (Recommended):**

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work")
with Pipeline(config) as pipeline:
    pipeline.run()
```

---

## Takeout Module

Google Takeout specific logic for JSON metadata handling.

### JSON Parser

**Module:** `takeout_photos.takeout.json_parser`

Parse Google Takeout JSON metadata files to extract photo timestamps and GPS coordinates.

#### parse_takeout_json

```python
def parse_takeout_json(json_path: Path) -> dict[str, Any]
```

Extract relevant metadata from Google Takeout JSON file.

Parses JSON to extract photo capture timestamp and GPS coordinates. Handles both old and new Google Takeout formats with fallback strategies.

**Parameters:**

- `json_path` (Path): Path to Google Takeout JSON metadata file

**Returns:**

- `dict[str, Any]`: Dictionary with extracted metadata fields:
  - `photo_taken_ts` (int): Unix timestamp of photo capture
  - `geo_lat` (float): GPS latitude coordinate
  - `geo_lon` (float): GPS longitude coordinate

  Returns empty dict if JSON is invalid or missing expected fields.

**Timestamp Sources (priority order):**

1. `photoTakenTime.timestamp` - Primary source for photo capture time
2. `creationTime.timestamp` - Fallback if photoTakenTime not available

**GPS Sources (first available):**

- `geoData.latitude/longitude` - Primary GPS source
- `geoDataExif.latitude/longitude` - EXIF-based GPS data

**Note:** GPS coordinates are only included if non-zero. Google Takeout sometimes includes (0.0, 0.0) as placeholder values which are invalid.

**Example:**

```python
from pathlib import Path
from takeout_photos.takeout.json_parser import parse_takeout_json

json_path = Path("IMG_1234.HEIC.supplemental-metadata.json")
metadata = parse_takeout_json(json_path)

print(metadata)
# {
#     'photo_taken_ts': 1609459200,
#     'geo_lat': 40.4168,
#     'geo_lon': -3.7038
# }
```

**Error Handling:**

Returns empty dict `{}` for:

- Invalid JSON syntax
- File encoding errors (non-UTF-8)
- Missing file
- Missing expected fields

**JSON Structure Examples:**

*Standard format (new exports):*

```json
{
  "photoTakenTime": {
    "timestamp": "1609459200"
  },
  "geoData": {
    "latitude": 40.4168,
    "longitude": -3.7038
  }
}
```

*Legacy format (old exports):*

```json
{
  "creationTime": {
    "timestamp": "1609459200"
  },
  "geoDataExif": {
    "latitude": 51.5074,
    "longitude": -0.1278
  }
}
```

---

### JSON Finder

**Module:** `takeout_photos.takeout.json_finder`

Locate associated JSON metadata files for media files, handling Google Takeout's complex naming patterns.

#### find_json_for_media

```python
def find_json_for_media(
    media_path: Path,
    extracted_base: Path | None = None
) -> Path | None
```

Locate associated JSON metadata file for a media file.

Google Takeout uses several naming patterns for JSON files that have evolved over time and vary by export batch. This function handles all known patterns with a two-phase search strategy.

**Parameters:**

- `media_path` (Path): Path to media file to find JSON for
- `extracted_base` (Path | None): Base directory containing all extracted ZIPs (e.g., `workdir/extracted/`). If provided, enables legacy global JSON search across per-ZIP layouts.

**Returns:**

- `Path | None`: Path to JSON metadata file if found, None otherwise

**JSON Naming Patterns Handled:**

| Pattern | Example | Notes |
|---------|---------|-------|
| Standard | `photo.jpg.json` | Old standard format |
| Supplemental Metadata | `photo.jpg.supplemental-metadata.json` | New format (since Oct 2024) |
| Numbered (before ext) | `photo(1).jpg.json` | Duplicate with number before extension |
| Numbered (after ext) | `photo.jpg(1).json` | Duplicate with number after extension |
| Truncated | `verylongfilen...oto.jpg.json` | 46-character filename limit |

**Search Strategy:**

1. **Local Search (fast path)**: Search in same directory as media file
   - Try all 18 standard patterns (from `core.constants.JSON_PATTERNS`)
   - Try numbered suffixes (1-9) with all patterns
   - Try truncated filename matching for names > 46 chars

2. **Global Search (if enabled)**: Search across all extracted ZIPs
   - Pattern: `extracted/*/Takeout/Google Photos/` (legacy per-ZIP layout)
   - Searches recursively in all Google Photos subdirectories
   - Only enabled when `extracted_base` is provided

**Why Google Takeout Has Inconsistent Naming:**

- 46-character filename limit causing truncation
- Different naming patterns for different export batches
- Numbered suffixes for duplicates/multiple uploads
- JSON files may be in a different ZIP than the media file

**Example (local search):**

```python
from pathlib import Path
from takeout_photos.takeout.json_finder import find_json_for_media

media = Path("/extracted/Takeout/Google Photos/IMG_1234.HEIC")
json_path = find_json_for_media(media)

if json_path:
    print(f"Found: {json_path}")
# Found: /extracted/Takeout/Google Photos/IMG_1234.HEIC.supplemental-metadata.json
else:
    print("No JSON found")
```

**Example (global search):**

```python
from pathlib import Path
from takeout_photos.takeout.json_finder import find_json_for_media

# Media in one ZIP, JSON might be in another (legacy per-ZIP layout)
media = Path("/extracted/takeout-001/Takeout/Google Photos/IMG_1234.HEIC")
extracted_base = Path("/workdir/extracted")

# Search across all ZIPs
json_path = find_json_for_media(media, extracted_base)

if json_path:
    print(f"Found in different ZIP: {json_path}")
    # Might find: /extracted/takeout-002/Takeout/Google Photos/IMG_1234.HEIC.json
```

**Performance Considerations:**

- Local search is fast (single directory, ~18 pattern checks)
- Global search can be slow for large collections (recursive search across all ZIPs)
- Use local-only when you know JSON is in same directory
- Use global search only when local search fails

**Edge Cases Handled:**

- Very long filenames (>46 chars) are matched by truncation
- Numbered suffixes up to (9) are checked
- Both old and new Google Takeout formats
- Missing JSON files return None (not an error)
- Non-existent directories are skipped gracefully

---

## EXIF Module

Operations for reading and writing EXIF metadata using exiftool.

**Modules:**

- `takeout_photos.exif.operations` - exiftool wrapper and core EXIF operations
- `takeout_photos.exif.format_detection` - File format detection and extension correction
- `takeout_photos.exif.validation` - EXIF date validation

---

### EXIF Operations

**Module:** `takeout_photos.exif.operations`

Core exiftool operations for reading and writing EXIF metadata.

#### run_exiftool

```python
def run_exiftool(
    args: list[str],
    capture_output: bool = True
) -> subprocess.CompletedProcess
```

Execute exiftool with specified arguments.

Thin wrapper to centralize exiftool invocation for all EXIF operations.

**Parameters:**

- `args` (list[str]): Command-line arguments for exiftool (without 'exiftool' itself)
- `capture_output` (bool): If True, capture stdout/stderr for processing

**Returns:**

- `subprocess.CompletedProcess`: Result with stdout, stderr, and returncode

**Raises:**

- `FileNotFoundError`: If exiftool is not installed or not in PATH

**Example:**

```python
from takeout_photos.exif.operations import run_exiftool

result = run_exiftool(["-FileType", "-s", "-s", "-s", "photo.jpg"])
if result.returncode == 0:
    print(f"File type: {result.stdout.strip()}")
```

**Note:** exiftool must be installed and available in PATH. Use `check_dependencies()` from `utils.dependencies` to verify.

#### ts_to_exif_date

```python
def ts_to_exif_date(timestamp: int) -> str
```

Convert Unix timestamp to EXIF datetime format.

EXIF datetime format is: `YYYY:MM:DD HH:MM:SS` (with colons as separators)

**Parameters:**

- `timestamp` (int): Unix timestamp (seconds since epoch, 1970-01-01 00:00:00 UTC)

**Returns:**

- `str`: EXIF-formatted datetime string

**Example:**

```python
from takeout_photos.exif.operations import ts_to_exif_date

ts_to_exif_date(1609459200)
# '2021:01:01 00:00:00'
```

**Note:** Uses local timezone of the system. Google Takeout JSON metadata contains timestamps in UTC, but EXIF dates are typically stored without timezone information.

#### get_file_type_and_exif

```python
def get_file_type_and_exif(file_path: Path) -> tuple[str | None, dict[str, Any]]
```

Get both file type and existing EXIF metadata in a single exiftool call.

Optimized operation that combines file type detection and EXIF reading, avoiding multiple exiftool invocations.

**Parameters:**

- `file_path` (Path): Path to file

**Returns:**

- `tuple[str | None, dict[str, Any]]`: (file_type, exif_dict)
  - `file_type`: File type string ("JPEG", "HEIC", etc.) or None
  - `exif_dict`: Dictionary with EXIF data or empty dict

**EXIF Fields Extracted:**

- DateTimeOriginal: Original capture date/time
- CreateDate: File creation date
- GPSLatitude: GPS latitude coordinate
- GPSLongitude: GPS longitude coordinate

**Example:**

```python
from pathlib import Path
from takeout_photos.exif.operations import get_file_type_and_exif

file_type, exif = get_file_type_and_exif(Path("photo.jpg"))
print(f"Type: {file_type}")
# Type: JPEG
print(f"Date: {exif.get('DateTimeOriginal', 'N/A')}")
# Date: 2021:01:01 12:30:45
```

**Note:** This combines file format detection and EXIF metadata reading into a single operation:

1. Detecting actual file format (for extension correction)
2. Reading existing EXIF metadata (to preserve it during operations)

---

### Format Detection

**Module:** `takeout_photos.exif.format_detection`

File format detection and extension correction for Google Takeout exports.

#### correct_file_extension_fast

```python
def correct_file_extension_fast(
    file_path: Path,
    real_type: str,
    existing_exif: dict[str, Any],
    log: logging.Logger
) -> Path
```

Correct file extension if it doesn't match the real file type (optimized version).

Fast version that receives existing_exif as a parameter instead of reading it again, avoiding a duplicate exiftool call. Use with `get_file_type_and_exif()`.

**Parameters:**

- `file_path` (Path): Path to file with potentially incorrect extension
- `real_type` (str): Real file type (e.g., "JPEG", "MP4", "HEIC")
- `existing_exif` (dict): EXIF data already read from the file
- `log` (logging.Logger): Logger instance for debug/error messages

**Returns:**

- `Path`: Path to corrected file (or original if no correction needed)

**Extension Mapping:**

- JPEG → .jpg (not .jpeg for consistency)
- Other types → lowercase of type name (e.g., HEIC → .heic)

**Example:**

```python
import logging
from pathlib import Path
from takeout_photos.exif.operations import get_file_type_and_exif
from takeout_photos.exif.format_detection import correct_file_extension_fast

log = logging.getLogger(__name__)
file_path = Path("photo.HEIC")

# Get file type and EXIF in one call
file_type, exif_data = get_file_type_and_exif(file_path)

# Correct extension if needed
if file_type:
    corrected = correct_file_extension_fast(file_path, file_type, exif_data, log)
    print(corrected)
    # photo.HEIC.jpg (if real type was JPEG)
```

**Note:**

- We don't use exiftool -o because it can't change file formats
- The file already has its EXIF embedded, we just need to fix the extension
- Extensions are always lowercase for consistency across platforms
- The original extension is preserved by appending: IMG_6486.HEIC → IMG_6486.HEIC.jpg

---

### Date Validation

**Module:** `takeout_photos.exif.validation`

EXIF metadata validation.

#### is_suspicious_date

```python
def is_suspicious_date(exif_date: str) -> bool
```

Check if an EXIF date is suspicious or likely incorrect.

EXIF dates in Google Takeout exports are often incorrect or use placeholder values. This function identifies common problematic date patterns.

**Parameters:**

- `exif_date` (str): EXIF date string in format "YYYY:MM:DD HH:MM:SS"

**Returns:**

- `bool`: True if date is suspicious and should not be trusted, False otherwise

**Suspicious Date Patterns:**

| Pattern | Example | Reason |
|---------|---------|--------|
| Unix epoch | 1970:01:01 | Default for uninitialized timestamps |
| Y2K default | 2000:01:01 | Common camera default (dead CMOS battery) |
| Before 1995 | 1990:06:15 | Before widespread consumer digital photography |
| Future dates | 2030:01:01 | Likely incorrect clock settings or timezone issues |

**Example:**

```python
from takeout_photos.exif.validation import is_suspicious_date

is_suspicious_date("1970:01:01 00:00:00")
# True
is_suspicious_date("2000:01:01 00:00:00")
# True
is_suspicious_date("2021:06:15 14:30:00")
# False
is_suspicious_date("invalid date")
# True
```

**Note:** Empty strings and unparseable dates are considered suspicious. This is a conservative approach - when in doubt, treat as suspicious and prefer JSON metadata from Google Takeout.

**Why These Dates Are Suspicious:**

- **1970:01:01**: Unix epoch (timestamp 0), used when date is unknown
- **2000:01:01**: Common default in cameras with dead CMOS battery
- **< 1995**: Before widespread consumer digital photography
- **Future dates**: Likely incorrect clock settings or timezone issues

---

## Hashing Module

Content-based file hashing for deduplication.

**Module:** `takeout_photos.hashing.hasher`

Provides fast content hashing using xxhash (if available) or SHA256 fallback for identifying duplicate media files based on content.

---

### compute_hash

```python
def compute_hash(filepath: Path) -> str
```

Compute content hash of a file for deduplication.

Uses xxhash if available (2-3x faster than SHA256) or SHA256 as fallback. The hash is computed from file content only, not filename or metadata. This enables detection of identical files across different ZIPs even if they have different names or paths.

**Parameters:**

- `filepath` (Path): Path to file to hash

**Returns:**

- `str`: Hex digest of file content hash (16-character xxhash or 64-character SHA256 string)

**Raises:**

- `FileNotFoundError`: If file does not exist
- `PermissionError`: If file cannot be read
- `IOError`: If file reading fails

**Hash Algorithm Selection:**

| Algorithm | Availability | Speed | Digest Length | Use Case |
|-----------|-------------|-------|---------------|----------|
| xxhash (xxh64) | If `xxhash` package installed | 2-3x faster | 16 chars | Preferred for large collections |
| SHA256 | Always (stdlib) | Baseline | 64 chars | Fallback when xxhash unavailable |

**Performance:**

- Reads file in 64KB chunks to handle large files efficiently
- Memory usage is constant (64KB) regardless of file size
- For 1GB file: ~2 seconds with xxhash, ~5 seconds with SHA256

**Example (Basic Usage):**

```python
from pathlib import Path
from takeout_photos.hashing.hasher import compute_hash

file1 = Path("photo1.jpg")
file2 = Path("photo2.jpg")  # Identical content, different name

hash1 = compute_hash(file1)
hash2 = compute_hash(file2)

if hash1 == hash2:
    print("Files are identical")
```

**Example (Deduplication Workflow):**

```python
from collections import defaultdict
from pathlib import Path
from takeout_photos.hashing.hasher import compute_hash

# Group files by content hash
hash_to_files = defaultdict(list)
for file in Path("/photos").glob("**/*"):
    if file.is_file():
        h = compute_hash(file)
        hash_to_files[h].append(file)

# Find duplicates
for hash_val, files in hash_to_files.items():
    if len(files) > 1:
        print(f"Duplicates ({len(files)}): {files}")
        # Keep first file, mark others as duplicates
```

**Content-Only Hashing:**

The hash is based on file content only. Identical files will have the same hash even if they have:

- Different filenames
- Different paths
- Different file extensions
- Different EXIF metadata
- Different modification timestamps

However, files with even a single byte difference will have different hashes (including EXIF changes).

**Example (Hash Stability):**

```python
from pathlib import Path
from takeout_photos.hashing.hasher import compute_hash

original = Path("photo.jpg")
hash1 = compute_hash(original)

# Rename file
renamed = Path("different_name.jpg")
original.rename(renamed)

hash2 = compute_hash(renamed)

assert hash1 == hash2  # Hash is unchanged
```

**Algorithm Details:**

*xxhash (when available):*

- Non-cryptographic hash designed for speed
- Excellent collision resistance for file deduplication
- 16-character hex digest (64-bit hash)
- Install with: `pip install xxhash` or `pip install takeout-photos[fast]`

*SHA256 (fallback):*

- Cryptographically secure (though not required for deduplication)
- 64-character hex digest (256-bit hash)
- Universal availability in Python standard library
- No additional installation required

**Note:** For best performance with large photo collections, install xxhash:

```bash
pip install takeout-photos[fast]
```

---

## Stages Module

The pipeline is implemented as stage functions in `takeout_photos.stages.*`.
In the current merge-extract design, the stages are orchestrated by `Pipeline.run()`.

**Stage Architecture (current):**

Most stage functions follow this pattern:

```python
def step_X(config: Config, db: PipelineDB, [zip_name|zip_path], log: logging.Logger) -> None
```

Design goals:

- **Stateless**: No shared state except database
- **Idempotent**: Safe to re-run
- **Atomic**: Commits happen at stage boundaries

---

### Phase 1: ZIP Extraction

**Module:** `takeout_photos.stages.extract`

Extract ZIP files and register media files with associated JSON metadata.

#### step_extract_zip

```python
def step_extract_zip(
    config: Config,
    db: PipelineDB,
    zip_path: Path,
    log: logging.Logger
) -> None
```

Extract a ZIP file and register all media files in the database.

**Parameters:**

- `config` (Config): Pipeline configuration
- `db` (PipelineDB): Database connection
- `zip_path` (Path): Path to ZIP file to extract
- `log` (logging.Logger): Logger instance

**Side Effects:**

- Extracts ZIP contents to the shared `extracted/` directory (merge-extract)
- Registers JSON metadata files for fast lookup
- Registers media files with associated JSON metadata
- Updates ZIP status: `pending` → `extracting` → `extracted`

**Process:**

1. Extract all contents to `extracted/` (shared)
2. Register JSON files in database (indexed for fast lookups)
3. Register media files with metadata from associated JSON
4. Update ZIP status to `extracted` with file count

**Example:**

```python
from pathlib import Path
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.extract import step_extract_zip
import logging

config = Config(workdir="/path/to/work")
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

zip_file = config.zips_dir / "takeout-001.zip"
step_extract_zip(config, db, zip_file, log)
# Extracts and registers 1234 media files
```

**Security Features:**

- **Path Traversal Protection**: Validates all ZIP member paths to prevent Zip Slip attacks
- Rejects paths containing `../` or absolute paths that could write outside extraction directory
- Logs security warnings for any rejected paths

**Collision Handling:**

- **Same path + same content**: Skip extraction (idempotent, logs info)
- **Same path + different content**: Rename new file with `_conflict_N` suffix (logs warning)
- Prevents data loss when different ZIPs contain files with identical relative paths but different content
- Example: If ZIP1 has `photos/img.jpg` (content A) and ZIP2 has `photos/img.jpg` (content B), result is `photos/img.jpg` (content A) + `photos/img_conflict_1.jpg` (content B)

**Performance:**

- Uses database-based JSON lookup (much faster than filesystem search)
- Skips already-extracted files (idempotent)
- Typical: 2-5 minutes per 1GB ZIP on SSD

---

### Phase 1b: Format Validation

**Module:** `takeout_photos.stages.validate`

Validate file formats and correct mismatched extensions using parallel workers.

#### step_validate_formats

```python
def step_validate_formats(
    config: Config,
    db: PipelineDB,
    zip_name: str,
    log: logging.Logger
) -> None
```

Validate file formats and correct extensions if needed, preserving EXIF metadata.

Google Takeout exports often have incorrect file extensions (.HEIC files that are actually JPEG, etc.). This stage detects the real file type and corrects extensions using parallel workers for I/O-bound exiftool operations.

**Parameters:**

- `config` (Config): Pipeline configuration (uses `config.workers` for parallelization)
- `db` (PipelineDB): Database connection
- `zip_name` (str): Name of ZIP being processed
- `log` (logging.Logger): Logger instance

**Side Effects:**

- May rename files to correct extensions (appending, not replacing)
- Updates `original_path` in database if files are renamed
- Stores the embedded `DateTimeOriginal` in `files.exif_datetime` whenever
  present, independent of whether a rename happened

**Process:**

1. Dispatch validation tasks to worker pool (ProcessPoolExecutor)
2. Workers detect real file type using exiftool (parallel I/O-bound operations)
3. Workers read existing EXIF metadata in the same call
4. Main thread receives results and renames files if needed: `IMG_6486.HEIC` → `IMG_6486.HEIC.jpg`
5. Update database with corrected paths
6. Store the embedded EXIF datetime whenever present (every file, not only
   renamed ones)

**Embedded-EXIF fallback (non-Takeout input):**

Most files already have the correct extension, so no rename occurs. This stage
still records their embedded `DateTimeOriginal`, which is what allows files with
**no** Google Takeout JSON sidecar to be organized by date. Later,
`step_apply_metadata` overwrites `exif_datetime` from JSON `photoTakenTime` when
a sidecar exists, but leaves the embedded value untouched when it does not — so
the date priority is: JSON `photoTakenTime` → embedded `DateTimeOriginal` →
`no_date/`.

**Common Corrections:**

- `.HEIC` → `.jpg` (HEIC files that are actually JPEG)
- `.PNG` → `.jpg` (PNG files that are actually JPEG)
- Various format mismatches from Google Takeout

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.validate import step_validate_formats
import logging

config = Config(workdir="/path/to/work", workers=4)
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

step_validate_formats(config, db, "takeout-001.zip", log)
# Corrects 15 mismatched extensions using 4 parallel workers
```

**Optimizations:**

- Uses `get_file_type_and_exif()` to detect format and read EXIF in one call (50% faster than separate operations)
- Parallelizes exiftool calls using ProcessPoolExecutor for 3-4x speedup on I/O-bound operations
- Main thread handles file renaming to avoid race conditions
- Worker pool size configurable via `config.workers`

---

### Phase 2a: Metadata Application

**Module:** `takeout_photos.stages.metadata`

Apply JSON metadata to EXIF tags using batch exiftool operations.

#### step_apply_metadata

```python
def step_apply_metadata(
    config: Config,
    db: PipelineDB,
    zip_name: str,
    log: logging.Logger
) -> None
```

Apply metadata from JSON files to photo EXIF tags using exiftool batch mode.

**Parameters:**

- `config` (Config): Pipeline configuration
- `db` (PipelineDB): Database connection
- `zip_name` (str): Name of ZIP being processed
- `log` (logging.Logger): Logger instance

**Side Effects:**

- Modifies EXIF data in extracted files (ALWAYS overwrites embedded EXIF dates)
- Updates file status to `meta_applied`

**Process:**

1. Retrieve all pending files for this ZIP
2. Generate exiftool arguments file for batch processing
3. Set `DateTimeOriginal` and `CreateDate` from JSON `photoTakenTime`
4. Set GPS coordinates from JSON `geoData`
5. Execute exiftool once for all files (batch mode)
6. Mark files as `meta_applied`

**Metadata Applied:**

- **DateTimeOriginal** and **CreateDate**: From JSON `photoTakenTime.timestamp`
- **GPSLatitude**, **GPSLongitude**: From JSON `geoData`
- **GPS reference directions**: N/S, E/W based on coordinate signs

**Important Note:**
Google Takeout is known to export files with incorrect embedded EXIF dates. This function ALWAYS prioritizes JSON photoTakenTime over any embedded EXIF when JSON metadata is available, following industry best practices.

Reference: <https://github.com/laurentlbm/google-photos-takeout-date-fixer>

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.metadata import step_apply_metadata
import logging

config = Config(workdir="/path/to/work")
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

step_apply_metadata(config, db, "takeout-001.zip", log)
# Applies metadata to 1234 files
```

**Performance:**

- Uses exiftool's `-@` flag for efficient batch processing
- Much faster than one exiftool process per file
- Typical: 30-60 seconds for 1000 files

---

### Phase 2b: Content Hashing

**Module:** `takeout_photos.stages.hash`

Compute content hashes for deduplication using parallel workers.

#### step_compute_hashes

```python
def step_compute_hashes(
    config: Config,
    db: PipelineDB,
    zip_name: str,
    log: logging.Logger
) -> None
```

Compute content hashes for deduplication using parallel workers.

**Parameters:**

- `config` (Config): Pipeline configuration
- `db` (PipelineDB): Database connection
- `zip_name` (str): Name of ZIP being processed
- `log` (logging.Logger): Logger instance

**Side Effects:**

- Updates `content_hash` field in files table
- Marks files with `status='error'` if hashing fails (file deleted, permission denied, I/O errors)
- Records error messages in database for debugging

**Process:**

1. Identify files without content hashes
2. Compute hash for each file in parallel (using ProcessPoolExecutor)
3. Store hash in database

**Hash Algorithm:**

- xxhash (if available) or SHA256 fallback
- Hash is based purely on file content, not filename or metadata
- Enables detection of identical files across different ZIPs

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.hash import step_compute_hashes
import logging

config = Config(workdir="/path/to/work", workers=8)
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

step_compute_hashes(config, db, "takeout-001.zip", log)
# Computes hashes for 1234 files using 8 parallel workers
```

**Performance:**

- Uses ProcessPoolExecutor for CPU-bound parallel hashing
- For 1000 files @ 2MB each with 8 workers:
  - With xxhash: ~30 seconds
  - With SHA256: ~90 seconds

---

### Deduplication (Inline)

**Module:** `takeout_photos.stages.dedupe`

Deduplication is performed inline during organization using the `organized_files` table.

#### check_if_duplicate

```python
def check_if_duplicate(hash: str, db: PipelineDB) -> bool
```

Returns True if a content hash has already been organized (duplicate), False otherwise.

---

### Organization (Per ZIP, Inline Deduplication)

**Module:** `takeout_photos.stages.organize`

Files are organized per ZIP after hashing. Deduplication is performed inline
using the `organized_files` table.

#### step_organize_files_from_zip

```python
def step_organize_files_from_zip(
    config: Config,
    db: PipelineDB,
    zip_name: str,
    log: logging.Logger
) -> dict[str, int]
```

Organize all hashed files for a given ZIP into `organized_dir/` and move duplicates
to `duplicates/`.

**Parameters:**

- `config` (Config): Pipeline configuration
- `db` (PipelineDB): Database connection
- `zip_name` (str): Name of ZIP being processed
- `log` (logging.Logger): Logger instance

**Returns:**
`{'organized': int, 'duplicates': int, 'errors': int, 'skipped': int}`

- `organized`: Number of files successfully organized
- `duplicates`: Number of duplicate files moved to duplicates/
- `errors`: Number of files that failed to organize
- `skipped`: Number of files already organized (on retry)

**Error Handling:**

- Skips files with `status='organized'` to support retry
- Tracks error count for files that fail to organize
- Marks ZIP as `'error'` if any files fail (records error count in database)
- Marks ZIP as `'organized'` only if all files succeed

**Retry Support:**

- On retry, already-organized files are automatically skipped
- Only failed/unprocessed files are retried
- Prevents moving already-organized files to duplicates/ on subsequent runs
- Enables fixing issues (disk space, permissions, restore deleted files) and retrying

**Organization Layouts:**

- **yyyy_mm**: `organized_dir/2023/05/filename.jpg`
- **yyyy**: `organized_dir/2023/filename.jpg`
- **no_date**: `organized_dir/no_date/filename.jpg`

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.organize import step_organize_files_from_zip
import logging

config = Config(workdir="/path/to/work")
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

stats = step_organize_files_from_zip(config, db, "takeout-001.zip", log)
print(f"Organized: {stats['organized']}, Duplicates: {stats['duplicates']}, Errors: {stats['errors']}")
```

**Note:** `step_organize()` exists for backward compatibility and is deprecated.

---

### Phase 5: Quality Control

**Module:** `takeout_photos.stages.qc`

Generate quality control report identifying potential metadata issues.

#### step_qc

```python
def step_qc(
    config: Config,
    db: PipelineDB,
    log: logging.Logger
) -> None
```

Quality control: detect and report potential issues.

**Parameters:**

- `config` (Config): Pipeline configuration
- `db` (PipelineDB): Database connection
- `log` (logging.Logger): Logger instance

**Side Effects:**

- Creates timestamped QC report in `logs/` directory

**Process:**

1. Find files without DateTimeOriginal (in `no_date/`)
2. Detect suspiciously old dates (< 1995)
3. Detect future dates (> today)
4. Detect suspicious epoch dates (1970-01-01, 2000-01-01)
5. Generate statistics by year
6. Write comprehensive report to `logs/YYYYMMDD_HHMMSS_qc.txt`

**QC Report Contents:**

- Files without DateTimeOriginal (in no_date/)
- Very old dates (< 1995) - may be incorrect
- Future dates - definitely incorrect
- Suspicious dates (1970-01-01, 2000-01-01) - likely default values
- File count statistics by year

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.qc import step_qc
import logging

config = Config(workdir="/path/to/work")
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

step_qc(config, db, log)
# Generates QC report at logs/20240115_143022_qc.txt
```

**Use Cases:**

- Identify files needing manual date correction
- Verify pipeline processed files correctly
- Generate statistics for reporting
- Detect metadata corruption or export issues

---

### Stage Orchestration

**Typical Usage (via Pipeline):**

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work")
pipeline = Pipeline(config)

# Run complete pipeline (all stages in order)
pipeline.run()
```

**Advanced Usage (manual stage control):**

```python
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.stages.extract import step_extract_zip
from takeout_photos.stages.validate import step_validate_formats
from takeout_photos.stages.metadata import step_apply_metadata
from takeout_photos.stages.hash import step_compute_hashes
from takeout_photos.stages.organize import step_organize_files_from_zip, cleanup_extracted_all
import logging

config = Config(workdir="/path/to/work")
db = PipelineDB(config.db_path)
log = logging.getLogger(__name__)

# Phase 1: Extract all ZIPs
for zip_path in config.zips_dir.glob("*.zip"):
    step_extract_zip(config, db, zip_path, log)

# Phase 2: Validate, apply metadata, hash, organize per ZIP
for zip_path in config.zips_dir.glob("*.zip"):
    zip_name = zip_path.stem
    step_validate_formats(config, db, zip_name, log)
    step_apply_metadata(config, db, zip_name, log)
    step_compute_hashes(config, db, zip_name, log)
    step_organize_files_from_zip(config, db, zip_name, log)

# Cleanup extracted/ after all ZIPs processed
cleanup_extracted_all(config, db, log)

db.close()
```

---

## CLI Module

Command-line interface for running the Google Photos Takeout pipeline from the terminal.

**Modules:**

- `takeout_photos.cli.main` - CLI entry point and argument parsing
- `takeout_photos.cli.commands` - Command implementations

The CLI provides three main commands:

- `process` - Run the complete pipeline
- `status` - View current processing state
- `reset` - Reset pipeline state

---

### Entry Point

The CLI can be invoked in two ways:

```bash
# As an installed script
takeout-photos --workdir ~/work process

# As a Python module
python -m takeout_photos --workdir ~/work process
```

---

### Global Options

These options apply to all commands and must be specified before the command name.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--workdir` | Path | **required** | Base working directory (ZIP files should be in this directory) |
| `--workers` | int | `4` | Number of parallel workers for hashing |
| `--dry-run` | flag | `False` | Simulate without making changes (for testing) |
| `--verbose`, `-v` | flag | `False` | Enable verbose debug logging |
| `--layout` | choice | `yyyy_mm` | Organization layout: `yyyy_mm` or `yyyy` |
| `--skip-deps-check` | flag | `False` | Skip dependency verification (advanced users only) |

**Examples:**

```bash
# Use 8 workers for faster processing
takeout-photos --workdir ~/work --workers 8 process

# Enable verbose logging
takeout-photos --workdir ~/work --verbose process

# Organize by year only (not year/month)
takeout-photos --workdir ~/work --layout yyyy process

# Test what would happen without making changes
takeout-photos --workdir ~/work --dry-run process

# Skip dependency check (use only if you know deps are installed)
takeout-photos --workdir ~/work --skip-deps-check process
```

---

### Commands

#### process

```bash
takeout-photos --workdir <path> process
```

Run the complete pipeline from start to finish.

Executes the merge-extract pipeline:

1. Extract all ZIPs to a shared `extracted/` directory
2. Validate file formats
3. Apply metadata (JSON → EXIF)
4. Compute content hashes
5. Organize files per ZIP with inline deduplication
6. Quality control

**What it does:**

- Processes all ZIP files in workdir root directory
- Creates organized photo library in `organized_dir/`
- Generates QC report in `workdir/logs/`
- Updates database with processing state

**Resumability:**
If interrupted (Ctrl+C), the pipeline saves its state. Simply run the command again to resume from the last checkpoint.

**Example:**

```bash
takeout-photos --workdir ~/google_takeout_work process
```

**Output:**

```
Checking dependencies...
============================================================
✓  exiftool: 12.50
✓  Python: 3.11.0
✅ All dependencies satisfied!
============================================================

Phase 1: Merge-Extract...
  takeout-001.zip: Extracting... (1234 files)
  takeout-002.zip: Extracting... (2345 files)

Phase 2: Batch Processing...
  [1/4] Validating formats...
  [2/4] Applying metadata...
  [3/4] Computing hashes...
  [4/4] Organizing files...
  Organized 2890 files, 234 duplicates, 0 errors, 10 skipped

Phase 5: Quality control...
  QC report: logs/qc_20240120_143022.txt

✅ Pipeline complete!
```

---

#### status

```bash
takeout-photos --workdir <path> status
```

Display current pipeline state and statistics.

Shows:

- Processing state of each ZIP file
- File counts by processing status
- Number of duplicates found
- Disk space usage by directory
- Last successful run timestamp

This is a read-only operation, safe to run at any time.

**Example:**

```bash
takeout-photos --workdir ~/google_takeout_work status
```

**Output:**

```
============================================================
PIPELINE STATUS: ~/google_takeout_work
============================================================

ZIPs:
  Name                                     Status          Files
  ---------------------------------------- --------------- ----------
  takeout-001.zip                          organized       1234
  takeout-002.zip                          organized       2345
  takeout-003.zip                          processing      1456
  takeout-004.zip                          pending         -

Files by status:
  organized: 3579
  meta_applied: 1456
  pending: 0

Duplicates found: 0

Last complete run: 2026-01-28 14:30:45

Disk space:
  extracted: 12.34 GB
  final: 8.23 GB
  duplicates: 0.33 GB
```

**Use Cases:**

- Check progress of a long-running pipeline
- Identify which ZIPs failed or are still pending
- Verify disk space usage
- Confirm pipeline completion

---

#### reset

```bash
# Reset a specific ZIP
takeout-photos --workdir <path> reset --zip <zip_name>

# Reset entire pipeline (requires confirmation)
takeout-photos --workdir <path> reset
```

Reset pipeline state for a specific ZIP or entire pipeline.

**For a specific ZIP:**

- Resets status to `'pending'`
- Removes all file records from database
- Deletes `extracted/<zip_stem>/` if it exists

**For full reset:**

- Clears entire database
- Deletes all work directories (`extracted/`, `duplicates/`)
- **Never deletes** `organized_dir/` (final output)
- Requires typing "YES" to confirm (destructive operation)

**Examples:**

```bash
# Reset a ZIP that failed or has errors
takeout-photos --workdir ~/work reset --zip takeout-003.zip

# Reset entire pipeline (requires confirmation)
takeout-photos --workdir ~/work reset
```

**Reset specific ZIP output:**

```
Resetting ZIP: takeout-003.zip
  Deleted: /work/extracted/takeout-003
Reset complete.
```

**Full reset output:**

```
Reset ENTIRE pipeline? (type 'YES' to confirm): YES
Resetting entire pipeline...
  Deleted: /work/extracted
  Deleted: /work/duplicates
Reset complete.
```

**Warning:**
Full reset is destructive and cannot be undone. The `organized_dir/` directory (final output) is never deleted for safety.

---

### Error Handling

The CLI handles errors gracefully:

**Keyboard Interrupt (Ctrl+C):**

```bash
^C
Interrupted by user. Pipeline state saved - run again to resume.
```

Exit code: 130

**Missing Dependencies:**

```bash
Dependency check failed. Please install missing dependencies.
(Use --skip-deps-check to bypass this check at your own risk)
```

Exit code: 1

**General Errors:**

```bash
Error: Failed to extract takeout-001.zip: file is corrupted
```

Exit code: 1

**Verbose Mode:**
With `--verbose`, stack traces are shown for debugging:

```bash
takeout-photos --workdir ~/work --verbose process
# ... error occurs ...
Error: Failed to process
Traceback (most recent call last):
  File "...", line 123, in cmd_process
    ...
```

---

### Command Reference

**Function:** `main() -> None`

**Module:** `takeout_photos.cli.main`

Entry point for the CLI. Parses arguments, validates dependencies, creates configuration, and dispatches to appropriate command handler.

**Exit Codes:**

- `0` - Success
- `1` - Error or missing required arguments
- `2` - Invalid arguments (argparse)
- `130` - Interrupted by user (SIGINT)

---

### Command Functions

**Module:** `takeout_photos.cli.commands`

#### cmd_process

```python
def cmd_process(config: Config) -> None
```

Execute the complete pipeline.

Wraps `Pipeline(config).run()` in a context manager for automatic cleanup.

**Parameters:**

- `config` (Config): Pipeline configuration

**Side Effects:**

- Creates all work directories
- Processes all ZIPs in workdir root
- Generates final organized photo library
- Creates QC report

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.cli.commands import cmd_process

config = Config(workdir="/path/to/work")
cmd_process(config)
# Processes complete pipeline
```

---

#### cmd_status

```python
def cmd_status(config: Config) -> None
```

Display current pipeline state and statistics.

**Parameters:**

- `config` (Config): Pipeline configuration

**Side Effects:**

- Prints status information to console

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.cli.commands import cmd_status

config = Config(workdir="/path/to/work")
cmd_status(config)
# Displays pipeline status
```

---

#### cmd_reset

```python
def cmd_reset(config: Config, zip_name: str | None = None) -> None
```

Reset pipeline state for a specific ZIP or entire pipeline.

**Parameters:**

- `config` (Config): Pipeline configuration
- `zip_name` (str | None): Optional ZIP name to reset. If None, resets entire pipeline (with confirmation).

**Side Effects:**

- Modifies/clears database tables
- Deletes work directories (never deletes `organized_dir/`)

**Example (specific ZIP):**

```python
from takeout_photos.core.config import Config
from takeout_photos.cli.commands import cmd_reset

config = Config(workdir="/path/to/work")
cmd_reset(config, zip_name="takeout-001.zip")
# Resets one ZIP
```

**Example (full reset):**

```python
config = Config(workdir="/path/to/work")
cmd_reset(config)
# Prompts for confirmation: Reset ENTIRE pipeline? (type 'YES' to confirm):
# User types 'YES' → resets everything
```

---

### Integration Examples

**Basic workflow:**

```bash
# 1. Place ZIPs in workdir root
mkdir -p ~/google_takeout_work
mv takeout-*.zip ~/google_takeout_work/

# 2. Run pipeline
takeout-photos --workdir ~/google_takeout_work process

# 3. Check results
takeout-photos --workdir ~/google_takeout_work status

# 4. View organized photos
ls ~/google_takeout_work/organized_media/2023/05/
```

**Advanced workflow with options:**

```bash
# Use 8 workers, organize by year only, enable verbose logging
takeout-photos \
  --workdir ~/google_takeout_work \
  --workers 8 \
  --layout yyyy \
  --verbose \
  process
```

**Recovery from errors:**

```bash
# Pipeline fails on takeout-003.zip
takeout-photos --workdir ~/work process
# Error: Failed to process takeout-003.zip

# Check status to identify issue
takeout-photos --workdir ~/work status
# ZIPs:
#   takeout-003.zip    error    -
#     ERROR: corrupted ZIP file

# Reset the problematic ZIP
takeout-photos --workdir ~/work reset --zip takeout-003.zip

# Fix the ZIP file (re-download or repair)
# ...

# Resume pipeline
takeout-photos --workdir ~/work process
```

---

### Best Practices

1. **Start with status**: Always check status before running process to see current state

2. **Use verbose mode for debugging**: Enable `--verbose` when troubleshooting issues

3. **Test with dry-run**: Use `--dry-run` to preview what would happen before committing changes

4. **Adjust workers**: Match `--workers` to your CPU core count for optimal performance

5. **Check dependencies first**: Let the CLI check dependencies automatically (don't skip unless necessary)

6. **Monitor disk space**: Use `status` command to track disk usage during processing

7. **Reset carefully**: Full pipeline reset is destructive - only use when necessary

8. **Keep organized_dir safe**: The CLI never deletes the final output directory

---

## Utilities

Shared utility functions for logging, progress display, media file detection, and dependency checking.

**Modules:**

- `takeout_photos.utils.logging_setup` - Logging configuration
- `takeout_photos.utils.progress` - Progress bar wrapper and media file detection
- `takeout_photos.utils.dependencies` - Dependency checking
- `takeout_photos.utils.timer` - Elapsed time tracking with intelligent formatting

---

### Logging Setup

**Module:** `takeout_photos.utils.logging_setup`

Configure logging for the pipeline with file and console output.

#### setup_logging

```python
def setup_logging(config: Config) -> logging.Logger
```

Configure logging to both file and console.

Creates a timestamped log file in the logs/ directory and configures console output. Log level is DEBUG if verbose mode is enabled, otherwise INFO.

**Parameters:**

- `config` (Config): Pipeline configuration containing logs_dir and verbose settings

**Returns:**

- `logging.Logger`: Configured logger instance

**Side Effects:**

- Creates logs_dir if it doesn't exist
- Creates timestamped log file: `run_YYYYMMDD_HHMMSS.log`
- Configures root logger with file and console handlers

**Example:**

```python
from takeout_photos.core.config import Config
from takeout_photos.utils.logging_setup import setup_logging

config = Config(workdir="/path/to/work", verbose=True)
log = setup_logging(config)

log.info("Pipeline started")
log.debug("Verbose debug information")
```

**Log Format:**

```
2024-01-20 14:30:45,123 [INFO] Pipeline started
2024-01-20 14:30:45,456 [DEBUG] Processing file: photo.jpg
```

---

### Timer

**Module:** `takeout_photos.utils.timer`

Context manager for measuring elapsed time with intelligent formatting.

#### Timer

```python
class Timer:
    def __init__(self, name: str = "")
    def format_elapsed(self) -> str
```

Context manager that tracks elapsed time and formats it intelligently.

**Parameters:**

- `name` (str, optional): Optional name for debugging (unused in formatting)

**Methods:**

- `format_elapsed()`: Returns formatted elapsed time string omitting zero hours/minutes

**Returns:**

- Formatted time string: "3s", "5m 44s", or "1h 14m 12s"

**Example:**

```python
from takeout_photos.utils.timer import Timer

# Basic usage
with Timer() as t:
    process_files()

print(f"Operation complete ({t.format_elapsed()})")
# Output: Operation complete (5m 44s)

# With name for debugging
with Timer(name="metadata_application") as t:
    apply_metadata_to_files()

print(f"Metadata applied ({t.format_elapsed()})")
# Output: Metadata applied (3m 10s)
```

**Time Format:**

The formatter intelligently omits zero units for compact output:

- Less than 1 minute: "3s"
- 1 minute to 1 hour: "5m 44s"
- 1 hour or more: "1h 14m 12s"

**Usage in Pipeline:**

All pipeline phases and operations use Timer for consistent timing:

```python
from takeout_photos.utils.timer import Timer

# Phase timing
with Timer() as phase_timer:
    extract_all_zips()

log.info(f"=== Phase 1 complete ({phase_timer.format_elapsed()}) ===")

# Operation timing
with Timer() as op_timer:
    validate_formats()

log.info(f"Formats validated: {count:,} corrections ({op_timer.format_elapsed()})")
```

---

### Progress Bar

**Module:** `takeout_photos.utils.progress`

Progress bar wrapper with graceful fallback and media file detection utilities.

#### progress_bar

```python
def progress_bar(
    iterable: Iterable[Any],
    total: int | None = None,
    desc: str | None = None,
    disable: bool = False,
) -> Iterable[Any]
```

Wrapper for tqdm progress bar with graceful fallback.

If tqdm is not installed, returns the plain iterable without progress indication. This allows the code to work with or without the optional tqdm dependency.

**Parameters:**

- `iterable` (Iterable[Any]): Iterable to wrap with progress bar
- `total` (int | None): Total number of items (if not determinable from iterable)
- `desc` (str | None): Description text to show with progress bar
- `disable` (bool): Force disable progress bar even if tqdm is available

**Returns:**

- `Iterable[Any]`: tqdm-wrapped iterable if tqdm is available and not disabled, otherwise returns the plain iterable

**Example:**

```python
from takeout_photos.utils.progress import progress_bar

files = ["file1.jpg", "file2.jpg", "file3.jpg"]
for file in progress_bar(files, desc="Processing"):
    # Process file
    process_file(file)
```

**With total parameter:**

```python
from pathlib import Path
from takeout_photos.utils.progress import progress_bar

files = list(Path("/path/to/photos").glob("*.jpg"))
for file in progress_bar(files, total=len(files), desc="Hashing files"):
    compute_hash(file)
```

**Output (when tqdm is available):**

```
Processing: 100%|████████████████| 3/3 [00:01<00:00,  2.50it/s]
```

#### is_media_file

```python
def is_media_file(path: Path) -> bool
```

Check if a file is a recognized media file (photo or video).

Uses the file extension to determine if the file is a known media type. Case-insensitive comparison against MEDIA_EXTENSIONS from `core.constants`.

**Parameters:**

- `path` (Path): File path to check

**Returns:**

- `bool`: True if file extension matches a known media type, False otherwise

**Supported Extensions:**

- **Photos**: .jpg, .jpeg, .png, .heic, .heif, .tif, .tiff, .gif, .webp, .bmp, .raw, .cr2, .nef, .arw
- **Videos**: .mov, .mp4, .mpg, .avi, .mkv, .m4v, .3gp, .webm

**Example:**

```python
from pathlib import Path
from takeout_photos.utils.progress import is_media_file

# Recognize media files
assert is_media_file(Path("photo.jpg")) is True
assert is_media_file(Path("video.mp4")) is True
assert is_media_file(Path("image.HEIC")) is True  # Case-insensitive

# Reject non-media files
assert is_media_file(Path("document.pdf")) is False
assert is_media_file(Path("metadata.json")) is False
assert is_media_file(Path("archive.zip")) is False
```

**Filtering media files:**

```python
from pathlib import Path
from takeout_photos.utils.progress import is_media_file

directory = Path("/path/to/files")
media_files = [f for f in directory.iterdir() if is_media_file(f)]
print(f"Found {len(media_files)} media files")
```

---

### Dependency Checking

**Module:** `takeout_photos.utils.dependencies`

Verify that all required and optional dependencies are installed.

#### check_dependencies

```python
def check_dependencies(verbose: bool = False) -> bool
```

Check for required and optional dependencies.

Verifies that all necessary tools are installed and provides clear installation instructions for missing dependencies.

**Required Dependencies:**

- Python 3.8+
- exiftool (external binary for EXIF operations)

**Optional Dependencies (for better performance):**

- xxhash (2-3x faster hashing)
- tqdm (progress bars)

**Parameters:**

- `verbose` (bool): If True, show detailed dependency information for all deps, even when satisfied

**Returns:**

- `bool`: True if all required dependencies are available, False otherwise

**Side Effects:**

- Prints dependency status to console
- Shows platform-specific installation instructions for missing dependencies

**Example:**

```python
from takeout_photos.utils.dependencies import check_dependencies

# Check at application startup
if not check_dependencies(verbose=True):
    print("Please install missing dependencies before running the pipeline")
    exit(1)

print("All dependencies satisfied - ready to run!")
```

**Output (all dependencies satisfied):**

```
Checking dependencies...
============================================================
✓  exiftool: 12.50 (/usr/local/bin/exiftool)
✓  Python: 3.11.0

Optional Python packages (for better performance):
------------------------------------------------------------
✓  xxhash: Available (fast hashing enabled)
✓  tqdm: Available (progress bars enabled)

============================================================
✅ All dependencies satisfied!
============================================================
```

**Output (missing exiftool on macOS):**

```
Checking dependencies...
============================================================
✗  exiftool: NOT FOUND (REQUIRED)
   This tool is essential for EXIF metadata operations.

   Install with: brew install exiftool

✓  Python: 3.11.0

Optional Python packages (for better performance):
------------------------------------------------------------
✓  xxhash: Available (fast hashing enabled)
✓  tqdm: Available (progress bars enabled)

============================================================
❌ Missing 1 required dependency/dependencies:
   - exiftool

Please install required dependencies before running the pipeline.
============================================================
```

**Platform-Specific Installation:**

| Platform | Command |
|----------|---------|
| macOS | `brew install exiftool` |
| Debian/Ubuntu | `sudo apt-get install libimage-exiftool-perl` |
| RHEL/Fedora | `sudo yum install perl-Image-ExifTool` |
| Windows | Download from <https://exiftool.org/> |

**Optional Packages:**

```bash
# Install optional performance packages
pip install xxhash tqdm

# Or install with the fast extras group
pip install takeout-photos[fast]
```

---

## Type Definitions

Common type aliases and protocols used throughout the package.

<!-- To be populated as needed -->

---

## Error Handling

### Exceptions

The package uses standard Python exceptions with descriptive messages:

- `zipfile.BadZipFile` - Corrupted ZIP file
- `FileNotFoundError` - Missing file or directory
- `sqlite3.Error` - Database operation errors
- `subprocess.CalledProcessError` - exiftool execution errors

### Error Recovery

The pipeline is designed for full idempotency and automatic crash recovery:

#### Automatic Recovery System

Recovery runs automatically at pipeline startup and reconciles:

1. **Intermediate ZIPs**: Reset stuck states
   - `extracting` → `pending` (re-extract)
   - `processing` → `extracted` (re-process)

2. **Staged Files**: Complete or revert (DB-before-move pattern)
   - File at `staged_path`: Complete staging → `organized`
   - File missing: Revert to `pending` for retry

3. **Orphaned Organized Files**: Register in database
   - Scan `organized/` for unregistered files
   - Compute hash and insert into `organized_files`
   - Update `files` table if matching record exists

4. **Orphaned Extracted Files** (also: "Manual files added to `extracted/`"):
   Register under a reserved synthetic ZIP and queue for processing
   - Scan `extracted/` for unregistered files
   - Register with `zip_name=constants.RECOVERED_ORPHANS_ZIP`
     (`"__recovered_orphans__.zip"`). The `.zip` suffix matters — every
     downstream stage queries via `get_files_for_zip()`, which appends `.zip` —
     and the reserved sentinel name cannot collide with a real Takeout archive
     (ZIP discovery skips + warns if a physical file uses it).
   - Set that row to `status='extracted'` so a subsequent `process` run actually
     validates, hashes, and organizes them (a plain `register_zip()` would leave
     it `pending`, which the batch phase skips)
   - Only **media** files are recovered (mirrors extraction's `is_media_file`
     filter); JSON sidecars, XMP and other files are left untouched in
     `extracted/`
   - **Deferred while any ZIP is pending (re-)extraction.** A crash mid-extraction
     leaves unregistered files that belong to the pending archive; they are
     re-registered (with their JSON) when it re-extracts. Recovering them here
     would double-register the paths and move them before JSON metadata is
     applied, so recovery waits until nothing is pending (it runs every startup)

5. **Missing Files**: Mark as error
   - Sample files table for filesystem mismatches
   - Mark missing files with `status='error'`, `error_msg='File not found'`

#### Fault Tolerance Features

- **ZIP-level checkpoints**: Each ZIP's state is saved in the database
- **File-level retry**: Metadata failures leave files in `pending` state for automatic retry
- **DB-before-move**: Organize stage uses transactional staging to ensure crash-safety
- **Automatic resume**: Restart the pipeline to continue from last checkpoint
- **Error isolation**: A failing ZIP doesn't stop processing of other ZIPs
- **Status tracking**: Use `status` command to identify failed ZIPs
- **Manual reset**: Use `reset --zip` to reprocess a specific failed ZIP

#### Example: Recovery from Crash

```python
from takeout_photos import Config, Pipeline

config = Config(workdir="/path/to/work")
pipeline = Pipeline(config)

try:
    pipeline.run()
except KeyboardInterrupt:
    # Pipeline saves state automatically
    print("Interrupted - state saved")
    print("Run again to resume from checkpoint")

# On next run:
# 1. Recovery system runs automatically
# 2. Staged files are completed or reverted
# 3. Pipeline continues from last checkpoint
pipeline = Pipeline(config)
pipeline.run()  # Resumes seamlessly
```

For detailed recovery behavior, see [Recovery and Retries](recovery-and-retries.md).

---

## Performance Considerations

### Optimization Tips

1. **Use xxhash**: Install `xxhash` for 2-3x faster hashing

   ```bash
   pip install takeout-photos[fast]
   ```

2. **Adjust workers**: Match CPU cores for parallel processing

   ```python
   config = Config(workdir="/path", workers=8)
   ```

3. **SSD storage**: Dramatically faster than HDD for random I/O

4. **Batch size**: Tune for very large collections

   ```python
   config = Config(workdir="/path", batch_size=1000)
   ```

### Performance Characteristics

For a typical 200K photo collection (~50GB) on SSD:

| Phase | Time | Bottleneck |
|-------|------|------------|
| Extraction | 30-60 min | I/O (disk read) |
| Metadata + Hash | 1-2 hours | CPU (hashing) + I/O |
| Deduplication | 10-20 min | I/O (file moves) |
| Organization | 30-60 min | I/O (file moves) |
| **Total** | **2-4 hours** | - |

---

## Extending the Pipeline

### Custom Stages

You can create custom processing stages:

```python
from pathlib import Path
import logging
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB

def my_custom_stage(
    config: Config,
    db: PipelineDB,
    log: logging.Logger
) -> None:
    """Custom processing stage."""
    log.info("Running custom stage...")

    # Get files from database
    files = db.conn.execute("SELECT * FROM files").fetchall()

    # Your custom logic here
    for file in files:
        # Process file
        pass

    db.commit()
    log.info("Custom stage complete")

# Use in pipeline
from takeout_photos import Pipeline

pipeline = Pipeline(config)
pipeline.extract_all_zips()
my_custom_stage(config, pipeline.db, pipeline.log)
# Continue with remaining pipeline stages as needed
```

---

## See Also

- [Architecture Documentation](architecture.md) - Design decisions and module structure
- [Pipeline Flow](pipeline-flow.md) - Visual flowcharts for each stage
- [Migration Guide](migration_guide.md) - Upgrading to latest version
- [README](../README.md) - Getting started and overview

---

**Note:** This API reference is built incrementally. Sections marked with `<!-- PHASE X: To be documented -->` will be completed as each phase is implemented.
