"""
Progress bar utilities and media file detection.

Provides a tqdm wrapper with fallback for progress bars and media file type checking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from takeout_photos.core.constants import MEDIA_EXTENSIONS

try:
    from tqdm import tqdm

    use_tqdm = True
except ImportError:
    tqdm = None
    use_tqdm = False


def progress_bar(
    iterable: Iterable[Any],
    total: int | None = None,
    desc: str | None = None,
    disable: bool = False,
) -> Iterable[Any]:
    """
    Wrapper for tqdm progress bar with graceful fallback.

    If tqdm is not installed, returns the plain iterable without progress indication.
    This allows the code to work with or without the optional tqdm dependency.

    Args:
        iterable: Iterable to wrap with progress bar
        total: Total number of items (if not determinable from iterable)
        desc: Description text to show with progress bar
        disable: Force disable progress bar even if tqdm is available

    Returns:
        tqdm-wrapped iterable if tqdm is available and not disabled,
        otherwise returns the plain iterable

    Example:
        >>> from takeout_photos.utils.progress import progress_bar
        >>> files = ["file1.jpg", "file2.jpg", "file3.jpg"]
        >>> for file in progress_bar(files, desc="Processing"):
        ...     # process file
        ...     pass
    """
    if use_tqdm and tqdm is not None and not disable:
        return tqdm(iterable, total=total, desc=desc)  # type: ignore[no-any-return]
    return iterable


def is_media_file(path: Path) -> bool:
    """
    Check if a file is a recognized media file (photo or video).

    Uses the file extension to determine if the file is a known media type.
    Case-insensitive comparison against MEDIA_EXTENSIONS.

    Args:
        path: File path to check

    Returns:
        True if file extension matches a known media type, False otherwise

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.utils.progress import is_media_file
        >>> is_media_file(Path("photo.jpg"))
        True
        >>> is_media_file(Path("document.pdf"))
        False
    """
    return path.suffix.lower() in MEDIA_EXTENSIONS
