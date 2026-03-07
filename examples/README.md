# Takeout Photos - Examples

This directory contains practical examples showing how to use the takeout-photos library in different scenarios.

## Available Examples

### 1. Basic Usage (`basic_usage.py`)

The simplest way to get started with takeout-photos. Shows how to process Google Photos Takeout ZIPs with default settings.

**What it demonstrates:**
- Creating a Config object with input/output directories
- Running the full 8-stage pipeline
- Understanding the output structure

**Run it:**
```bash
python examples/basic_usage.py
```

---

### 2. Custom Organization (`custom_organization.py`)

Shows different ways to organize your photos based on your needs.

**What it demonstrates:**
- Organizing photos to an external drive
- Using YYYY format (year-only folders)
- Using YYYY-MM format (year-month folders)
- Cleaning up ZIPs after successful extraction

**Run it:**
```bash
python examples/custom_organization.py
```

---

### 3. Incremental Processing (`incremental_processing.py`)

Learn how to process Takeout ZIPs in batches and add new exports over time.

**What it demonstrates:**
- Checking which ZIPs have already been processed
- Running the pipeline multiple times safely
- Adding new ZIPs without reprocessing old ones
- Querying the database for status information

**Run it:**
```bash
python examples/incremental_processing.py
```

---

### 4. Recovery Workflow (`recovery_workflow.py`)

Understand how the recovery system handles interruptions and errors.

**What it demonstrates:**
- Analyzing recovery state before processing
- Automatic recovery on pipeline startup
- Manual recovery operations
- Handling common error scenarios (interruptions, disk full, etc.)

**Run it:**
```bash
python examples/recovery_workflow.py
```

---

### 5. Monitoring (`monitoring.py`)

Monitor pipeline progress and get real-time statistics.

**What it demonstrates:**
- Querying the database for statistics
- Displaying progress bars and status
- Monitoring individual ZIP files
- Live monitoring while pipeline runs

**Run it:**
```bash
# One-time status check
python examples/monitoring.py

# Continuous live monitoring
python examples/monitoring.py --live
```

---

## Prerequisites

Before running these examples:

1. **Install takeout-photos:**
   ```bash
   pip install -e .
   ```

2. **Install exiftool** (required for EXIF processing):
   - **Mac:** `brew install exiftool`
   - **Ubuntu/Debian:** `sudo apt-get install libimage-exiftool-perl`
   - **Windows:** Download from [exiftool.org](https://exiftool.org/)

3. **Prepare your Takeout ZIPs:**
   - Download your Google Photos Takeout from [Google Takeout](https://takeout.google.com/)
   - Place the ZIP files in a directory (e.g., `~/Downloads/takeout_zips/`)

---

## Customizing Examples

All examples use paths like `~/Downloads/takeout_zips` and `~/Pictures/Google Photos`.

**To customize for your setup:**

1. Edit the path variables at the top of each example:
   ```python
   input_dir = Path.home() / "Downloads" / "takeout_zips"
   output_dir = Path.home() / "Pictures" / "Google Photos"
   work_dir = Path.home() / "takeout_work"
   ```

2. Or use the CLI instead:
   ```bash
   takeout-photos \
     --workdir /your/work/path \
     --organized-dir /your/output/path \
     process
   ```

---

## Example Workflow

Here's a complete workflow using these examples:

### First-time Processing

1. **Start with basic usage** to understand the pipeline:
   ```bash
   python examples/basic_usage.py
   ```

2. **Monitor progress** in another terminal:
   ```bash
   python examples/monitoring.py --live
   ```

3. **Check results** when complete:
   ```bash
   ls -lh ~/Pictures/Google\ Photos/
   ```

### Adding More Photos Later

4. **Download new Takeout ZIPs** from Google

5. **Place them in the same input directory**

6. **Run incremental processing**:
   ```bash
   python examples/incremental_processing.py
   ```

   The pipeline will skip already-processed ZIPs and only process the new ones.

### Handling Interruptions

If the pipeline is interrupted (Ctrl+C, system crash, etc.):

7. **Check recovery state**:
   ```bash
   python examples/recovery_workflow.py
   ```

8. **Just run the pipeline again** - it auto-recovers:
   ```bash
   python examples/basic_usage.py
   ```

---

## Tips

- **Start small:** Test with 1-2 small ZIPs first to verify your setup
- **Use dry-run:** Set `dry_run=True` in Config to preview without making changes
- **Monitor disk space:** Processing requires 2-3x the size of your ZIPs
- **Be patient:** Large Takeouts (100GB+) can take several hours
- **Check logs:** Look in `work_dir/logs/` for detailed operation logs

---

## Getting Help

- **Documentation:** See [docs/](../docs/) for detailed guides
- **Troubleshooting:** See [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md)
- **Tutorial:** See [docs/TUTORIAL.md](../docs/TUTORIAL.md) for a complete walkthrough
- **Cookbook:** See [docs/COOKBOOK.md](../docs/COOKBOOK.md) for common recipes

---

## Next Steps

After trying these examples:

1. Read the [TUTORIAL.md](../docs/TUTORIAL.md) for a complete walkthrough
2. Check [COOKBOOK.md](../docs/COOKBOOK.md) for common use cases
3. Explore the [API documentation](../docs/api.md) for advanced usage
4. Review [architecture.md](../docs/architecture.md) to understand the internals
