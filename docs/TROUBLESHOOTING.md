# Troubleshooting Guide

Common issues and solutions for takeout-photos.

---

## Table of Contents

- [Installation Issues](#installation-issues)
- [ExifTool Errors](#exiftool-errors)
- [Disk Space Problems](#disk-space-problems)
- [Pipeline Interruptions](#pipeline-interruptions)
- [Corrupted ZIP Files](#corrupted-zip-files)
- [Performance Issues](#performance-issues)
- [Database Errors](#database-errors)
- [Date/Time Issues](#datetime-issues)
- [File Permission Errors](#file-permission-errors)
- [Recovery Failures](#recovery-failures)

---

## Installation Issues

### Error: "No module named 'takeout_photos'"

**Problem:** Package not installed or virtual environment not activated.

**Solution:**
```bash
# Activate virtual environment
source .venv/bin/activate  # Mac/Linux
.venv\Scripts\activate     # Windows

# Install package
pip install -e .

# Verify installation
python -c "import takeout_photos; print('OK')"
```

### Error: "python: command not found"

**Problem:** Python not installed or not in PATH.

**Solution:**

**Mac:**
```bash
# Install via Homebrew
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
- Download from [python.org](https://www.python.org/downloads/)
- Run installer and check "Add Python to PATH"

---

## ExifTool Errors

### Error: "exiftool not found" or "ExifTool dependency not found"

**Problem:** ExifTool not installed or not in PATH.

**Solution:**

**Mac:**
```bash
# Install via Homebrew
brew install exiftool

# Verify installation
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
2. Extract `exiftool(-k).exe` and rename to `exiftool.exe`
3. Place in a directory in your PATH (e.g., `C:\Windows\System32`)
4. Or place in the same directory as your script

**Verify:**
```bash
exiftool -ver
# Should output version number (e.g., 12.70)
```

### Error: "ExifTool returned non-zero exit code"

**Problem:** ExifTool failed to process a file.

**Common causes:**
- Corrupted image file
- Unsupported file format
- File permissions issue

**Solution:**
```bash
# Test the specific file manually
exiftool /path/to/problem/file.jpg

# Check file integrity
file /path/to/problem/file.jpg

# Check permissions
ls -l /path/to/problem/file.jpg

# The pipeline will mark failed files and continue processing others
```

---

## Disk Space Problems

### Error: "No space left on device"

**Problem:** Work directory or output directory is full.

**Solution:**

**1. Check available space:**
```bash
df -h ~/takeout_work
df -h ~/Pictures
```

**2. Clean up work directory:**
```bash
# Remove extracted files (safe after successful run)
rm -rf ~/takeout_work/extracted/*

# Remove duplicates (optional)
rm -rf ~/takeout_work/duplicates/*

# Keep the database!
# Don't delete ~/takeout_work/pipeline.db
```

**3. Use external drive for output:**
```bash
takeout-photos process \
  --workdir ~/takeout_work \
  --organized-dir /Volumes/ExternalDrive/Photos
```

**4. Process in smaller batches:**
- Move only 5-10 ZIPs into your workdir at a time
- Process them
- Clean up and add next batch

**5. Use a different work directory with more space:**
```bash
takeout-photos process \
  --workdir /path/to/larger/drive/work \
  --organized-dir ~/Pictures/Google\ Photos
```

### How much disk space do I need?

**Rule of thumb:** 2-3x the total size of your ZIP files.

**Example:**
- ZIP files: 100GB
- Work directory: 100GB (for extraction and processing)
- Output directory: 80GB (deduplicated, organized files)
- **Total needed:** ~180-200GB

**Check ZIP sizes:**
```bash
du -sh ~/Downloads/takeout_zips
```

---

## Pipeline Interruptions

### What happens if I press Ctrl+C?

**Answer:** The pipeline can be safely interrupted and will auto-recover.

**What happens:**
- Current stage completes or is marked incomplete
- Database is updated with current state
- Files remain in their current locations

**To resume:**
```bash
# Just run the pipeline again
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

**Auto-recovery will:**
- Detect incomplete ZIPs
- Resume from last completed stage
- Clean up any orphaned files
- Continue processing

### Error: "Pipeline was interrupted unexpectedly"

**Problem:** System crash, power loss, or forced termination.

**Solution:**
```bash
# 1. Check recovery state
takeout-photos recovery --workdir ~/takeout_work --dry-run

# 2. Run recovery (optional - auto-recovery happens on next run)
takeout-photos recovery --workdir ~/takeout_work

# 3. Resume processing
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

---

## Corrupted ZIP Files

### Error: "Failed to extract ZIP file" or "ZIP file is corrupted"

**Problem:** ZIP file is damaged or incomplete.

**Solution:**

**1. Verify the ZIP:**
```bash
# Test ZIP integrity
unzip -t ~/Downloads/takeout_zips/takeout-001.zip

# Or on Mac:
ditto -V ~/Downloads/takeout_zips/takeout-001.zip
```

**2. Re-download the ZIP:**
- Download the Takeout ZIP again from Google
- Replace the corrupted file

**3. Skip the corrupted ZIP:**
```bash
# Remove the corrupted ZIP from workdir
mv ~/takeout_work/takeout-001.zip ~/Downloads/corrupted/

# Continue processing other ZIPs
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

**4. Reset and retry:**
```bash
# Reset the ZIP in database
takeout-photos --workdir ~/takeout_work reset --zip takeout-001.zip

# Fix or replace the ZIP file

# Retry processing
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

---

## Performance Issues

### Pipeline is very slow

**Possible causes and solutions:**

**1. Slow disk (spinning HDD):**
```bash
# Move work directory to SSD
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/fast_ssd/takeout_work  # Use SSD
```

**2. Missing fast dependencies:**
```bash
# Install optional fast dependencies
pip install takeout-photos[fast]
```

**3. External drive over USB 2.0:**
- Use USB 3.0+ or Thunderbolt for external drives
- Or process to local drive first, then move to external

**4. Antivirus scanning:**
- Temporarily disable antivirus for work directory
- Add takeout_work to exclusions

**5. Too many small files:**
- This is normal for large Takeouts
- Be patient - hashing thousands of files takes time

### How long should processing take?

**Approximate times:**

| Takeout Size | File Count | Estimated Time |
| ------------ | ---------- | -------------- |
| 10GB         | 5,000      | 30-60 minutes  |
| 50GB         | 25,000     | 2-4 hours      |
| 100GB        | 50,000     | 4-8 hours      |
| 200GB+       | 100,000+   | 8-16 hours     |

**Factors affecting speed:**
- Disk speed (SSD vs HDD)
- Whether xxhash is installed
- File count (many small files are slower)
- CPU speed
- Available RAM

---

## Database Errors

### Error: "database is locked" or "SQLITE_BUSY"

**Problem:** Multiple processes trying to access database simultaneously.

**Solution:**
```bash
# 1. Check for other running processes
ps aux | grep takeout-photos

# 2. Kill any stuck processes
kill <process_id>

# 3. Wait a moment and retry
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

**Prevention:** Don't run multiple pipeline instances with the same work directory.

### Error: "database disk image is malformed"

**Problem:** Database file is corrupted.

**Solution:**

**Option 1: Use recovery (if possible):**
```bash
takeout-photos recovery --workdir ~/takeout_work
```

**Option 2: Rebuild database (loses progress tracking):**
```bash
# Backup current database
cp ~/takeout_work/pipeline.db ~/takeout_work/pipeline.db.backup

# Delete corrupted database
rm ~/takeout_work/pipeline.db

# Run pipeline (creates new database)
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

**Note:** This will reprocess all ZIPs since progress tracking is lost.

---

## Date/Time Issues

### Photos not organized by correct date

**Problem:** Date information missing or incorrect in files.

**Common causes:**
- No EXIF data in file
- Incorrect timezone in EXIF
- Screenshot or edited photo (creation date only)

**Solution:**

**1. Check file dates:**
```bash
# View EXIF data
exiftool /path/to/photo.jpg | grep Date

# View file dates
ls -l /path/to/photo.jpg
stat /path/to/photo.jpg
```

**2. How the pipeline determines dates (in order):**
1. Google Takeout JSON metadata
2. EXIF DateTimeOriginal
3. EXIF CreateDate
4. File modification time (fallback)

**3. If using wrong date:**
- The pipeline uses the best available date
- Consider manually organizing problem files
- Check if Google Takeout JSON exists for the file

### Files organized into wrong year/month folders

**Problem:** Date format or timezone issues.

**Check:**
```bash
# View a file's metadata
exiftool /path/to/photo.jpg | grep -i date
```

**Solutions:**
- Verify the date format setting matches your preference
- Check that file dates are correct in EXIF data
- Some files (screenshots, downloads) may not have accurate dates

---

## File Permission Errors

### Error: "Permission denied" when accessing files

**Problem:** Insufficient permissions for files or directories.

**Solution:**

**1. Check permissions:**
```bash
ls -ld ~/takeout_work
ls -l ~/Downloads/takeout_zips
```

**2. Fix permissions:**
```bash
# Make directories writable
chmod -R u+w ~/takeout_work

# Fix ownership (if needed)
sudo chown -R $USER:$USER ~/takeout_work
```

**3. Check disk permissions:**
- External drives may be read-only
- Check mount options for external drives

**4. macOS Security:**
- System Preferences → Security & Privacy → Full Disk Access
- Add Terminal or your Python app

---

## macOS Binary Issues

### macOS Binary "killed" or Blocked on Launch

**Problem:** macOS Gatekeeper blocks the downloaded binary because it's not code-signed.

**Symptoms:**
- Running `./takeout-photos` results in `[1] killed ./takeout-photos`
- System Settings shows: *"takeout-photos was blocked from use because it is not from an identified developer"*

**This is expected behavior** - the binary is unsigned to avoid requiring an Apple Developer account ($99/year).

**Solutions:**

**Method 1: Privacy & Security (Recommended)**

1. Try to run the binary once (it will be blocked)
2. Go to **System Settings** → **Privacy & Security**
3. Scroll down to the **Security** section
4. You'll see: *"takeout-photos was blocked from use because it is not from an identified developer"*
5. Click **"Open Anyway"**
6. Confirm in the dialog by clicking **"Open"**
7. The binary will now run normally

**Method 2: Remove Quarantine Attribute (Terminal)**

```bash
# Navigate to where you extracted the binary
cd ~/Downloads

# Remove the quarantine flag
xattr -d com.apple.quarantine takeout-photos

# Now it will run without blocking
./takeout-photos --help
```

**Method 3: Right-Click Method**

1. In Finder, **right-click** (or Control+click) on `takeout-photos`
2. Select **"Open"** from the context menu (not double-click!)
3. Click **"Open"** in the confirmation dialog
4. The binary will run and be whitelisted for future use

**Why does this happen?**

macOS Gatekeeper blocks unsigned binaries downloaded from the internet as a security measure. Code signing requires an Apple Developer account ($99/year), which we've chosen not to require for this open-source project.

**Is this safe?**

Yes - as long as you downloaded the binary from the official GitHub Releases page. The binary is built automatically by GitHub Actions, and the source code is publicly auditable.

---

## Recovery Failures

### Recovery doesn't fix the issue

**Problem:** Recovery system can't automatically fix the issue.

**Solution:**

**1. Analyze what's wrong:**
```bash
takeout-photos recovery --workdir ~/takeout_work --dry-run
```

**2. Manual recovery steps:**

**For stuck ZIPs:**
```bash
# Reset the specific ZIP
takeout-photos --workdir ~/takeout_work reset --zip takeout-001.zip
```

**For corrupted files:**
```bash
# Remove the specific corrupted file if known
rm -f ~/takeout_work/extracted/path/to/problem.jpg

# Reset the ZIP and re-run
takeout-photos --workdir ~/takeout_work reset --zip takeout-001.zip
```

**3. Nuclear option (start fresh):**
```bash
# Backup organized files (if any)
cp -r ~/Pictures/Google\ Photos ~/Pictures/Google\ Photos.backup

# Delete work directory
rm -rf ~/takeout_work

# Start over
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work
```

---

## Still Having Issues?

### Collect Debug Information

```bash
# 1. Check versions
python --version
exiftool -ver
takeout-photos --version

# 2. Check status
takeout-photos status --workdir ~/takeout_work

# 3. Check logs
cat ~/takeout_work/logs/pipeline.log | tail -100

# 4. Test with dry-run
takeout-photos process \
  --organized-dir ~/Pictures/Google\ Photos \
  --workdir ~/takeout_work \
  --dry-run
```

### Enable Debug Logging

```python
import logging
from pathlib import Path
from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

config = Config(
    workdir=Path.home() / "takeout_work",
    organized_dir=Path.home() / "Pictures" / "Google Photos",
)

pipeline = Pipeline(config)
pipeline.run()
```

### Getting Help

1. **Check the documentation:**
   - [TUTORIAL.md](TUTORIAL.md) - Complete walkthrough
   - [COOKBOOK.md](COOKBOOK.md) - Common recipes
   - [examples/](../examples/) - Code examples

2. **Search existing issues:**
   - Check the GitHub issues page for similar problems

3. **Open a new issue:**
   - Include error messages
   - Include debug information
   - Describe what you were trying to do
   - Include your configuration (with paths anonymized)

---

## Common Error Messages

### "FileNotFoundError: [Errno 2] No such file or directory"

**Cause:** Path doesn't exist.

**Solution:** Check that all directories exist and paths are correct.

### "PermissionError: [Errno 13] Permission denied"

**Cause:** No write permissions.

**Solution:** Fix permissions with `chmod` or run with appropriate user.

### "OSError: [Errno 28] No space left on device"

**Cause:** Disk full.

**Solution:** Free up space or use a different directory.

### "zipfile.BadZipFile: File is not a zip file"

**Cause:** Corrupted or invalid ZIP file.

**Solution:** Re-download the Takeout ZIP from Google.

### "sqlite3.OperationalError: database is locked"

**Cause:** Another process is using the database.

**Solution:** Wait for other process to finish or kill stuck processes.

### "ModuleNotFoundError: No module named 'xxhash'"

**Cause:** xxhash library not installed.

**Solution:**
```bash
pip install xxhash
```

---

## Prevention Tips

1. **Start small:** Test with 1-2 ZIPs first
2. **Check disk space:** Ensure 2-3x ZIP size available
3. **Use dry-run:** Test configuration with `--dry-run` first
4. **Monitor progress:** Use `status` command to track progress
5. **Keep backups:** Don't delete ZIPs until you verify results
6. **Use xxhash:** Install `takeout-photos[fast]`
7. **Batch processing:** Process large Takeouts in smaller batches
8. **Fast storage:** Use SSD for work directory when possible

---

## Quick Reference

| Issue                  | Quick Fix                                                    |
| ---------------------- | ------------------------------------------------------------ |
| exiftool not found     | `brew install exiftool` (Mac) or download from exiftool.org |
| Disk full              | Clean up work directory or use external drive                |
| Pipeline interrupted   | Just run it again - auto-recovery happens                    |
| Corrupted ZIP          | Re-download from Google or use `reset --zip`                 |
| Slow performance       | Install `takeout-photos[fast]` and use SSD for work dir      |
| Database locked        | Wait or kill stuck processes                                 |
| Permission denied      | `chmod -R u+w ~/takeout_work`                                |
| Can't resume           | Run `recovery` command or just run pipeline again            |
| Wrong dates            | Check EXIF data with `exiftool`                              |
| Module not found       | Activate venv: `source .venv/bin/activate`                   |
