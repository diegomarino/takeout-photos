"""
Pytest configuration and shared fixtures for takeout_photos tests.

This module provides reusable fixtures for all test modules, including:
- Temporary directories and database paths
- Test database instances
- Sample test data
"""

from __future__ import annotations

import pytest

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB


@pytest.fixture
def temp_dir(tmp_path):
    """
    Provide a temporary directory for tests.

    Args:
        tmp_path: Pytest built-in fixture for temporary directories

    Returns:
        Path object to temporary directory
    """
    return tmp_path


@pytest.fixture
def test_db_path(temp_dir):
    """
    Provide a temporary database file path.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to temporary database file
    """
    return temp_dir / "test_pipeline.db"


@pytest.fixture
def db(test_db_path):
    """
    Provide a fresh PipelineDB instance for testing.

    Creates a new database with schema initialized, and cleans up
    after the test completes.

    Args:
        test_db_path: Temporary database path fixture

    Yields:
        PipelineDB instance with initialized schema

    Cleanup:
        Closes database connection and removes file
    """
    database = PipelineDB(test_db_path)
    yield database
    database.close()
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def test_config(temp_dir):
    """
    Provide a test Config instance with temporary directories.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Config instance pointing to temporary workdir
    """
    return Config(workdir=temp_dir)
