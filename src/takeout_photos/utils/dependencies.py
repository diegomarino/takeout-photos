"""
Dependency checking for required and optional tools.

Verifies that all necessary dependencies are installed and provides
clear installation instructions for missing components.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

try:
    import xxhash

    use_xxhash = True
except ImportError:
    xxhash = None  # type: ignore[assignment]
    use_xxhash = False

try:
    from tqdm import tqdm

    use_tqdm = True
except ImportError:
    tqdm = None
    use_tqdm = False


def check_dependencies(verbose: bool = False, log=None) -> bool:
    """
    Check for required and optional dependencies.

    Verifies that all necessary tools are installed and provides
    clear installation instructions for missing dependencies.

    Required dependencies:
    - Python 3.8+
    - exiftool (external binary for EXIF operations)

    Optional dependencies (for better performance):
    - xxhash (2-3x faster hashing)
    - tqdm (progress bars)

    Args:
        verbose: If True, show detailed dependency information for all deps,
                 even when satisfied
        log: Optional logger instance. If provided, uses logging instead of print

    Returns:
        True if all required dependencies are available, False otherwise

    Side effects:
        Prints dependency status and installation instructions to console
        or logs if logger is provided

    Example:
        >>> from takeout_photos.utils.dependencies import check_dependencies
        >>> if check_dependencies(verbose=True):
        ...     print("Ready to run!")
        ... else:
        ...     print("Please install missing dependencies")
    """
    all_ok = True
    warnings = []
    errors = []

    def output(msg: str):
        """Helper to output to logger or print."""
        if log:
            log.info(msg)
        else:
            print(msg)

    def log_only(msg: str):
        """Helper to log only (for audit trail)."""
        if log:
            log.info(msg)

    output("Checking dependencies...")
    output("=" * 60)

    # Check brew (macOS package manager) - helpful but not required
    brew_available = shutil.which("brew") is not None
    if not brew_available and sys.platform == "darwin":
        warnings.append("brew not found (macOS package manager)")
        output("⚠  brew: Not found (optional for installation)")
    elif brew_available and verbose:
        output("✓  brew: Available")

    # Check exiftool (REQUIRED)
    exiftool_path = shutil.which("exiftool")
    if exiftool_path:
        try:
            result = subprocess.run(
                ["exiftool", "-ver"], capture_output=True, text=True, check=False
            )
            version = result.stdout.strip()
            output(f"✓  exiftool: {version} ({exiftool_path})")
        except Exception:
            output(f"✓  exiftool: Available ({exiftool_path})")
    else:
        errors.append("exiftool")
        output("✗  exiftool: NOT FOUND (REQUIRED)")
        output("   This tool is essential for EXIF metadata operations.")
        output("")
        if sys.platform == "darwin":
            output("   Install with: brew install exiftool")
        elif sys.platform == "linux":
            output("   Install with: sudo apt-get install libimage-exiftool-perl")
            output("             or: sudo yum install perl-Image-ExifTool")
        else:
            output("   Download from: https://exiftool.org/")
        output("")
        all_ok = False

    # Check Python version (required: 3.8+)
    # Note: Package installation already enforces requires-python >= 3.8
    py_version = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    output(f"✓  Python: {py_version}")

    # Check optional Python packages
    # Always log for audit trail, only print to terminal if packages missing
    log_only("")
    log_only("Optional Python packages (for better performance):")
    log_only("-" * 60)

    # Collect optional package status
    optional_status = []

    # Check xxhash
    if use_xxhash:
        try:
            import xxhash  # noqa: F401, F811

            log_only("✓  xxhash: Available (fast hashing enabled)")
        except Exception:
            pass
    else:
        warnings.append("xxhash")
        optional_status.append("⚠  xxhash: Not available")
        optional_status.append("   Will use SHA256 (2-3x slower for hashing)")
        optional_status.append("   Install with: pip install xxhash")
        log_only("⚠  xxhash: Not available")

    # Check tqdm
    if use_tqdm:
        try:
            from tqdm import tqdm  # noqa: F401, F811

            log_only("✓  tqdm: Available (progress bars enabled)")
        except Exception:
            pass
    else:
        warnings.append("tqdm")
        optional_status.append("⚠  tqdm: Not available")
        optional_status.append("   Progress bars will not be displayed")
        optional_status.append("   Install with: pip install tqdm")
        log_only("⚠  tqdm: Not available")

    # Print to terminal only if packages are missing
    if optional_status:
        print()
        print("Optional Python packages (for better performance):")
        print("-" * 60)
        for line in optional_status:
            print(line)
        print()

    # Summary
    output("")
    output("=" * 60)
    if all_ok and not warnings:
        output("✅ All dependencies satisfied!")
    elif all_ok:
        output("✓  Required dependencies satisfied")
        output(f"⚠  {len(warnings)} optional package(s) missing (recommended)")
        output("")
        output("For optimal performance, install optional packages:")
        output("  pip install tqdm xxhash")
    else:
        output(f"❌ Missing {len(errors)} required dependency/dependencies:")
        for dep in errors:
            output(f"   - {dep}")
        output("")
        output("Please install required dependencies before running the pipeline.")

    output("=" * 60)
    print()

    return all_ok
