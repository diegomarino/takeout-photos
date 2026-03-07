"""
Parse Google Takeout JSON metadata files.

Extracts photo capture timestamps and GPS coordinates from Google Takeout's
JSON metadata files, which accompany exported media files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_takeout_json(json_path: Path) -> dict[str, Any]:
    """
    Extract relevant metadata from Google Takeout JSON file.

    Parses JSON to extract photo capture timestamp and GPS coordinates.
    Handles both old and new Google Takeout formats.

    Args:
        json_path: Path to Google Takeout JSON metadata file

    Returns:
        Dictionary with extracted metadata fields:
            - photo_taken_ts (int): Unix timestamp of photo capture
            - geo_lat (float): GPS latitude coordinate
            - geo_lon (float): GPS longitude coordinate

        Returns empty dict if JSON is invalid or missing expected fields.

    Timestamp Sources (in priority order):
        1. photoTakenTime.timestamp - Primary source for photo capture time
        2. creationTime.timestamp - Fallback if photoTakenTime not available

    GPS Sources (first available):
        - geoData.latitude/longitude - Primary GPS source
        - geoDataExif.latitude/longitude - EXIF-based GPS data

    Note:
        GPS coordinates are only included if non-zero. Google Takeout
        sometimes includes (0.0, 0.0) as placeholder values which are invalid.

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.takeout.json_parser import parse_takeout_json
        >>> json_path = Path("IMG_1234.HEIC.supplemental-metadata.json")
        >>> metadata = parse_takeout_json(json_path)
        >>> print(metadata)
        {
            'photo_taken_ts': 1609459200,
            'geo_lat': 40.4168,
            'geo_lon': -3.7038
        }
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
        return {}

    result: dict[str, Any] = {}

    # Extract capture timestamp
    if "photoTakenTime" in data:
        ts = data["photoTakenTime"].get("timestamp")
        if ts:
            try:
                result["photo_taken_ts"] = int(ts)
            except (ValueError, TypeError):
                pass

    # Fallback to creationTime if photoTakenTime not available
    if "photo_taken_ts" not in result and "creationTime" in data:
        ts = data["creationTime"].get("timestamp")
        if ts:
            try:
                result["photo_taken_ts"] = int(ts)
            except (ValueError, TypeError):
                pass

    # Extract GPS coordinates
    geo = data.get("geoData") or data.get("geoDataExif") or {}
    lat = geo.get("latitude")
    lon = geo.get("longitude")

    # Only include coordinates if they're non-zero (0,0 is invalid)
    if lat and lon and (lat != 0.0 or lon != 0.0):
        result["geo_lat"] = lat
        result["geo_lon"] = lon

    return result
