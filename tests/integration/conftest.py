"""Shared fixtures for integration tests.

Provides a factory for generating real JPEG files that carry genuine embedded
EXIF (written by exiftool), so tests exercise the actual get_file_type_and_exif()
read path instead of mocking it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def make_jpeg_with_exif():
    """Return a factory that writes a real JPEG with an embedded DateTimeOriginal.

    Usage:
        make(path, date="2021:07:15 09:30:00", color=(120, 60, 30))

    The generated file has genuine EXIF written by exiftool, so validation reads
    it through the real code path (no mocks). Parent directories are created as
    needed.

    Pillow is imported lazily via ``importorskip`` so that environments without
    it skip these tests cleanly instead of aborting collection (a module-level
    import failure in a conftest is fatal for the whole test session).
    """
    pil_image = pytest.importorskip("PIL.Image")

    def _make(
        path: str | Path,
        date: str = "2021:07:15 09:30:00",
        color: tuple[int, int, int] = (120, 60, 30),
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        pil_image.new("RGB", (16, 16), color).save(path, "JPEG")
        subprocess.run(
            [
                "exiftool",
                "-overwrite_original",
                f"-DateTimeOriginal={date}",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return path

    return _make
