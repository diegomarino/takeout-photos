#!/usr/bin/env python3
"""Incremental processing example for takeout-photos.

This example demonstrates how the pipeline automatically skips already-processed ZIPs,
making it safe to run multiple times and process new ZIPs incrementally.
"""

from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline


def check_processed_zips(db_path: Path):
    """Query the database to see which ZIPs have been processed."""
    print("=" * 80)
    print("Checking Previously Processed ZIPs")
    print("=" * 80)

    if not db_path.exists():
        print(f"\n✗ No database found at: {db_path}")
        print("  This is a fresh start - no ZIPs have been processed yet.")
        return

    db = PipelineDB(db_path)

    # Get all ZIPs in the database
    zips = db.get_intermediate_zips()

    if not zips:
        print("\nNo ZIPs found in database yet.")
        return

    print(f"\nFound {len(zips)} ZIP(s) in database:")
    print("\n{:<40} {:<15}".format("ZIP File", "Status"))
    print("-" * 80)

    for zip_record in zips:
        zip_name = zip_record["name"]
        status = zip_record["status"]

        print(f"{zip_name:<40} {status:<15}")

    print("\nStatus meanings:")
    print("  - pending: Not yet started")
    print("  - in_progress: Currently being processed")
    print("  - completed: Fully processed (will be skipped on next run)")
    print("  - failed: Encountered an error (will be retried)")


def process_incrementally():
    """Process ZIPs incrementally - automatically skips already-processed ones."""
    print("\n" + "=" * 80)
    print("Incremental Processing")
    print("=" * 80)

    input_dir = Path.home() / "Downloads" / "takeout_zips"
    output_dir = Path.home() / "Pictures" / "Google Photos"
    work_dir = Path.home() / "takeout_work"

    print(f"\nInput directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Work directory:   {work_dir}")

    # Check what's already been processed
    db_path = work_dir / "pipeline.db"
    check_processed_zips(db_path)

    print("\n" + "=" * 80)
    print("Starting Pipeline (will skip completed ZIPs)")
    print("=" * 80)

    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=output_dir,
        organize_layout="yyyy_mm",
        dry_run=False,
    )

    pipeline = Pipeline(config)
    pipeline.run()

    print("\n" + "=" * 80)
    print("Processing Complete")
    print("=" * 80)
    print("\nThe pipeline automatically:")
    print("  ✓ Skipped ZIPs that were already completed")
    print("  ✓ Processed any new ZIPs found in the input directory")
    print("  ✓ Resumed any ZIPs that were in progress")
    print("  ✓ Retried any ZIPs that had previously failed")

    # Show final status
    print("\n" + "=" * 80)
    check_processed_zips(db_path)


def simulate_adding_new_zips():
    """Show how to add new ZIPs and process them incrementally."""
    print("\n" + "=" * 80)
    print("Workflow: Adding New Takeout ZIPs")
    print("=" * 80)

    input_dir = Path.home() / "Downloads" / "takeout_zips"
    work_dir = Path.home() / "takeout_work"

    print("\nScenario: You've already processed some ZIPs and now have new ones.")
    print("\n1. Download new Takeout ZIPs from Google")
    print(f"2. Place them in: {input_dir}")
    print("3. Run the pipeline again")
    print("\nThe pipeline will:")
    print("  - Skip the ZIPs you already processed")
    print("  - Only process the new ZIPs")
    print("  - Update the same database and organized directory")

    print("\nBefore running, check current status:")
    db_path = work_dir / "pipeline.db"
    check_processed_zips(db_path)

    print("\n" + "=" * 80)
    print("To process the new ZIPs, simply run:")
    print("=" * 80)
    print("\n  python examples/basic_usage.py")
    print("\n  # or use the CLI:")
    print(f"  takeout-photos process --input-dir {input_dir}")


def main():
    """Demonstrate incremental processing workflow."""
    # Check what's already processed
    work_dir = Path.home() / "takeout_work"
    db_path = work_dir / "pipeline.db"
    check_processed_zips(db_path)

    # Show how to process incrementally
    print("\n" + "=" * 80)
    print("Key Benefit: Incremental Processing")
    print("=" * 80)
    print("\nYou can run the pipeline multiple times safely:")
    print("  • Add new ZIPs to the input directory")
    print("  • Run the pipeline again")
    print("  • It will skip ZIPs that are already completed")
    print("  • Only new ZIPs will be processed")
    print("\nThis makes it easy to:")
    print("  - Process very large Takeouts in batches")
    print("  - Resume after interruptions")
    print("  - Add new Google Photos exports later")

    # Uncomment to actually run processing:
    # process_incrementally()


if __name__ == "__main__":
    main()
