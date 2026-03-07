"""
Content-based file hashing for deduplication.

Provides fast hashing using xxhash (if available) or SHA256 fallback
for identifying duplicate media files based on content.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    import xxhash

    use_xxhash = True
except ImportError:
    xxhash = None  # type: ignore[assignment]
    use_xxhash = False


def compute_hash(filepath: Path) -> str:
    """
    Compute content hash of a file for deduplication.

    Uses xxhash if available (2-3x faster than SHA256) or SHA256 as fallback.
    The hash is computed from file content only, not filename or metadata.
    This enables detection of identical files across different ZIPs even if
    they have different names or paths.

    Args:
        filepath: Path to file to hash

    Returns:
        Hex digest of file content hash (16-character xxhash or 64-character SHA256)

    Raises:
        FileNotFoundError: If file does not exist
        PermissionError: If file cannot be read
        IOError: If file reading fails

    Hash Algorithm Selection:
        - xxhash (xxh64): Used if xxhash package is installed
          - 2-3x faster than SHA256
          - Produces 16-character hex digest
          - Excellent collision resistance for file deduplication
        - SHA256: Fallback if xxhash not available
          - Cryptographically secure (though not required for deduplication)
          - Produces 64-character hex digest
          - Universal availability in Python standard library

    Performance:
        - Reads file in 64KB chunks to handle large files efficiently
        - Memory usage is constant (64KB) regardless of file size
        - For 1GB file: ~2 seconds with xxhash, ~5 seconds with SHA256

    Example:
        >>> from pathlib import Path
        >>> from takeout_photos.hashing.hasher import compute_hash
        >>> file1 = Path("photo1.jpg")
        >>> file2 = Path("photo2.jpg")  # Identical content, different name
        >>> hash1 = compute_hash(file1)
        >>> hash2 = compute_hash(file2)
        >>> hash1 == hash2  # True if files have identical content
        True

    Use Case - Deduplication:
        >>> from collections import defaultdict
        >>> from pathlib import Path
        >>> from takeout_photos.hashing.hasher import compute_hash
        >>>
        >>> # Group files by content hash
        >>> hash_to_files = defaultdict(list)
        >>> for file in Path("/photos").glob("**/*"):
        ...     if file.is_file():
        ...         h = compute_hash(file)
        ...         hash_to_files[h].append(file)
        >>>
        >>> # Find duplicates
        >>> for hash_val, files in hash_to_files.items():
        ...     if len(files) > 1:
        ...         print(f"Duplicates: {files}")

    Note:
        The hash is based on file content only. Identical files will have
        the same hash even if they have:
        - Different filenames
        - Different paths
        - Different file extensions
        - Different EXIF metadata
        - Different modification timestamps

        However, files with even a single byte difference will have
        different hashes (including EXIF changes).
    """
    h: Any
    if use_xxhash and xxhash is not None:
        h = xxhash.xxh64()
    else:
        h = hashlib.sha256()

    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)

    return str(h.hexdigest())
