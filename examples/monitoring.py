#!/usr/bin/env python3
"""Pipeline monitoring example for takeout-photos.

This example shows how to monitor pipeline progress using database queries
and display real-time statistics about processing status.
"""

import time
from pathlib import Path

from takeout_photos.core.database import PipelineDB


def get_pipeline_statistics(db_path: Path) -> dict:
    """Get comprehensive statistics from the pipeline database."""
    if not db_path.exists():
        return {
            "total_zips": 0,
            "completed": 0,
            "in_progress": 0,
            "failed": 0,
            "pending": 0,
            "total_files": 0,
            "organized_files": 0,
            "duplicates": 0,
        }

    db = PipelineDB(db_path)

    # Get all ZIPs (intermediate state)
    zips = db.get_intermediate_zips()

    # Count by status
    status_counts = {"completed": 0, "in_progress": 0, "failed": 0, "pending": 0}

    for zip_record in zips:
        status = zip_record["status"]
        if status in status_counts:
            status_counts[status] += 1

    # Get pending ZIPs (alternative method)
    pending_zips = db.get_pending_zips()

    return {
        "total_zips": len(zips),
        "completed": status_counts["completed"],
        "in_progress": status_counts["in_progress"],
        "failed": status_counts["failed"],
        "pending": len(pending_zips),
        "total_files": 0,  # Not directly available
        "organized_files": 0,  # Not directly available
        "duplicates": 0,  # Not directly available
    }


def display_progress_bar(completed: int, total: int, width: int = 50) -> str:
    """Create a text-based progress bar."""
    if total == 0:
        return "[" + " " * width + "] 0%"

    percentage = completed / total
    filled = int(width * percentage)
    bar = "=" * filled + " " * (width - filled)

    return f"[{bar}] {percentage * 100:.1f}%"


def display_statistics(stats: dict):
    """Display formatted pipeline statistics."""
    print("=" * 80)
    print("Pipeline Status")
    print("=" * 80)

    # ZIP processing status
    print("\nZIP Files:")
    print(f"  Total:       {stats['total_zips']}")
    print(f"  Completed:   {stats['completed']}")
    print(f"  In Progress: {stats['in_progress']}")
    print(f"  Failed:      {stats['failed']}")
    print(f"  Pending:     {stats['pending']}")

    if stats["total_zips"] > 0:
        progress = display_progress_bar(stats["completed"], stats["total_zips"])
        print(f"\n  Progress: {progress}")

    # File statistics
    print("\nFiles:")
    print(f"  Total processed:  {stats['total_files']}")
    print(f"  Organized:        {stats['organized_files']}")
    print(f"  Duplicates found: {stats['duplicates']}")

    if stats["total_files"] > 0:
        dedup_rate = (stats["duplicates"] / stats["total_files"]) * 100
        print(f"  Deduplication:    {dedup_rate:.1f}%")

    print("\n" + "=" * 80)


def monitor_detailed_zip_status(db_path: Path):
    """Show detailed status for each ZIP file."""
    print("\nDetailed ZIP Status:")
    print("-" * 80)

    if not db_path.exists():
        print("No database found - pipeline hasn't been run yet.")
        return

    db = PipelineDB(db_path)
    zips = db.get_intermediate_zips()

    if not zips:
        print("No ZIPs found in database yet.")
        return

    # Header
    print(f"{'ZIP File':<35} {'Status':<12} {'Files':<10}")
    print("-" * 80)

    for zip_record in zips:
        zip_name = zip_record["name"][:34]  # Truncate long names
        status = zip_record["status"]

        # Get file count for this ZIP
        files = db.get_files_for_zip(zip_record["name"])
        file_count = len(files)

        print(f"{zip_name:<35} {status:<12} {file_count:<10}")


def monitor_live(db_path: Path, interval: int = 5, duration: int = 60):
    """Monitor pipeline progress in real-time."""
    print("=" * 80)
    print("Live Pipeline Monitor")
    print("=" * 80)
    print(f"\nRefreshing every {interval} seconds...")
    print(f"Monitoring for {duration} seconds (Ctrl+C to stop)")
    print("\n")

    start_time = time.time()

    try:
        while (time.time() - start_time) < duration:
            # Clear screen (works on Unix/Mac)
            print("\033[2J\033[H", end="")

            # Get and display current statistics
            stats = get_pipeline_statistics(db_path)
            display_statistics(stats)

            # Show detailed status
            monitor_detailed_zip_status(db_path)

            # Show update time
            elapsed = int(time.time() - start_time)
            print(f"\nElapsed: {elapsed}s | Next update in {interval}s...")

            # Wait before next update
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")


def check_completion_status(db_path: Path) -> bool:
    """Check if the pipeline has completed all processing.

    Args:
        db_path: Path to the pipeline database

    Returns:
        True if all ZIPs are completed and none are in progress
    """
    stats = get_pipeline_statistics(db_path)

    if stats["total_zips"] == 0:
        return False

    # Completed if all ZIPs are done and no in-progress
    return bool(stats["completed"] == stats["total_zips"] and stats["in_progress"] == 0)


def example_simple_monitoring():
    """Simple one-time status check."""
    print("=" * 80)
    print("Simple Status Check")
    print("=" * 80)

    work_dir = Path.home() / "takeout_work"
    db_path = work_dir / "pipeline.db"

    print(f"\nDatabase: {db_path}")

    if not db_path.exists():
        print("\n✗ No database found - pipeline hasn't been run yet.")
        return

    # Get statistics
    stats = get_pipeline_statistics(db_path)
    display_statistics(stats)

    # Show detailed ZIP status
    monitor_detailed_zip_status(db_path)

    # Check if complete
    if check_completion_status(db_path):
        print("\n✓ Pipeline processing is complete!")
    elif stats["in_progress"] > 0:
        print("\n⏳ Pipeline is currently running...")
    elif stats["failed"] > 0:
        print(f"\n⚠️  {stats['failed']} ZIP(s) failed - check logs for details")
    else:
        print(f"\n⏸  {stats['pending']} ZIP(s) pending processing")


def example_continuous_monitoring():
    """Continuously monitor while pipeline is running."""
    print("=" * 80)
    print("Continuous Monitoring Example")
    print("=" * 80)

    work_dir = Path.home() / "takeout_work"
    db_path = work_dir / "pipeline.db"

    print(f"\nDatabase: {db_path}")

    if not db_path.exists():
        print("\n✗ No database found - pipeline hasn't been run yet.")
        print("\nStart the pipeline in another terminal, then run this script.")
        return

    print("\nStarting live monitoring...")
    print("This will update every 5 seconds.")
    print("\n")

    # Monitor for up to 300 seconds (5 minutes)
    monitor_live(db_path, interval=5, duration=300)


def main():
    """Demonstrate different monitoring approaches."""
    print("Pipeline Monitoring Examples")
    print("=" * 80)
    print("\nThis script shows how to monitor pipeline progress.")
    print("\nTwo approaches:")
    print("  1. Simple one-time status check")
    print("  2. Continuous live monitoring")

    print("\n" + "=" * 80)

    # Run simple monitoring by default
    example_simple_monitoring()

    print("\n" + "=" * 80)
    print("\nTo run continuous monitoring:")
    print("  1. Start the pipeline in one terminal:")
    print("     $ takeout-photos process --input-dir ~/Downloads/takeout_zips")
    print("\n  2. Run this script in another terminal:")
    print("     $ python examples/monitoring.py --live")
    print("\n  Or uncomment the line below:")
    print("  # example_continuous_monitoring()")


if __name__ == "__main__":
    import sys

    # Support --live flag for continuous monitoring
    if "--live" in sys.argv:
        work_dir = Path.home() / "takeout_work"
        db_path = work_dir / "pipeline.db"
        monitor_live(db_path, interval=5, duration=600)
    else:
        main()
