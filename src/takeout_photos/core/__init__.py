"""
Core module for the takeout_photos package.

This module contains fundamental building blocks:
- Config: Configuration dataclass
- PipelineDB: SQLite database for state management
- Pipeline: Main pipeline orchestrator
- Constants: Shared constants and patterns
"""

from __future__ import annotations

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline

__all__ = ["Config", "PipelineDB", "Pipeline"]
