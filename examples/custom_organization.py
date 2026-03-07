#!/usr/bin/env python3
"""Custom organization example for takeout-photos.

This example shows how to:
- Organize photos to an external drive
- Use different date formats (YYYY vs YYYY-MM)
- Clean up ZIPs after successful extraction
"""

from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


def example_external_drive():
    """Organize photos directly to an external drive with year-only folders."""
    print("=" * 80)
    print("Example 1: External Drive Organization (YYYY format)")
    print("=" * 80)

    # Organize to external drive mounted at /Volumes/Photos
    # On Windows, this might be "D:/Photos" or similar
    input_dir = Path.home() / "Downloads" / "takeout_zips"
    external_drive = Path("/Volumes/Photos")  # Mac/Linux
    # external_drive = Path("D:/Photos")  # Windows example
    work_dir = Path.home() / "takeout_work"

    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=external_drive / "Google Photos",
        organize_layout="yyyy",  # Year-only folders (simpler structure)
        dry_run=False,
    )

    print(f"\nOrganizing to external drive: {config.organized_dir}")
    print(f"Layout: {config.organize_layout} (creates folders like 2023/, 2024/)")

    pipeline = Pipeline(config)
    pipeline.run()

    print(f"\n✓ Photos organized to: {config.organized_dir}")
    print("  Structure:")
    print("    2022/")
    print("      photo1.jpg")
    print("      photo2.png")
    print("    2023/")
    print("      photo3.jpg")
    print("    ...")


def example_cleanup_zips():
    """Process Takeout ZIPs and delete them after successful extraction."""
    print("\n" + "=" * 80)
    print("Example 2: Auto-cleanup ZIPs after extraction")
    print("=" * 80)

    input_dir = Path.home() / "Downloads" / "takeout_zips"
    output_dir = Path.home() / "Pictures" / "Google Photos"
    work_dir = Path.home() / "takeout_work"

    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=output_dir,
        delete_zips_after_extract=True,  # Delete ZIPs after successful extraction
        dry_run=True,  # Preview mode - doesn't actually delete
    )

    print("\n⚠️  This example runs in DRY RUN mode (no actual deletion)")
    print("    Set dry_run=False to actually delete ZIPs")
    print("\nThis will:")
    print("  1. Extract each ZIP")
    print("  2. Process the contents")
    print("  3. Delete the ZIP only if extraction was successful")
    print("  4. Keep the ZIP if there were any errors")

    pipeline = Pipeline(config)
    pipeline.run()

    print("\n⚠️  Use with caution! Make sure you have backups before deleting ZIPs.")


def example_year_month_organization():
    """Use YYYY-MM format for more granular organization."""
    print("\n" + "=" * 80)
    print("Example 3: Year-Month Organization (YYYY-MM format)")
    print("=" * 80)

    input_dir = Path.home() / "Downloads" / "takeout_zips"
    output_dir = Path.home() / "Pictures" / "Google Photos by Month"
    work_dir = Path.home() / "takeout_work"

    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=output_dir,
        organize_layout="yyyy_mm",  # Year-month folders (more detailed)
        dry_run=False,
    )

    print(f"\nOrganizing with monthly folders: {config.organized_dir}")
    print(f"Layout: {config.organize_layout}")

    pipeline = Pipeline(config)
    pipeline.run()

    print(f"\n✓ Photos organized to: {config.organized_dir}")
    print("  Structure:")
    print("    2023-01/")
    print("      photo1.jpg")
    print("    2023-02/")
    print("      photo2.jpg")
    print("    2023-12/")
    print("      photo3.jpg")
    print("    ...")


def main():
    """Run all custom organization examples."""
    # Choose which example to run:

    # Example 1: External drive with year-only folders
    example_external_drive()

    # Example 2: Show how to cleanup ZIPs (CLI only)
    example_cleanup_zips()

    # Example 3: Year-month organization
    # example_year_month_organization()


if __name__ == "__main__":
    main()
