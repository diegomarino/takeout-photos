"""
Locate JSON metadata files for media files.

Handles Google Takeout's complex and inconsistent JSON naming patterns,
including truncated filenames, numbered suffixes, and global searches.
"""

from __future__ import annotations

from pathlib import Path

from takeout_photos.core.constants import JSON_PATTERNS


def find_json_for_media(media_path: Path, extracted_base: Path | None = None) -> Path | None:
    """
    Locate associated JSON metadata file for a media file.

    Google Takeout uses several naming patterns for JSON files that have evolved
    over time and vary by export batch. This function handles all known patterns.

    JSON Naming Patterns (handled):
        - photo.jpg.json (old standard)
        - photo.jpg.supplemental-metadata.json (new standard since Oct 2024)
        - Truncated variants when filename exceeds 46 chars before .json
        - Files with numbered suffixes: photo.jpg(1).json, photo(1).jpg.json

    Args:
        media_path: Path to media file to find JSON for
        extracted_base: Base directory containing all extracted ZIPs
                       (e.g., workdir/extracted/). If provided, enables
                       global JSON search across all ZIPs.

    Returns:
        Path to JSON metadata file if found, None otherwise

    Search Strategy:
        1. Search in same directory as media file (fast path)
        2. If not found and extracted_base provided, search globally across
           the extracted tree (legacy per-ZIP layout)

    Note:
        Google Takeout has inconsistent naming due to:
        - 46-character filename limit causing truncation
        - Different naming patterns for different export batches
        - Numbered suffixes for duplicates/multiple uploads
        - JSON files may be in a different ZIP than the media file

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.takeout.json_finder import find_json_for_media
        >>> media = Path("/extracted/Google Photos/IMG_1234.HEIC")
        >>> json_path = find_json_for_media(media)
        >>> print(json_path)
        /extracted/takeout-001/Google Photos/IMG_1234.HEIC.supplemental-metadata.json

        >>> # Global search across extracted tree (legacy per-ZIP layout)
        >>> extracted_base = Path("/workdir/extracted")
        >>> json_path = find_json_for_media(media, extracted_base)
    """

    def _try_patterns_in_directory(search_dir: Path, filename: str) -> Path | None:
        """
        Try all JSON patterns in a specific directory.

        Args:
            search_dir: Directory to search in
            filename: Media filename (without directory path)

        Returns:
            Path to JSON file if found, None otherwise
        """
        # Create a fake path with the filename in the search directory
        fake_media_path = search_dir / filename

        # Try all standard patterns
        for pattern in JSON_PATTERNS:
            json_path = pattern(fake_media_path)
            if json_path.exists():
                return json_path

        # Try patterns with numbered suffixes (1), (2), etc.
        for i in range(1, 10):
            for pattern in JSON_PATTERNS:
                # Try with number before extension: photo(1).jpg.json
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                numbered_name = f"{stem}({i}){suffix}"
                numbered_path = search_dir / numbered_name
                json_path = pattern(numbered_path)
                if json_path.exists():
                    return json_path

                # Try with number after extension: photo.jpg(1).json
                json_candidate = pattern(fake_media_path)
                json_with_number = (
                    json_candidate.parent / f"{json_candidate.stem}({i}){json_candidate.suffix}"
                )
                if json_with_number.exists():
                    return json_with_number

        # Try searching by truncated filename (46 char limit)
        if len(filename) > 46:
            truncated_base = filename[:46]
            for json_file in search_dir.glob(f"{truncated_base}*.json"):
                if json_file.is_file():
                    return json_file

        return None

    # PHASE 1: Search in same directory as media file (fast path)
    json_path = _try_patterns_in_directory(media_path.parent, media_path.name)
    if json_path:
        return json_path

    # PHASE 2: Global search across all extracted ZIPs if enabled
    if extracted_base and extracted_base.exists():
        filename = media_path.name

        # Search in all "Google Photos" directories across all ZIPs
        # Pattern: extracted/*/Takeout/Google Photos/
        for google_photos_dir in extracted_base.glob("*/Takeout/Google Photos"):
            if not google_photos_dir.is_dir():
                continue

            # Search recursively in this Google Photos directory
            for subdir in [google_photos_dir] + list(google_photos_dir.rglob("*")):
                if not subdir.is_dir():
                    continue

                json_path = _try_patterns_in_directory(subdir, filename)
                if json_path:
                    return json_path

    return None
