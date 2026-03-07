"""
EXIF metadata operations using exiftool.

Provides wrappers for reading and writing EXIF metadata, with optimized
batch operations and combined file type + metadata reading.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_exiftool_path() -> str:
    """
    Get path to exiftool, preferring bundled version in PyInstaller.

    When running from a PyInstaller bundle, uses the bundled exiftool.
    Otherwise, falls back to system exiftool in PATH.

    Returns:
        Path to exiftool executable

    Raises:
        RuntimeError: If exiftool is not found

    Example:
        >>> from takeout_photos.exif.operations import get_exiftool_path
        >>> exiftool = get_exiftool_path()
        >>> print(f"Using exiftool: {exiftool}")

    Note:
        For PyInstaller bundles, exiftool and its lib/ directory must be
        bundled using the pyinstaller.spec datas configuration.
    """
    # Check if running from PyInstaller bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(str(meipass)) / "exiftool"
        if bundled.exists():
            return str(bundled)

    # Fallback: system exiftool in PATH
    system_exiftool = shutil.which("exiftool")
    if system_exiftool:
        return system_exiftool

    raise RuntimeError(
        "exiftool not found. Install from https://exiftool.org\n"
        "macOS: brew install exiftool\n"
        "Ubuntu/Debian: sudo apt install exiftool\n"
        "Windows: Download from https://exiftool.org"
    )


def write_exif_warning(warning_file: Path | None, message: str) -> None:
    """
    Append exiftool warning/error to dedicated warnings file.

    Args:
        warning_file: Path to exif_warnings file, or None to skip
        message: Raw stderr output from exiftool

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.exif.operations import write_exif_warning
        >>> warning_file = Path("logs/warnings.txt")
        >>> write_exif_warning(warning_file, "Warning: Issue detected\\n")
    """
    if warning_file and message.strip():
        with open(warning_file, "a", encoding="utf-8") as f:
            f.write(message)
            if not message.endswith("\n"):
                f.write("\n")


def run_exiftool(
    args: list[str],
    capture_output: bool = True,
    exif_warnings_file: Path | None = None,
    log: logging.Logger | None = None,
) -> subprocess.CompletedProcess:
    """
    Execute exiftool with specified arguments.

    This is a thin wrapper to centralize exiftool invocation for all
    EXIF operations. Ensures consistent error handling and output capture.

    Args:
        args: List of command-line arguments for exiftool (without 'exiftool' itself)
        capture_output: If True, capture stdout/stderr for processing
        exif_warnings_file: Optional path to append stderr warnings
        log: Optional logger to log critical errors to console

    Returns:
        CompletedProcess instance with result, stdout, stderr, and returncode

    Raises:
        FileNotFoundError: If exiftool is not installed or not in PATH

    Example:
        >>> from takeout_photos.exif.operations import run_exiftool
        >>> from pathlib import Path
        >>> import logging
        >>> log = logging.getLogger(__name__)
        >>> warnings = Path("logs/warnings.txt")
        >>> result = run_exiftool(
        ...     ["-FileType", "-s", "-s", "-s", "photo.jpg"],
        ...     exif_warnings_file=warnings,
        ...     log=log
        ... )
        >>> if result.returncode == 0:
        ...     print(f"File type: {result.stdout.strip()}")

    Note:
        exiftool must be installed and available in PATH. Use
        `check_dependencies()` from utils.dependencies to verify.
    """
    exiftool_path = get_exiftool_path()

    # Set up environment for bundled exiftool (Perl lib path)
    env = os.environ.copy()
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        lib_path = Path(str(meipass)) / "lib"
        if lib_path.exists():
            env["PERL5LIB"] = str(lib_path)

    cmd = [exiftool_path] + args
    result = subprocess.run(cmd, capture_output=capture_output, text=True, check=False, env=env)

    # Handle stderr (warnings/errors)
    if result.stderr:
        # Write all stderr to dedicated warnings file
        write_exif_warning(exif_warnings_file, result.stderr)

        # Only log actual Errors to console (not Warnings)
        if log and "Error:" in result.stderr:
            error_count = result.stderr.count("Error:")
            log.error(
                f"exiftool encountered {error_count} error(s) "
                f"(see {exif_warnings_file.name if exif_warnings_file else 'stderr'})"
            )

    return result


def ts_to_exif_date(timestamp: int) -> str:
    """
    Convert Unix timestamp to EXIF datetime format.

    EXIF datetime format is: YYYY:MM:DD HH:MM:SS (with colons as separators)

    Args:
        timestamp: Unix timestamp (seconds since epoch, 1970-01-01 00:00:00 UTC)

    Returns:
        EXIF-formatted datetime string

    Example:
        >>> from takeout_photos.exif.operations import ts_to_exif_date
        >>> ts_to_exif_date(1609459200)
        '2021:01:01 00:00:00'

    Note:
        Uses UTC. Google Takeout JSON metadata contains timestamps in UTC,
        and EXIF dates have no timezone field, so UTC ensures consistent
        output regardless of the system timezone.
    """
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def get_file_type_and_exif(
    file_path: Path,
    exif_warnings_file: Path | None = None,
    log: logging.Logger | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """
    Get both file type and existing EXIF metadata in a single exiftool call.

    This is an optimized version that combines file type detection and
    EXIF reading into one operation, reducing overhead by 50% compared
    to calling get_real_file_type() and read_existing_exif() separately.

    Args:
        file_path: Path to file
        exif_warnings_file: Optional path to append stderr warnings
        log: Optional logger to log critical errors to console

    Returns:
        Tuple of (file_type, exif_dict):
            - file_type (str | None): File type string ("JPEG", "HEIC", etc.) or None
            - exif_dict (dict): Dictionary with EXIF data or empty dict

    EXIF Fields Extracted:
        - DateTimeOriginal: Original capture date/time
        - CreateDate: File creation date
        - GPSLatitude: GPS latitude coordinate
        - GPSLongitude: GPS longitude coordinate

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.exif.operations import get_file_type_and_exif
        >>> file_type, exif = get_file_type_and_exif(Path("photo.jpg"))
        >>> print(f"Type: {file_type}")
        Type: JPEG
        >>> print(f"Date: {exif.get('DateTimeOriginal', 'N/A')}")
        Date: 2021:01:01 12:30:45

    Note:
        This combines two operations that were previously done separately:
        1. Detecting actual file format (for extension correction)
        2. Reading existing EXIF metadata (to preserve it during operations)

        Use this instead of calling get_real_file_type() and read_existing_exif()
        separately for better performance.
    """
    result = run_exiftool(
        [
            "-FileType",
            "-DateTimeOriginal",
            "-CreateDate",
            "-GPSLatitude",
            "-GPSLongitude",
            "-json",
            str(file_path),
        ],
        exif_warnings_file=exif_warnings_file,
        log=log,
    )

    file_type = None
    exif_dict: dict[str, Any] = {}

    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if data and len(data) > 0:
                file_data = data[0]
                # Extract file type
                if "FileType" in file_data:
                    file_type = file_data["FileType"].upper()
                # Extract EXIF data (exclude FileType)
                exif_dict = {k: v for k, v in file_data.items() if k != "FileType"}
        except (json.JSONDecodeError, IndexError):
            pass

    return file_type, exif_dict
