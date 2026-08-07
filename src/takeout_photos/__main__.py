"""
Entry point for python -m takeout_photos.

Allows running the CLI as: python -m takeout_photos

This is also the entry point PyInstaller bundles (see pyinstaller.spec), which
is why multiprocessing.freeze_support() is called here.
"""

from __future__ import annotations

import multiprocessing

from takeout_photos.cli.main import main

if __name__ == "__main__":
    # MUST be the first call, before any argument parsing.
    #
    # In a PyInstaller-frozen build, sys.executable is the bundled CLI binary
    # itself. When ProcessPoolExecutor (stages/validate.py, stages/hash.py)
    # spawns worker/resource-tracker subprocesses, multiprocessing re-invokes
    # sys.executable with bootstrap arguments like "tracker_fd=11" and
    # "from multiprocessing.resource_tracker import main;main(5)". Without
    # freeze_support(), those arguments reach our argparser, which rejects them
    # as an invalid command and the whole pool dies ("A process in the process
    # pool was terminated abruptly"). freeze_support() intercepts that bootstrap
    # and runs the worker instead of falling through to main().
    #
    # In a normal (non-frozen) run this is a harmless no-op.
    multiprocessing.freeze_support()
    main()
