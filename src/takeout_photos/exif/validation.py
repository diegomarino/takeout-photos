"""
EXIF metadata validation.

Validates EXIF date/time values to detect suspicious or incorrect metadata
that is common in Google Takeout exports.
"""

from __future__ import annotations

from datetime import datetime


def is_suspicious_date(exif_date: str) -> bool:
    """
    Check if an EXIF date is suspicious or likely incorrect.

    EXIF dates in Google Takeout exports are often incorrect or use placeholder
    values. This function identifies common problematic date patterns.

    Args:
        exif_date: EXIF date string in format "YYYY:MM:DD HH:MM:SS"

    Returns:
        True if date is suspicious and should not be trusted, False otherwise

    Suspicious Date Patterns:
        - Unix epoch: 1970:01:01 (default for uninitialized timestamps)
        - Y2K default: 2000:01:01 (common camera default)
        - Before digital photography era: < 1995
        - Future dates: > current date

    Example:
        >>> from takeout_photos.exif.validation import is_suspicious_date
        >>> is_suspicious_date("1970:01:01 00:00:00")
        True
        >>> is_suspicious_date("2000:01:01 00:00:00")
        True
        >>> is_suspicious_date("2021:06:15 14:30:00")
        False
        >>> is_suspicious_date("invalid date")
        True

    Note:
        Empty strings and unparseable dates are considered suspicious.
        This is a conservative approach - when in doubt, treat as suspicious
        and prefer JSON metadata from Google Takeout.

    Why These Dates Are Suspicious:
        - **1970:01:01**: Unix epoch (timestamp 0), used when date is unknown
        - **2000:01:01**: Common default in cameras with dead CMOS battery
        - **< 1995**: Before widespread consumer digital photography
        - **Future dates**: Likely incorrect clock settings or timezone issues
    """
    if not exif_date:
        return True

    try:
        # Parse EXIF date
        dt = datetime.strptime(exif_date, "%Y:%m:%d %H:%M:%S")

        # Check for epoch dates
        if dt.year == 1970 and dt.month == 1 and dt.day == 1:
            return True
        if dt.year == 2000 and dt.month == 1 and dt.day == 1:
            return True

        # Check for too old (before widespread digital photography)
        if dt.year < 1995:
            return True

        # Check for future dates (allow 1 day slack for timezone issues)
        now = datetime.now()
        if dt > now:
            return True

        return False

    except ValueError:
        # Unparseable dates are suspicious
        return True
