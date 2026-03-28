"""Shared fixtures for stages tests."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB


@pytest.fixture
def config(tmp_path):
    """Create a test configuration."""
    workdir = tmp_path / "work"
    return Config(
        workdir=str(workdir),
        workers=2,
        dry_run=False,
    )


@pytest.fixture
def db(tmp_path):
    """Create a mock database."""
    mock_db = MagicMock(spec=PipelineDB)
    mock_db.conn = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.update_file = MagicMock()
    mock_db.update_zip_status = MagicMock()
    mock_db.get_files_for_zip = MagicMock(return_value=[])
    mock_db.register_file = MagicMock()
    mock_db.register_json_file = MagicMock()
    mock_db.find_json_for_media_db = MagicMock(return_value=None)
    return mock_db


@pytest.fixture
def real_db(tmp_path):
    """Create a real database for v3.0 tests."""
    db_path = tmp_path / "test_pipeline.db"
    db = PipelineDB(db_path)
    yield db
    db.close()


@pytest.fixture
def logger():
    """Create a test logger."""
    log = logging.getLogger("test")
    log.setLevel(logging.DEBUG)
    return log
