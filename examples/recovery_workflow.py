#!/usr/bin/env python3
"""Recovery workflow example for takeout-photos.

This example demonstrates the recovery system that handles interruptions,
errors, and corrupted state. The pipeline can recover automatically or
you can manually trigger recovery operations.
"""

from pathlib import Path

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline
from takeout_photos.stages.recovery_system import RecoverySystem


def analyze_recovery_state(work_dir: Path):
    """Analyze the current pipeline state and show what can be recovered."""
    print("=" * 80)
    print("Recovery State Analysis")
    print("=" * 80)

    db_path = work_dir / "pipeline.db"

    if not db_path.exists():
        print(f"\n✗ No database found at: {db_path}")
        print("  Nothing to recover - this is a fresh start.")
        return

    db = PipelineDB(db_path)
    recovery = RecoverySystem(db, work_dir)

    print(f"\nAnalyzing: {db_path}")
    print("\nRecovery Analysis:")
    print("-" * 80)

    # Analyze the state
    state = recovery.analyze_state()

    print(f"Incomplete ZIPs:        {state['incomplete_zips']}")
    print(f"Orphaned extracts:      {state['orphaned_extracts']}")
    print(f"Orphaned staged:        {state['orphaned_staged']}")
    print(f"Corrupted intermediate: {state['corrupted_intermediate']}")
    print(f"Inconsistent records:   {state['inconsistent_db_records']}")

    total_issues = sum(state.values())

    if total_issues == 0:
        print("\n✓ No issues found - pipeline state is clean!")
    else:
        print(f"\n⚠️  Found {total_issues} issue(s) that can be recovered")

    return state


def demonstrate_auto_recovery():
    """Show how the pipeline automatically recovers on startup."""
    print("\n" + "=" * 80)
    print("Automatic Recovery on Pipeline Start")
    print("=" * 80)

    input_dir = Path.home() / "Downloads" / "takeout_zips"
    output_dir = Path.home() / "Pictures" / "Google Photos"
    work_dir = Path.home() / "takeout_work"

    print("\nThe pipeline automatically performs recovery when you start it:")
    print("\n1. Checks for incomplete ZIPs")
    print("2. Detects orphaned files")
    print("3. Cleans up corrupted state")
    print("4. Resumes from the last completed stage")

    print("\n" + "=" * 80)
    print("Starting pipeline with auto-recovery...")
    print("=" * 80)

    config = Config(
        workdir=work_dir,
        zips_dir=input_dir,
        organized_dir=output_dir,
        organize_layout="yyyy_mm",
        dry_run=False,
    )

    pipeline = Pipeline(config)

    # The pipeline will automatically call recovery on startup
    # You don't need to do anything special!
    pipeline.run()

    print("\n✓ Pipeline completed with automatic recovery")


def demonstrate_manual_recovery():
    """Show how to manually trigger recovery operations."""
    print("\n" + "=" * 80)
    print("Manual Recovery Operations")
    print("=" * 80)

    work_dir = Path.home() / "takeout_work"
    db_path = work_dir / "pipeline.db"

    if not db_path.exists():
        print(f"\n✗ No database found at: {db_path}")
        print("  Run the pipeline first to create the database.")
        return

    print("\nManual recovery is useful for:")
    print("  • Inspecting what needs recovery before running the pipeline")
    print("  • Cleaning up after errors without reprocessing")
    print("  • Debugging pipeline state issues")

    # Create recovery system
    db = PipelineDB(db_path)
    recovery = RecoverySystem(db, work_dir)

    # Analyze current state
    print("\n" + "-" * 80)
    state = recovery.analyze_state()

    if sum(state.values()) == 0:
        print("✓ No recovery needed - state is clean")
        return

    # Show what will be recovered
    print("\n" + "-" * 80)
    print("Recovery operations that will be performed:")

    if state["incomplete_zips"] > 0:
        print(f"  • Reset {state['incomplete_zips']} incomplete ZIP(s)")

    if state["orphaned_extracts"] > 0:
        print(f"  • Clean up {state['orphaned_extracts']} orphaned extract folder(s)")

    if state["orphaned_staged"] > 0:
        print(f"  • Remove {state['orphaned_staged']} orphaned staged file(s)")

    if state["corrupted_intermediate"] > 0:
        print(f"  • Delete {state['corrupted_intermediate']} corrupted intermediate ZIP(s)")

    if state["inconsistent_db_records"] > 0:
        print(f"  • Fix {state['inconsistent_db_records']} inconsistent database record(s)")

    # Perform recovery
    print("\n" + "-" * 80)
    print("Performing recovery...")
    recovery.recover_all()
    print("✓ Recovery complete!")

    # Verify clean state
    print("\n" + "-" * 80)
    print("Verifying recovery...")
    final_state = recovery.analyze_state()

    if sum(final_state.values()) == 0:
        print("✓ All issues resolved!")
    else:
        print("⚠️  Some issues remain:")
        print(final_state)


def handle_common_scenarios():
    """Show how recovery handles common error scenarios."""
    print("\n" + "=" * 80)
    print("Common Recovery Scenarios")
    print("=" * 80)

    print("\n1. Pipeline Interrupted (Ctrl+C, system crash)")
    print("   ↳ Auto-recovery: Resumes from last completed stage")
    print("   ↳ No data loss: Database tracks all progress")

    print("\n2. Disk Full During Processing")
    print("   ↳ Auto-recovery: Cleans up partial files")
    print("   ↳ Resets affected ZIPs to retry")

    print("\n3. Corrupted ZIP File")
    print("   ↳ Auto-recovery: Marks ZIP as failed")
    print("   ↳ Continues processing other ZIPs")

    print("\n4. Orphaned Files After Manual Cleanup")
    print("   ↳ Auto-recovery: Detects and removes orphaned files")
    print("   ↳ Syncs database with actual file system state")

    print("\n5. Inconsistent Database State")
    print("   ↳ Auto-recovery: Fixes record inconsistencies")
    print("   ↳ Validates all ZIPs and file references")

    print("\n" + "=" * 80)
    print("Recovery is Automatic and Safe")
    print("=" * 80)
    print("\n✓ Just run the pipeline again - it handles everything!")
    print("✓ No manual intervention needed in most cases")
    print("✓ Use 'analyze_state()' to inspect before recovery")


def main():
    """Demonstrate the recovery workflow."""
    work_dir = Path.home() / "takeout_work"

    # Step 1: Analyze current state
    print("\nStep 1: Analyze Recovery State")
    print("-" * 80)
    analyze_recovery_state(work_dir)

    # Step 2: Explain auto-recovery
    print("\n\nStep 2: Automatic Recovery")
    print("-" * 80)
    print("\nThe pipeline automatically recovers on startup.")
    print("You don't need to do anything special!")
    print("\nTo see auto-recovery in action:")
    print("  1. Start the pipeline")
    print("  2. Interrupt it (Ctrl+C)")
    print("  3. Start it again")
    print("  4. Watch it resume from where it left off")

    # Step 3: Show manual recovery (if needed)
    db_path = work_dir / "pipeline.db"
    if db_path.exists():
        print("\n\nStep 3: Manual Recovery (optional)")
        print("-" * 80)
        print("\nUncomment the line below to trigger manual recovery:")
        print("# demonstrate_manual_recovery()")

    # Step 4: Explain common scenarios
    handle_common_scenarios()

    # Uncomment to actually run auto-recovery:
    # demonstrate_auto_recovery()


if __name__ == "__main__":
    main()
