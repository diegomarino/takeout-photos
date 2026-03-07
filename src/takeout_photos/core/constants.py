"""
Shared constants for the takeout_photos package.

This module contains file extensions and naming patterns used throughout
the pipeline for identifying media files and associated metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

# Media file extensions recognized by the pipeline
MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".gif",
    ".webp",
    ".bmp",
    ".raw",
    ".cr2",
    ".nef",
    ".arw",
    ".mov",
    ".mp4",
    ".mpg",
    ".avi",
    ".mkv",
    ".m4v",
    ".3gp",
    ".webm",
}

# Google Takeout JSON naming patterns
# Google uses several patterns for associated JSON metadata files.
# Includes standard formats, truncated formats (Google truncates at 46 chars),
# and various abbreviated forms.
JSON_PATTERNS: list[Callable[[Path], Path]] = [
    # Standard formats
    lambda p: p.with_suffix(p.suffix + ".json"),  # photo.jpg.json (old standard)
    lambda p: p.with_suffix(
        p.suffix + ".supplemental-metadata.json"
    ),  # photo.jpg.supplemental-metadata.json (new standard)
    # Truncated formats (Google truncates at 46 chars before .json)
    lambda p: p.with_suffix(p.suffix + ".supplemental-metada.json"),  # truncated at 46
    lambda p: p.with_suffix(p.suffix + ".supplemental-metad.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental-meta.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental-met.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental-me.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental-m.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental-.json"),  # more truncated
    lambda p: p.with_suffix(p.suffix + ".supplemental.json"),  # truncated
    lambda p: p.with_suffix(p.suffix + ".supplement.json"),  # variant
    lambda p: p.with_suffix(p.suffix + ".supple.json"),  # truncated variant
    lambda p: p.with_suffix(p.suffix + ".suppl.json"),  # abbreviated
    lambda p: p.with_suffix(p.suffix + ".supp.json"),  # more abbreviated
    lambda p: p.with_suffix(p.suffix + ".sup.json"),  # very abbreviated
    lambda p: p.with_suffix(p.suffix + ".s.json"),  # extremely abbreviated
    # Without original extension
    lambda p: p.with_suffix(".json"),  # photo.json
    lambda p: p.parent / (p.stem + ".json"),  # photo.json (stem only)
]
