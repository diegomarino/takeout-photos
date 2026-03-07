"""
File format detection and extension correction.

Handles mismatched file extensions in Google Takeout exports by detecting
actual file format and correcting extensions as needed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


def correct_file_extension_fast(
    file_path: Path, real_type: str, existing_exif: dict[str, Any], log: logging.Logger
) -> Path:
    """
    Correct file extension if it doesn't match the real file type (optimized version).

    This is the fast version that receives existing_exif as a parameter instead of
    reading it again, avoiding a duplicate exiftool call. Use with get_file_type_and_exif().

    Args:
        file_path: Path to file with potentially incorrect extension
        real_type: Real file type (e.g., "JPEG", "MP4", "HEIC")
        existing_exif: EXIF data already read from the file
        log: Logger instance for debug/error messages

    Returns:
        Path to corrected file (or original if no correction needed)

    Process:
        1. Determine correct extension based on real_type
        2. If extension matches, return original file
        3. If mismatch, rename the file by appending correct extension
        4. Return new path

    Extension Mapping:
        - JPEG → .jpg (not .jpeg for consistency)
        - Other types → lowercase of type name (e.g., HEIC → .heic)

    Example:
        >>> import logging
        >>> from pathlib import Path
        >>> from takeout_photos.exif.format_detection import correct_file_extension_fast
        >>> log = logging.getLogger(__name__)
        >>> # File with .HEIC extension but actually JPEG format
        >>> corrected = correct_file_extension_fast(
        ...     Path("photo.HEIC"),
        ...     "JPEG",
        ...     {"DateTimeOriginal": "2021:01:01 12:00:00"},
        ...     log
        ... )
        >>> print(corrected)
        photo.HEIC.jpg

    Note:
        We don't use exiftool -o because it can't change file formats.
        The file already has its EXIF embedded, we just need to fix the extension.

        Extensions are always lowercase for consistency across platforms
        (macOS is case-insensitive by default, Linux is case-sensitive).

        The original extension is preserved by appending the new one to avoid
        filename collisions: IMG_6486.HEIC → IMG_6486.HEIC.jpg
    """
    # Map file types to extensions
    # Only specify special cases that don't map 1:1
    special_cases = {
        "JPEG": ".jpg",  # Not .jpeg
    }

    # Get extension: use special case or derive from type name (lowercase)
    correct_ext = special_cases.get(real_type, f".{real_type.lower()}")

    # Note: Always use lowercase extensions for consistency across platforms
    # macOS is case-insensitive by default, Linux is case-sensitive

    current_ext = file_path.suffix.lower()

    # Extension is correct, no change needed
    if current_ext == correct_ext:
        return file_path

    # Extension needs correction
    log.debug(
        f"Correcting extension: {file_path.name} "
        f"({current_ext} → {correct_ext}, real type: {real_type})"
    )

    # Append correct extension instead of replacing to avoid filename collisions
    # IMG_6486.HEIC (JPEG) → IMG_6486.HEIC.jpg
    new_path = Path(str(file_path) + correct_ext)

    # Simply rename the file - EXIF is already embedded in the file
    try:
        file_path.rename(new_path)
        log.debug(f"Successfully corrected extension: {file_path.name} → {new_path.name}")
        return new_path
    except Exception as e:
        log.error(f"Failed to rename {file_path.name}: {e}")
        return file_path
