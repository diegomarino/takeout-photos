"""
Takeout Photos - Process and organize Google Takeout photo exports.

A modular Python package for processing large Google Photos Takeout exports
with metadata preservation, deduplication, and organization.

Example:
    >>> from takeout_photos import Config, Pipeline
    >>> config = Config(workdir="/path/to/work")
    >>> pipeline = Pipeline(config)
    >>> pipeline.run()
"""

from __future__ import annotations

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.pipeline import Pipeline

__version__ = "1.0.4"

__all__ = [
    "__version__",
    "Config",
    "PipelineDB",
    "Pipeline",
]
