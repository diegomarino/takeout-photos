"""Integration tests for Pipeline + RecoveryManager."""

from __future__ import annotations

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline


def test_pipeline_runs_recovery_on_startup(tmp_path):
    """Test that Pipeline runs recovery check on startup."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)

    # Create an intermediate ZIP (recovery issue)
    db.register_zip("test")
    db.update_zip_status("test", "extracting")

    # Start pipeline (should run recovery)
    pipeline = Pipeline(config)

    # Verify recovery ran and fixed the issue
    status = db.get_zip_status("test")
    assert status == "pending", "Recovery should have reset intermediate ZIP"

    # Verify recovery was logged with correct details
    history = db.get_recovery_history(limit=1)
    assert len(history) > 0, "Recovery should be logged"

    # Verify log entry content
    log_entry = history[0]
    assert log_entry["recovery_type"] == "intermediate_zips", "Should log intermediate_zips type"
    assert log_entry["affected_count"] == 1, "Should log 1 affected ZIP"
    assert log_entry["resolved"] == 1, "Should be marked as resolved"
    assert "details" in log_entry, "Should include details"

    pipeline.close()


def test_pipeline_recovery_respects_process_lock(tmp_path):
    """Test that recovery doesn't run if another pipeline is active."""
    config = Config(workdir=tmp_path)

    # Start first pipeline
    pipeline1 = Pipeline(config)

    # Try to start second pipeline (should fail due to lock)
    with pytest.raises(RuntimeError, match="already running"):
        Pipeline(config)

    pipeline1.close()
