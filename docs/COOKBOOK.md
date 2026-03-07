# Takeout Photos Cookbook

Common recipes and workflows for processing Google Photos Takeout exports.

---

## Table of Contents

- [First-Time Setup](#first-time-setup)
- [Processing Your First Takeout](#processing-your-first-takeout)
- [Organizing to External Drive](#organizing-to-external-drive)
- [Incremental Processing](#incremental-processing)
- [Recovery After Interruption](#recovery-after-interruption)
- [Checking Processing Status](#checking-processing-status)
- [Resetting a Corrupted ZIP](#resetting-a-corrupted-zip)
- [Dry-Run Testing](#dry-run-testing)
- [Custom Date Formats](#custom-date-formats)
- [Finding Duplicates](#finding-duplicates)
- [Performance Optimization](#performance-optimization)

---

## First-Time Setup

### Install takeout-photos

**macOS (Apple Silicon) — no Python required:**

```bash
brew tap diegomarino/tap
brew install takeout-photos
```

**All platforms (via PyPI):**

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install takeout-photos[fast]
```

### Install exiftool (Required for PyPI installs)

> **Homebrew users:** Skip this step — the Homebrew binary already bundles exiftool.

**Mac:**

```bash
brew install exiftool
```

**Ubuntu/Debian:**

```bash
sudo apt-get install libimage-exiftool-perl
```

**Windows:**

1. Download from [exiftool.org](https://exiftool.org/)
2. Extract `exiftool.exe` to a directory in your PATH

**Verify installation:**

```bash
exiftool -ver
```

### Prepare Your Workspace

```bash
# Create directories
mkdir -p ~/takeout_work
mkdir -p ~/Pictures/Google\ Photos

# Download your Takeout ZIPs from Google
# Place them directly in ~/takeout_work/
```

---

## Processing Your First Takeout

### Quick Start (CLI)

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos
```

### With Python

```python
from pathlib import Path
from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline

config = Config(
    workdir=Path.home() / "takeout_work",
    organized_dir=Path.home() / "Pictures" / "Google Photos",
    workers=8,
    organize_layout="yyyy_mm",
)

pipeline = Pipeline(config)
pipeline.run()
```

---

## Organizing to External Drive

### Mac/Linux

```bash
# Mount your external drive (e.g., at /Volumes/Photos)
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir /Volumes/Photos/Google\ Photos
```

### Windows

```bash
# External drive mounted as D:
takeout-photos process \
  --workdir C:\Users\YourName\takeout_work \
  --organized-dir D:\Google Photos
```

### With Year-Only Folders

Use `yyyy` layout for simpler organization:

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir /Volumes/Photos/Google\ Photos \
  --layout yyyy
```

**Result:**

```
/Volumes/Photos/Google Photos/
  2022/
    photo1.jpg
    photo2.png
  2023/
    photo3.jpg
```

---

## Incremental Processing

### Adding New Takeout ZIPs

The pipeline automatically skips already-processed ZIPs:

1. Download new Takeout ZIPs from Google
2. Place them in your workdir (same directory where you run the pipeline)
3. Run the pipeline again

```bash
# First batch
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos

# [Time passes, you download more ZIPs]

# Second batch - automatically skips first batch
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos
```

### Check What's Already Processed

```bash
takeout-photos status --workdir ~/takeout_work
```

Or with Python:

```python
from pathlib import Path
from takeout_photos.core.database import PipelineDB

db = PipelineDB(Path.home() / "takeout_work" / "pipeline.db")
rows = db.conn.execute("SELECT name, status FROM zips ORDER BY name").fetchall()
for row in rows:
    print(f"{row['name']}: {row['status']}")
```

---

## Recovery After Interruption

### Automatic Recovery

If the pipeline is interrupted (Ctrl+C, crash, power loss), just run it again:

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos
```

**What happens:**

- Automatically detects incomplete ZIPs
- Cleans up orphaned files
- Resumes from the last completed stage
- No data loss

### Manual Recovery Check

```bash
takeout-photos recovery --workdir ~/takeout_work --dry-run
```

**Sample output:**

```
Recovery Summary (dry-run):
  Intermediate ZIPs:      2
  Orphaned organized:     1
  Orphaned extracted:     0
  Missing files:          0
```

### Force Recovery

```bash
takeout-photos recovery --workdir ~/takeout_work
```

---

## Checking Processing Status

### Quick Status

```bash
takeout-photos status --workdir ~/takeout_work
```

**Output:**

```
Pipeline Status:
  Total ZIPs:       10
  Completed:        8
  In Progress:      1
  Failed:           0
  Pending:          1

Files:
  Total processed:  15,432
  Organized:        14,890
  Duplicates:       542 (3.5%)
```

### Detailed ZIP Status

```python
from pathlib import Path
from takeout_photos.core.database import PipelineDB

db = PipelineDB(Path.home() / "takeout_work" / "pipeline.db")
rows = db.conn.execute(
    "SELECT name, status, file_count FROM zips ORDER BY name"
).fetchall()

print(f"{'ZIP File':<40} {'Status':<12} {'Files'}")
print("-" * 70)

for row in rows:
    zip_name = Path(row["name"]).name
    status = row["status"]
    file_count = row["file_count"] or "-"
    print(f"{zip_name:<40} {status:<12} {file_count}")
```

---

## Resetting a Corrupted ZIP

If a ZIP file is corrupted or you want to reprocess it:

```bash
takeout-photos --workdir ~/takeout_work reset --zip takeout-001.zip
```

**What it does:**

- Resets the ZIP status to "pending"
- Removes associated extracted files
- Clears file records for that ZIP
- Removes extracted files for that ZIP
- Cleans up database records

**Then reprocess:**

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos
```

---

## Dry-Run Testing

### Test Without Making Changes

**CLI:**

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos \
  --dry-run
```

**Python:**

```python
config = Config(
    workdir=Path.home() / "takeout_work",
    organized_dir=Path.home() / "Pictures" / "Google Photos",
    dry_run=True,  # Preview mode
)

pipeline = Pipeline(config)
pipeline.run()
```

**What happens in dry-run (current behavior):**

- Skips destructive operations (file moves, ZIP deletion, EXIF writes)
- Still extracts ZIPs and updates the database
- Useful for verifying configuration and logging output, but not a pure no-op

---

## Custom Date Formats

### Year-Month Folders (Default)

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos \
  --layout yyyy_mm
```

**Result:**

```
Google Photos/
  2023/
    01/
    02/
    12/
```

### Year-Only Folders

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos \
  --layout yyyy
```

**Result:**

```
Google Photos/
  2022/
  2023/
  2024/
```

---

## Finding Duplicates

### List All Duplicates

Duplicates are moved to `duplicates/` in your workdir. You can list them from the filesystem:

```bash
find ~/takeout_work/duplicates -type f | head -50
```

### Duplicate Statistics

```python
from pathlib import Path
from takeout_photos.core.database import PipelineDB

db = PipelineDB(Path.home() / "takeout_work" / "pipeline.db")
total_files = db.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
duplicates = sum(1 for _ in (Path.home() / "takeout_work" / "duplicates").rglob("*") if _.is_file())

print(f"Total files:    {total_files}")
print(f"Duplicates:     {duplicates}")
print(f"Unique files:   {total_files - duplicates}")
if total_files:
    print(f"Dedup rate:     {(duplicates / total_files) * 100:.1f}%")
```

---

## Performance Optimization

### Use xxhash for Faster Hashing

Install the optional fast dependencies:

```bash
pip install takeout-photos[fast]
```

### Process on Fast Storage

Put the work directory on fast storage (SSD):

```bash
takeout-photos process \
  --workdir ~/fast_ssd/takeout_work \
  --organized-dir /Volumes/SlowDrive/Photos  # SSD for temp work
```

### Delete ZIPs After Extraction

Save disk space by deleting ZIPs after successful extraction:

```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos \
  --delete-zips-after-extract
```

**⚠️ Warning:** Only use this if you have backups! ZIPs are deleted permanently.

### Batch Processing

Process very large Takeouts in batches:

1. Move 5-10 ZIPs into your workdir
2. Run the pipeline
3. Verify results
4. Add the next batch
5. Run again (automatically skips first batch)

---

## Common Workflows

### Workflow 1: Small Takeout (< 50GB)

```bash
# 1. Download Takeout ZIPs
# 2. Place in workdir
# 3. Run pipeline
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos

# 4. Verify results
ls -lh ~/Pictures/Google\ Photos/

# 5. Done!
```

### Workflow 2: Large Takeout (100GB+)

```bash
# 1. Process in batches
# First batch (10 ZIPs)
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos

# 2. Monitor progress
takeout-photos status --workdir ~/takeout_work

# 3. Add next batch after first completes
# 4. Run again (skips first batch)
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos
```

### Workflow 3: External Drive with Cleanup

```bash
# 1. Process to external drive
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir /Volumes/Photos/Google\ Photos \
  --delete-zips-after-extract

# 2. Verify results on external drive
ls -lh /Volumes/Photos/Google\ Photos/

# 3. ZIPs are automatically deleted after successful processing
```

---

## Tips and Tricks

### Check Disk Space Before Processing

```bash
# Check available space
df -h ~/takeout_work
df -h ~/Pictures

# Rule of thumb: Need 2-3x the size of your ZIPs
```

### Monitor Progress While Running

```bash
# Terminal 1: Run pipeline
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir ~/Pictures/Google\ Photos

# Terminal 2: Monitor progress
watch -n 5 'takeout-photos status --workdir ~/takeout_work'
```

### Verify Output Structure

```bash
# Count files by year-month
find ~/Pictures/Google\ Photos -type f | \
  xargs -I {} dirname {} | \
  sort | uniq -c

# Check file types
find ~/Pictures/Google\ Photos -type f | \
  sed 's/.*\.//' | sort | uniq -c
```

### Clean Up After Success

```bash
# After successful processing, you can clean up work directory
# (Keep the database for incremental processing)
rm -rf ~/takeout_work/extracted/*
rm -rf ~/takeout_work/duplicates/*

# Keep the database!
# Don't delete ~/takeout_work/pipeline.db
```

---

## Next Steps

- See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
- See [TUTORIAL.md](TUTORIAL.md) for a complete walkthrough
- See [examples/](../examples/) for code examples
