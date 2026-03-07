# Takeout Photos Tutorial

A complete step-by-step guide to processing your Google Photos Takeout export.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Scenario: Processing a Real Takeout](#scenario-processing-a-real-takeout)
5. [Verification and Results](#verification-and-results)
6. [What's Next](#whats-next)

---

## Introduction

This tutorial walks you through processing a realistic Google Photos Takeout export from start to finish.

**Our scenario:**

- **Takeout size:** 200GB
- **Number of ZIPs:** 50 files (takeout-001.zip through takeout-050.zip)
- **Estimated photos:** ~80,000 files
- **Goal:** Organize photos by year-month into a local directory
- **Expected time:** 6-10 hours (depending on hardware)

---

## Prerequisites

### What You Need

1. **Python 3.8 or higher**

   ```bash
   python3 --version
   ```

2. **Sufficient disk space**
   - Your Takeout ZIPs: 200GB
   - Work directory: 200GB (temporary)
   - Output directory: 160GB (after deduplication)
   - **Total recommended:** 400-500GB free space

3. **Your Google Photos Takeout ZIPs**
   - Downloaded from [Google Takeout](https://takeout.google.com/)
   - All ZIPs in one directory

### System Requirements

- **RAM:** 2GB minimum, 4GB+ recommended
- **CPU:** Any modern processor (multi-core helps)
- **OS:** macOS, Linux, or Windows
- **Storage:** SSD recommended for faster processing

---

## Installation

### Step 1: Install Python and Dependencies

**macOS:**

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python3

# Verify
python3 --version
```

**Ubuntu/Debian:**

```bash
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv
```

**Windows:**

1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run installer
3. Check "Add Python to PATH"
4. Verify in Command Prompt: `python --version`

### Step 2: Install ExifTool

ExifTool is required for reading and writing photo metadata.

**macOS:**

```bash
brew install exiftool

# Verify
exiftool -ver
```

**Ubuntu/Debian:**

```bash
sudo apt-get install libimage-exiftool-perl

# Verify
exiftool -ver
```

**Windows:**

1. Download from [exiftool.org](https://exiftool.org/)
2. Extract `exiftool(-k).exe`
3. Rename to `exiftool.exe`
4. Place in `C:\Windows\System32` or in your PATH
5. Verify in Command Prompt: `exiftool -ver`

### Step 3: Install Takeout-Photos

**macOS (Apple Silicon) — easiest, no Python required:**

```bash
brew tap diegomarino/tap
brew install takeout-photos

# Verify
takeout-photos --version
```

**All platforms (via PyPI):**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # Mac/Linux
.venv\Scripts\activate     # Windows

# Install
pip install takeout-photos[fast]

# Verify installation
takeout-photos --version
```

**Expected output:**

```
takeout-photos version 1.0.0
```

---

## Scenario: Processing a Real Takeout

Let's process our 200GB, 50-ZIP Google Photos Takeout.

### Phase 1: Preparation (15 minutes)

#### 1.1 Create Directory Structure

```bash
# Create directories for our workflow
mkdir -p ~/takeout_project/organized
mkdir -p ~/takeout_project/work
```

**Directory purposes:**

- `work/` - Working directory (ZIPs + extracted files + logs + database)
- `organized/` - Final organized photos (output)

#### 1.2 Move Your Takeout ZIPs

```bash
# Move all Takeout ZIPs into the work directory
mv ~/Downloads/takeout-*.zip ~/takeout_project/work/

# Verify they're there
ls -lh ~/takeout_project/work/*.zip
```

**Expected output:**

```
-rw-r--r--  1 user  staff   4.0G Jan 15 10:00 takeout-001.zip
-rw-r--r--  1 user  staff   4.0G Jan 15 10:15 takeout-002.zip
-rw-r--r--  1 user  staff   4.0G Jan 15 10:30 takeout-003.zip
...
-rw-r--r--  1 user  staff   4.0G Jan 15 18:30 takeout-050.zip
```

#### 1.3 Check Available Disk Space

```bash
df -h ~/takeout_project
```

**You should have:**

- At least 400GB free for smooth processing
- Minimum 300GB (tight but workable)

### Phase 2: Initial Test Run (30 minutes)

Before processing all 50 ZIPs, let's test with just 2 ZIPs.

#### 2.1 Test with Subset

```bash
# Create test workdir
mkdir -p ~/takeout_project/test_work

# Copy first 2 ZIPs into the workdir
cp ~/takeout_project/work/takeout-001.zip ~/takeout_project/test_work/
cp ~/takeout_project/work/takeout-002.zip ~/takeout_project/test_work/

# Test with dry-run first (no actual changes)
takeout-photos process \
  --organized-dir ~/takeout_project/test_output \
  --workdir ~/takeout_project/test_work \
  --layout yyyy_mm \
  --dry-run
```

**What to expect:**

- Should complete in a few seconds
- Shows what would be done
- No actual files created

#### 2.2 Run Test Processing

```bash
# Actually process the 2 test ZIPs
takeout-photos process \
  --organized-dir ~/takeout_project/test_output \
  --workdir ~/takeout_project/test_work \
  --layout yyyy_mm \
```

**Expected output (abbreviated):**

```
=== PHASE 1: Merge-Extract ===
Extracting: takeout-001.zip
Extracting: takeout-002.zip

=== PHASE 2: Batch Processing ===
[1/4] Validating formats...
[2/4] Applying metadata...
[3/4] Computing hashes...
[4/4] Organizing files...
✅ Completed takeout-001
✅ Completed takeout-002

=== PHASE 5: Quality control ===
QC report: logs/qc_YYYYMMDD_HHMMSS.txt
```

#### 2.3 Verify Test Results

```bash
# Check organized structure
ls -lh ~/takeout_project/test_output/

# Should see year/month folders
tree -L 2 ~/takeout_project/test_output/
```

**Expected structure:**

```
~/takeout_project/test_output/
├── 2020/
│   ├── 01/
│   │   ├── IMG_001.jpg
│   │   ├── IMG_002.jpg
│   └── ...
├── 2020-02/
│   ├── IMG_050.jpg
│   └── ...
├── 2020-12/
└── 2021-01/
```

#### 2.4 Check Statistics

```bash
# View processing statistics
takeout-photos status --workdir ~/takeout_project/test_work
```

**Expected output:**

```
Pipeline Status:
  Total ZIPs:       2
  Completed:        2
  In Progress:      0
  Failed:           0
  Pending:          0

Files:
  Total processed:  3,247
  Organized:        3,120
  Duplicates:       127 (3.9%)
```

**✓ Test successful!** Now we can process all 50 ZIPs.

### Phase 3: Full Processing (6-10 hours)

Now we'll process all 50 ZIPs. This will take several hours.

#### 3.1 Start Full Processing

```bash
# Process all ZIPs
takeout-photos process \
  --organized-dir ~/takeout_project/organized \
  --workdir ~/takeout_project/work \
  --layout yyyy_mm \
```

**What happens:**

- Processes all 50 ZIPs sequentially
- Shows progress for each stage
- Updates database continuously
- Can be safely interrupted (Ctrl+C) and resumed

#### 3.2 Monitor Progress (Optional)

Open a second terminal to monitor while processing:

```bash
# Activate environment
cd ~/takeout-photos
source .venv/bin/activate

# Watch status (updates every 5 seconds)
watch -n 5 'takeout-photos status --workdir ~/takeout_project/work'
```

**Or use the monitoring example:**

```bash
python examples/monitoring.py --live
```

#### 3.3 Expected Timeline

| Phase | Time | Notes |
| --- | --- | --- |
| Extract ZIPs | 1-2 hours | Depends on disk speed |
| Validate Formats | 30 min | exiftool calls |
| Apply Metadata | 1-2 hours | JSON → EXIF |
| Compute Hashes | 2-3 hours | Most time-consuming (CPU) |
| Organize + Inline Dedupe | 1 hour | Moving to final structure |
| Quality Control | 20 min | exiftool scans |
| **Total** | 5-9 hrs | Varies by hardware |

### Phase 4: Handling Interruptions

If you need to stop processing (system shutdown, low disk space, etc.):

#### 4.1 Interrupt the Pipeline

```bash
# Press Ctrl+C to stop
# Or close terminal
# Or system crash
```

**Don't worry!** The pipeline tracks all progress.

#### 4.2 Check Recovery State

```bash
takeout-photos recovery --workdir ~/takeout_project/work --dry-run
```

**Expected output (example):**

```
Recovery Summary (dry-run):
  Intermediate ZIPs:      1
  Orphaned organized:     0
  Orphaned extracted:     0
  Missing files:          0
```

#### 4.3 Resume Processing

```bash
# Just run the pipeline again
takeout-photos process \
  --organized-dir ~/takeout_project/organized \
  --workdir ~/takeout_project/work \
  --layout yyyy_mm \
```

**What happens:**

- Auto-recovery runs on startup
- Skips completed ZIPs (e.g., ZIPs 1-25)
- Resumes incomplete ZIP (e.g., ZIP 26)
- Continues with pending ZIPs (e.g., ZIPs 27-50)

---

## Verification and Results

### Step 1: Check Final Status

```bash
takeout-photos status --workdir ~/takeout_project/work
```

**Expected output:**

```
Pipeline Status:
  Total ZIPs:       50
  Completed:        50
  In Progress:      0
  Failed:           0
  Pending:          0

Files:
  Total processed:  82,147
  Organized:        78,903
  Duplicates:       3,244 (3.9%)
```

### Step 2: Explore Organized Photos

```bash
# View folder structure
ls -lh ~/takeout_project/organized/

# Count files by year-month
find ~/takeout_project/organized -type f | \
  xargs -I {} dirname {} | \
  basename -a | \
  sort | uniq -c

# Check file types
find ~/takeout_project/organized -type f | \
  sed 's/.*\.//' | sort | uniq -c
```

**Expected structure:**

```
~/takeout_project/organized/
├── 2015-06/
│   └── (345 files)
├── 2015-07/
│   └── (412 files)
├── ...
├── 2023-11/
│   └── (1,234 files)
└── 2023-12/
    └── (987 files)
```

### Step 3: Verify Sample Files

```bash
# Pick a random folder and check a file
cd ~/takeout_project/organized/2020-01/

# View file details
ls -lh | head -10

# Check EXIF data on a photo
exiftool IMG_20200115_*.jpg
```

### Step 4: Check for Duplicates

```python
# Run this Python snippet
from pathlib import Path
from takeout_photos.core.database import PipelineDB

db = PipelineDB(Path.home() / "takeout_project/work/pipeline.db")
duplicates = db.get_all_duplicates()

print(f"Found {len(duplicates)} sets of duplicates")
print(f"\nExample duplicate set:")
if duplicates:
    dup_hash, files = duplicates[0]
    print(f"Hash: {dup_hash}")
    for file_path in files:
        print(f"  - {file_path}")
```

### Step 5: Calculate Space Savings

```bash
# Original ZIP size
du -sh ~/takeout_project/work/
# Output: 200G

# Organized output size
du -sh ~/takeout_project/organized/
# Output: 164G

# Space saved: 36GB (18% reduction from deduplication)
```

### Step 6: Clean Up Work Directory (Optional)

After successful processing, you can clean up temporary files:

```bash
# Remove extraction directories
rm -rf ~/takeout_project/work/extract/*

# Remove intermediate ZIPs
rm -rf ~/takeout_project/work/intermediate/*

# Keep the database for future incremental processing!
# Don't delete ~/takeout_project/work/pipeline.db
```

---

## What's Next

### Incremental Processing

When you have new Google Photos to export:

1. Download new Takeout ZIPs from Google
2. Place them in `~/takeout_project/work/`
3. Run the pipeline again:

```bash
takeout-photos process \
  --organized-dir ~/takeout_project/organized \
  --workdir ~/takeout_project/work \
  --layout yyyy_mm \
```

**The pipeline will:**

- Automatically skip the 50 ZIPs already processed
- Only process the new ZIPs
- Add new photos to existing date folders
- Deduplicate against existing photos

### Moving to External Drive

To move your organized photos to an external drive:

**Option 1: Copy after processing**

```bash
# Copy to external drive
cp -r ~/takeout_project/organized/* /Volumes/Photos/Google\ Photos/

# Verify
ls -lh /Volumes/Photos/Google\ Photos/
```

**Option 2: Process directly to external drive**

```bash
takeout-photos process \
  --organized-dir /Volumes/Photos/Google\ Photos \
  --workdir ~/takeout_project/work \
  --layout yyyy_mm \
```

### Importing to Photo Management Software

Your organized photos can now be imported to:

- **Apple Photos:** File → Import → Select folder
- **Google Photos:** Upload organized folders
- **Adobe Lightroom:** Import from folder
- **Any photo manager:** Point to organized directory

The organized structure makes it easy to:

- Find photos by date
- Manage chronologically
- Share specific time periods
- Backup incrementally

---

## Summary

**What we accomplished:**

✅ Installed takeout-photos and dependencies
✅ Processed 200GB of Google Photos Takeout (50 ZIPs)
✅ Organized 78,903 photos by year-month
✅ Removed 3,244 duplicate photos (3.9%)
✅ Saved 36GB of space through deduplication
✅ Created a clean, organized photo library

**Time invested:**

- Setup: 15 minutes
- Testing: 30 minutes
- Processing: 6-10 hours (mostly unattended)
- Verification: 15 minutes

**Next steps:**

- Import to your favorite photo manager
- Set up regular backups
- Process new Takeouts incrementally
- Enjoy your organized photo library!

---

## Additional Resources

- **Examples:** See [examples/](../examples/) for code samples
- **Cookbook:** See [COOKBOOK.md](COOKBOOK.md) for common recipes
- **Troubleshooting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for help
- **API Docs:** See [api.md](api.md) for library documentation
- **Architecture:** See [architecture.md](architecture.md) for internals

---

## Getting Help

If you encounter issues:

1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Review the logs in `~/takeout_project/work/logs/`
3. Run with `--dry-run` to preview
4. Start with a smaller subset of ZIPs
5. Check available disk space

**Still stuck?** Open an issue on GitHub with:

- Error messages
- Configuration used
- System information (OS, Python version, exiftool version)
- Steps to reproduce

---

**Congratulations!** You've successfully processed your Google Photos Takeout and created an organized, deduplicated photo library. 🎉
