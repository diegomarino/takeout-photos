#!/usr/bin/env python3
"""Basic usage example for takeout-photos.

This example demonstrates the simplest way to process Google Photos Takeout ZIPs.
The pipeline will extract, validate, process metadata, organize, and deduplicate your photos.
"""

from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


def main():
    """Process Google Photos Takeout ZIPs with default settings."""
    print("=" * 80)
    print("Google Photos Takeout - Basic Processing Example")
    print("=" * 80)

    # Step 1: Define your paths
    # This is where your Takeout ZIP files are located
    input_dir = Path.home() / "Downloads" / "takeout_zips"

    # This is where the final organized photos will be placed
    output_dir = Path.home() / "Pictures" / "Google Photos Organized"

    # This is the working directory for extraction and processing
    work_dir = Path.home() / "takeout_work"

    print(f"\nInput directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Work directory:   {work_dir}")

    # Step 2: Create configuration
    # The Config object holds all settings for the pipeline
    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=output_dir,
        organize_layout="yyyy_mm",  # Organize photos by year and month
        dry_run=False,  # Set to True to preview actions without making changes
    )

    print("\nConfiguration:")
    print(f"  - Layout:         {config.organize_layout}")
    print(f"  - Workers:        {config.workers}")
    print(f"  - Dry run:        {config.dry_run}")

    # Step 3: Create and run the pipeline
    # The Pipeline automatically handles all 8 stages:
    # 1. Extract ZIPs
    # 2. Validate files
    # 3. Process metadata
    # 4. Compute hashes
    # 5. Stage files
    # 6. Deduplicate
    # 7. Organize by date
    # 8. Quality control
    print("\n" + "=" * 80)
    print("Starting pipeline...")
    print("=" * 80)

    pipeline = Pipeline(config)
    pipeline.run()

    print("\n" + "=" * 80)
    print("Processing complete!")
    print("=" * 80)
    print(f"\nYour organized photos are in: {output_dir}")
    print("\nFolder structure:")
    print("  YYYY-MM/")
    print("    photo1.jpg")
    print("    photo2.png")
    print("    ...")

    # Step 4: Check the database for statistics
    db_path = work_dir / "pipeline.db"
    print(f"\nPipeline database: {db_path}")
    print("You can query this database to see processing details and statistics.")


if __name__ == "__main__":
    main()
