"""Diagnostics utilities (doctor command)."""

from __future__ import annotations

import logging

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.recovery import RecoveryManager


def cmd_doctor(config: Config | None = None) -> int:
    """
    Run system health checks and diagnostics.

    Level 1 (no workdir): Dependencies only
    Level 2 (with workdir): Full diagnostic using RecoveryManager in dry-run mode

    Args:
        config: Optional configuration. If None, only checks dependencies.

    Returns:
        0: All checks passed
        1: Warnings found (recovery issues detected)
        2: Errors found (missing dependencies)

    Example:
        >>> # Dependencies only
        >>> exit_code = cmd_doctor()
        >>>
        >>> # Full diagnostic
        >>> from takeout_photos.core.config import Config
        >>> config = Config(workdir="/path/to/workdir")
        >>> exit_code = cmd_doctor(config=config)
    """
    print("=" * 60)
    print("CHECKING DEPENDENCIES")
    print("=" * 60)

    # Level 1: Dependencies
    from takeout_photos.utils.dependencies import check_dependencies

    deps_ok = check_dependencies(verbose=True)

    if config is None:
        return 0 if deps_ok else 2

    # Level 2: Full diagnostic
    print()
    print("=" * 60)
    print(f"CHECKING PIPELINE HEALTH: {config.workdir}")
    print("=" * 60)

    # Type narrowing
    assert config.db_path is not None

    log = logging.getLogger(__name__)
    db = PipelineDB(config.db_path)

    # Run recovery in dry-run mode
    print("\nPIPELINE:")
    print("-" * 60)

    recovery_mgr = RecoveryManager(config, db, log, dry_run=True)
    stats = recovery_mgr.check_and_recover()

    # Summary
    print()
    print("=" * 60)
    if stats.total > 0:
        print(f"⚠️  {stats.total} issue(s) found")
        print("   → Run: takeout-photos process (will auto-recover)")
        print("=" * 60)
        return 1
    elif not deps_ok:
        print("❌ Dependency errors found")
        print("=" * 60)
        return 2
    else:
        print("✅ All checks passed")
        print("=" * 60)
        return 0
