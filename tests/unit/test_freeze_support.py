"""Regression: multiprocessing.freeze_support() is called at the CLI entry points.

Without this call, a PyInstaller-frozen build crashes on any ProcessPoolExecutor
use (validate/hash stages): the frozen binary re-invokes itself to spawn workers,
and the multiprocessing bootstrap arguments (e.g. ``tracker_fd=11``) reach our
argparser, which rejects them and tears down the whole pool.

These tests execute the entry-point modules as ``__main__`` (matching how the
frozen binary runs ``__main__.py``) and assert freeze_support() runs before any
argument parsing.
"""

from __future__ import annotations

import multiprocessing
import runpy
import sys

import pytest


def test_package_main_calls_freeze_support_before_main(monkeypatch):
    """`python -m takeout_photos` (and the frozen entry) calls freeze_support first."""
    events: list[str] = []

    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: events.append("freeze_support"))
    # The __main__ module does `from takeout_photos.cli.main import main`, so
    # patching the attribute here makes the fresh import pick up our stub.
    monkeypatch.setattr("takeout_photos.cli.main.main", lambda: events.append("main"))
    monkeypatch.setattr(sys, "argv", ["takeout-photos"])

    runpy.run_module("takeout_photos", run_name="__main__")

    # freeze_support() MUST run, and MUST run before main() (before argparse).
    assert events == ["freeze_support", "main"]


def test_cli_main_module_calls_freeze_support(monkeypatch):
    """Running cli/main.py directly as __main__ also calls freeze_support first."""
    from takeout_photos.cli import main as main_mod

    events: list[str] = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: events.append("freeze_support"))
    # argv with no subcommand makes main() print help and sys.exit(0); we only
    # care that freeze_support ran before that happened.
    monkeypatch.setattr(sys, "argv", ["takeout-photos"])

    with pytest.raises(SystemExit):
        runpy.run_path(main_mod.__file__, run_name="__main__")

    assert "freeze_support" in events
