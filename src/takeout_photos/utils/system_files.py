"""System file detection utilities.

Filters OS metadata and temporary files that should not be processed
as media files or Google Takeout content.
"""

from __future__ import annotations

from pathlib import Path


def should_ignore_path(path: Path) -> bool:
    """
    Check if a path should be ignored (OS system files).

    Filters out operating system metadata and temporary files that
    should not be processed as media files or Google Takeout content.

    Args:
        path: File or directory path to check

    Returns:
        True if the path should be ignored, False otherwise

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.utils.system_files import should_ignore_path
        >>> should_ignore_path(Path("._photo.jpg"))
        True
        >>> should_ignore_path(Path("_7A_0520.jpg"))
        False
        >>> should_ignore_path(Path(".DS_Store"))
        True
    """
    name = path.name

    # AppleDouble resource forks (macOS) - PRIORITY
    if name.startswith("._"):
        return True

    # macOS system files/folders
    if name in {".DS_Store", ".Spotlight-V100", ".Trashes", ".TemporaryItems", ".fseventsd"}:
        return True

    # Windows system files (case-insensitive)
    if name.lower() in {"thumbs.db", "desktop.ini", "ehthumbs.db"}:
        return True

    # Linux system files
    if name == ".directory" or name.startswith(".nfs"):
        return True

    # Check for system directories in path
    parts = path.parts
    if "__MACOSX" in parts or "$RECYCLE.BIN" in parts:
        return True

    if any(p.startswith(".Trash-") for p in parts):
        return True

    return False
