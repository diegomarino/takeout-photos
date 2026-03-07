"""
Command-line interface entry point.

Main function with argparse configuration for takeout-photos CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from takeout_photos import __version__
from takeout_photos.cli.commands import cmd_process, cmd_recovery, cmd_reset, cmd_status
from takeout_photos.core.config import Config


def main() -> None:
    """
    Command-line interface entry point.

    Parses arguments and dispatches to appropriate command handler.

    Commands:
        process: Run the full pipeline
        status: Display current state
        reset: Reset pipeline state

    Global options:
        --workdir: Base directory for all operations (required for commands)
        --doctor: Run system health checks and diagnostics (optional workdir)
        --workers: Number of parallel workers (default: 4)
        --dry-run: Simulate without making changes
        --verbose: Enable debug logging
        --layout: Organization layout (yyyy_mm or yyyy, default: yyyy_mm)
        --organized-dir: Custom output directory for organized photos
        --keep-extracted-files: Preserve extracted/ after organizing
        --delete-zips-after-extract: Delete ZIPs after extraction
        --skip-deps-check: Skip dependency verification

    Example:
        $ takeout-photos --doctor
        $ takeout-photos --workdir ~/work --doctor
        $ takeout-photos --workdir ~/work process
        $ takeout-photos --workdir ~/work status
        $ takeout-photos --workdir ~/work reset --zip takeout-001.zip
    """
    parser = argparse.ArgumentParser(
        prog="takeout-photos",
        description="Google Photos Takeout Pipeline - Process and organize photo exports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run system diagnostics (dependencies only)
  takeout-photos --doctor

  # Run full diagnostics with pipeline health check
  takeout-photos --workdir ~/google_takeout_work --doctor

  # Process all ZIPs in workdir/
  takeout-photos --workdir ~/google_takeout_work process

  # View current status
  takeout-photos --workdir ~/google_takeout_work status

  # Reset a specific ZIP with errors
  takeout-photos --workdir ~/google_takeout_work reset --zip takeout-001.zip

  # Reset entire pipeline (requires confirmation)
  takeout-photos --workdir ~/google_takeout_work reset

  # Run recovery check and fix inconsistencies
  takeout-photos --workdir ~/google_takeout_work recovery

  # Run recovery in diagnostic mode (detect only, no fixes)
  takeout-photos --workdir ~/google_takeout_work recovery --dry-run

  # Dry run to see what would happen
  takeout-photos --workdir ~/google_takeout_work --dry-run process

  # Use 8 parallel workers for faster processing
  takeout-photos --workdir ~/google_takeout_work --workers 8 process

  # Organize by year only (YYYY instead of YYYY/MM)
  takeout-photos --workdir ~/google_takeout_work --layout yyyy process

  # Prefix filenames with date for better sorting
  takeout-photos --workdir ~/work --dated-filenames process

  # Custom output directory
  takeout-photos --workdir ~/work --organized-dir /Volumes/Photos/Library process

  # Space-constrained mode: delete ZIPs after extraction
  takeout-photos --workdir ~/work --delete-zips-after-extract process

  # Keep extracted files for debugging
  takeout-photos --workdir ~/work --keep-extracted-files process

For more information, visit: https://github.com/your-repo/takeout-photos
        """,
    )

    # Global options
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--workdir",
        help="Base working directory (ZIP files should be in this directory)",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run system health checks and diagnostics",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers for hashing (default: 4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without making changes (for testing)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--layout",
        choices=["yyyy_mm", "yyyy"],
        default="yyyy_mm",
        help="Organization layout: yyyy_mm (2023/05/) or yyyy (2023/) (default: yyyy_mm)",
    )
    parser.add_argument(
        "--skip-deps-check",
        action="store_true",
        help="Skip dependency check (advanced users only)",
    )
    parser.add_argument(
        "--delete-zips-after-extract",
        action="store_true",
        help="[DESTRUCTIVE] Delete original ZIP files after successful extraction",
    )
    parser.add_argument(
        "--organized-dir",
        type=Path,
        help="Output directory for organized photos (default: workdir/organized_media)",
    )
    parser.add_argument(
        "--keep-extracted-files",
        action="store_true",
        help="Preserve extracted/ files after organizing (default: auto-delete for space savings)",
    )
    parser.add_argument(
        "--dated-filenames",
        action="store_true",
        help="Prefix filenames with date (YYYY-MM-DD_) when organizing",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=100,
        help="Commit database every N files/hashes (default: 100, range: 10-1000)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # process command
    subparsers.add_parser(
        "process",
        help="Process all ZIPs through complete pipeline",
        description="Extract, validate, apply metadata, deduplicate, and organize photos",
    )

    # status command
    subparsers.add_parser(
        "status",
        help="View current pipeline status",
        description="Display processing state, file counts, and disk usage",
    )

    # reset command
    sub_reset = subparsers.add_parser(
        "reset",
        help="Reset pipeline state",
        description="Reset specific ZIP or entire pipeline (with confirmation)",
    )
    sub_reset.add_argument(
        "--zip",
        help="Specific ZIP to reset (if not provided, resets entire pipeline)",
    )

    # recovery command
    sub_recovery = subparsers.add_parser(
        "recovery",
        help="Run recovery check and fix inconsistencies",
        description="Detect and fix pipeline inconsistencies (intermediate ZIPs, orphaned files, etc.)",
    )
    sub_recovery.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect issues without fixing them (diagnostic mode)",
    )

    # Show friendly message if run with no arguments
    if len(sys.argv) == 1:
        print("takeout-photos - Google Photos Takeout Organizer\n")
        print("Quick start:")
        print("  takeout-photos --doctor                    # Check if dependencies are installed")
        print("  takeout-photos --workdir ~/work process    # Process Google Takeout ZIPs")
        print("  takeout-photos --help                      # Show all options\n")
        print("Common commands:")
        print("  process   - Process and organize all Takeout ZIPs")
        print("  status    - View current pipeline status")
        print("  reset     - Reset pipeline state")
        print("  recovery  - Fix inconsistencies\n")
        print("For detailed help: takeout-photos --help")
        sys.exit(0)

    # Parse arguments
    args = parser.parse_args()

    # Handle --doctor flag (special case: works without workdir)
    if args.doctor:
        from takeout_photos.utils.diagnostics import cmd_doctor

        # Doctor with workdir if provided
        config = None
        if args.workdir:
            config = Config(workdir=Path(args.workdir))

        exit_code = cmd_doctor(config=config)
        sys.exit(exit_code)

    # Require workdir for all other commands
    if not args.workdir:
        parser.error("--workdir is required (unless using --doctor)")

    # Show help if no command provided
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create configuration (dependency check will happen inside Pipeline init)
    config = Config(
        workdir=args.workdir,
        workers=args.workers,
        dry_run=args.dry_run,
        verbose=args.verbose,
        organize_layout=args.layout,
        delete_zips_after_extract=args.delete_zips_after_extract,
        dated_filenames=args.dated_filenames,
        organized_dir=args.organized_dir,
        keep_extracted_files=args.keep_extracted_files,
        skip_deps_check=args.skip_deps_check,
        checkpoint_interval=args.checkpoint_interval,
    )

    # Dispatch to command handler
    try:
        if args.command == "process":
            cmd_process(config)
        elif args.command == "status":
            cmd_status(config)
        elif args.command == "reset":
            cmd_reset(config, args.zip)
        elif args.command == "recovery":
            cmd_recovery(config, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Pipeline state saved - run again to resume.")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
