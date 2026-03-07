"""Integration tests for process lock mechanism."""

from __future__ import annotations

import os

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.pipeline import Pipeline


def test_process_lock_prevents_concurrent_execution(tmp_path):
    """Test that process lock prevents multiple pipeline instances."""
    config = Config(workdir=tmp_path)

    # Start first pipeline (acquires lock)
    pipeline1 = Pipeline(config)

    # Try to start second pipeline
    with pytest.raises(RuntimeError, match="already running"):
        Pipeline(config)

    # Cleanup
    pipeline1.close()


def test_process_lock_released_on_close(tmp_path):
    """Test that lock is released when pipeline closes."""
    config = Config(workdir=tmp_path)

    # Start and close first pipeline
    pipeline1 = Pipeline(config)
    pipeline1.close()

    # Should be able to start second pipeline
    pipeline2 = Pipeline(config)
    pipeline2.close()  # No exception


def test_process_lock_handles_stale_lock(tmp_path):
    """Test that stale locks from dead processes are removed."""
    config = Config(workdir=tmp_path)
    lock_file = config.workdir / ".pipeline.lock"

    # Create stale lock with fake PID
    lock_file.write_text("999999")  # PID unlikely to exist

    # Should detect stale lock and take over
    pipeline = Pipeline(config)

    # Verify lock has current PID
    assert lock_file.read_text().strip() == str(os.getpid())

    pipeline.close()
