#!/usr/bin/env python3
"""Download and extract exiftool for bundling in PyInstaller binary.

This script downloads the official exiftool binary for macOS ARM64 from
exiftool.org and extracts it to build/exiftool/ for bundling.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

# ExifTool download URL (Perl distribution from SourceForge)
EXIFTOOL_VERSION = "13.47"
EXIFTOOL_URL = (
    f"https://sourceforge.net/projects/exiftool/files/"
    f"Image-ExifTool-{EXIFTOOL_VERSION}.tar.gz/download"
)

# Build directory for exiftool
BUILD_DIR = Path(__file__).parent.parent / "build" / "exiftool"


def check_platform() -> None:
    """Verify we're running on macOS ARM64."""
    if sys.platform != "darwin":
        print(f"❌ This script is for macOS only (detected: {sys.platform})")
        sys.exit(1)

    machine = platform.machine()
    if machine != "arm64":
        print(f"⚠️  Warning: Expected ARM64, detected {machine}")
        print("   Continuing anyway, but binary may not work on Apple Silicon")


def download_exiftool() -> Path:
    """Download exiftool tarball.

    Returns:
        Path to downloaded tarball
    """
    print(f"Downloading exiftool {EXIFTOOL_VERSION}...")
    print(f"URL: {EXIFTOOL_URL}")

    tarball_path = BUILD_DIR / f"exiftool-{EXIFTOOL_VERSION}.tar.gz"

    try:
        with urllib.request.urlopen(EXIFTOOL_URL) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            print(f"Size: {total_size / 1024 / 1024:.1f} MB")

            with open(tarball_path, "wb") as f:
                f.write(response.read())

        print(f"✅ Downloaded: {tarball_path}")
        return tarball_path

    except Exception as e:
        print(f"❌ Download failed: {e}")
        sys.exit(1)


def extract_exiftool(tarball_path: Path) -> None:
    """Extract exiftool from tarball.

    Args:
        tarball_path: Path to downloaded tarball
    """
    print("\nExtracting exiftool...")

    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            # Extract to temporary directory
            extract_dir = BUILD_DIR / "temp"
            extract_dir.mkdir(exist_ok=True)

            tar.extractall(extract_dir)

        source_dir = extract_dir / f"Image-ExifTool-{EXIFTOOL_VERSION}"

        # Copy exiftool executable
        exiftool_src = source_dir / "exiftool"
        if not exiftool_src.exists():
            print(f"❌ exiftool not found in tarball: {exiftool_src}")
            sys.exit(1)

        exiftool_dest = BUILD_DIR / "exiftool"
        shutil.copy2(exiftool_src, exiftool_dest)
        os.chmod(exiftool_dest, 0o755)
        print("✅ Copied exiftool executable")

        # Copy lib directory with Perl modules
        lib_src = source_dir / "lib"
        lib_dest = BUILD_DIR / "lib"

        if lib_dest.exists():
            shutil.rmtree(lib_dest)

        shutil.copytree(lib_src, lib_dest)
        print("✅ Copied Perl library modules")

        # Cleanup
        shutil.rmtree(extract_dir)
        tarball_path.unlink()

        print(f"✅ Extracted to: {BUILD_DIR}")

    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        sys.exit(1)


def verify_exiftool() -> None:
    """Verify exiftool is executable and working."""
    exiftool_path = BUILD_DIR / "exiftool"
    lib_path = BUILD_DIR / "lib"

    print("\nVerifying exiftool...")

    # Check executable exists
    if not exiftool_path.exists():
        print(f"❌ exiftool not found: {exiftool_path}")
        sys.exit(1)

    # Check lib directory exists
    if not lib_path.exists():
        print(f"❌ lib directory not found: {lib_path}")
        sys.exit(1)

    # Check executable permission
    if not os.access(exiftool_path, os.X_OK):
        print(f"❌ exiftool not executable: {exiftool_path}")
        sys.exit(1)

    # Test execution with PERL5LIB set
    import subprocess

    try:
        env = os.environ.copy()
        env["PERL5LIB"] = str(lib_path)

        result = subprocess.run(
            [str(exiftool_path), "-ver"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ exiftool working (version: {version})")
        else:
            print(f"❌ exiftool execution failed: {result.stderr}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ exiftool verification failed: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    print("=== ExifTool Download Script ===\n")

    # Ensure build directory exists
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    exiftool_path = BUILD_DIR / "exiftool"
    if exiftool_path.exists():
        print(f"✅ exiftool already exists: {exiftool_path}")
        print("   Delete it to re-download")
        verify_exiftool()
        return

    # Check platform
    check_platform()

    # Download and extract
    tarball_path = download_exiftool()
    extract_exiftool(tarball_path)

    # Verify
    verify_exiftool()

    print("\n✅ ExifTool setup complete!")


if __name__ == "__main__":
    main()
