"""
Cross-platform disk benchmark utility.

Measures sustained sequential read/write throughput by writing and reading
a temporary file, bypassing OS page cache where possible.

Supported platforms:
    - macOS: uses F_NOCACHE via fcntl
    - Linux: uses O_DIRECT with page-aligned buffers (fallback if unsupported)
    - Windows: uses os.fsync + large files (no stdlib cache bypass available)
"""

from __future__ import annotations

import logging
import mmap
import os
import platform
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

_SYSTEM = platform.system()
_DEFAULT_FILE_SIZE_MB = 256
_DEFAULT_BLOCK_SIZE_KB = 1024  # 1 MB
_DEFAULT_PASSES = 3


@dataclass
class BenchmarkResult:
    """Results from a single read or write pass.

    Args:
        operation: "read" or "write"
        pass_number: 1-indexed pass number
        bytes_transferred: Total bytes in this pass
        elapsed_seconds: Wall-clock time for the pass
    """

    operation: str
    pass_number: int
    bytes_transferred: int
    elapsed_seconds: float

    @property
    def speed_mb_s(self) -> float:
        """Throughput in MB/s (base-10 MB = 10^6 bytes)."""
        if self.elapsed_seconds <= 0:
            return 0.0
        return (self.bytes_transferred / 1_000_000) / self.elapsed_seconds


@dataclass
class BenchmarkSummary:
    """Aggregated benchmark results.

    Args:
        target_dir: Directory where benchmark ran
        file_size_mb: Size of test file in MB
        block_size_kb: I/O block size in KB
        num_passes: Number of passes per operation
        write_speeds: Write speeds in MB/s per pass
        read_speeds: Read speeds in MB/s per pass
        platform_info: OS and cache-bypass method used
    """

    target_dir: str
    file_size_mb: int
    block_size_kb: int
    num_passes: int
    write_speeds: list[float] = field(default_factory=list)
    read_speeds: list[float] = field(default_factory=list)
    platform_info: str = ""

    @property
    def write_min(self) -> float:
        return min(self.write_speeds) if self.write_speeds else 0.0

    @property
    def write_avg(self) -> float:
        return statistics.mean(self.write_speeds) if self.write_speeds else 0.0

    @property
    def write_max(self) -> float:
        return max(self.write_speeds) if self.write_speeds else 0.0

    @property
    def read_min(self) -> float:
        return min(self.read_speeds) if self.read_speeds else 0.0

    @property
    def read_avg(self) -> float:
        return statistics.mean(self.read_speeds) if self.read_speeds else 0.0

    @property
    def read_max(self) -> float:
        return max(self.read_speeds) if self.read_speeds else 0.0


# ---------------------------------------------------------------------------
# Cross-platform cache bypass helpers
# ---------------------------------------------------------------------------


def _get_platform_info() -> str:
    """Return a human-readable string describing the cache bypass method."""
    if _SYSTEM == "Darwin":
        return "macOS (F_NOCACHE)"
    if _SYSTEM == "Linux":
        return "Linux (O_DIRECT)"
    if _SYSTEM == "Windows":
        return "Windows (fsync)"
    return f"{_SYSTEM} (fsync)"


def _open_for_write(filepath: str) -> tuple[int, bool]:
    """Open a file for benchmark writing with cache bypass when possible.

    Args:
        filepath: Path to the file to open.

    Returns:
        Tuple of (file_descriptor, is_direct) where is_direct indicates
        whether OS page cache bypass is active.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    is_direct = False

    # Linux: try O_DIRECT (may fail on tmpfs or unsupported filesystems)
    if _SYSTEM == "Linux" and hasattr(os, "O_DIRECT"):
        try:
            fd = os.open(filepath, flags | os.O_DIRECT, 0o600)
            return fd, True
        except OSError:
            pass

    fd = os.open(filepath, flags, 0o600)

    # macOS: apply F_NOCACHE after opening
    if _SYSTEM == "Darwin":
        try:
            import fcntl

            fcntl.fcntl(fd, 48, 1)  # F_NOCACHE = 48
            is_direct = True
        except (ImportError, OSError):
            pass

    return fd, is_direct


def _open_for_read(filepath: str) -> tuple[int, bool]:
    """Open a file for benchmark reading with cache bypass when possible.

    Args:
        filepath: Path to the file to open.

    Returns:
        Tuple of (file_descriptor, is_direct).
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    is_direct = False

    if _SYSTEM == "Linux" and hasattr(os, "O_DIRECT"):
        try:
            fd = os.open(filepath, flags | os.O_DIRECT)
            return fd, True
        except OSError:
            pass

    fd = os.open(filepath, flags)

    if _SYSTEM == "Darwin":
        try:
            import fcntl

            fcntl.fcntl(fd, 48, 1)
            is_direct = True
        except (ImportError, OSError):
            pass

    return fd, is_direct


def _make_write_buffer(data: bytes) -> bytes | mmap.mmap:
    """Create a write buffer, page-aligned on Linux for O_DIRECT compatibility.

    On Linux, O_DIRECT requires page-aligned memory. We use an anonymous mmap
    which is guaranteed to be page-aligned, then copy our data into it.

    Args:
        data: The raw bytes to write.

    Returns:
        A buffer containing the data, page-aligned on Linux.
    """
    if _SYSTEM == "Linux" and hasattr(os, "O_DIRECT"):
        buf = mmap.mmap(-1, len(data))
        buf.write(data)
        buf.seek(0)
        return buf
    return data


def _make_read_buffer(size: int) -> bytearray | mmap.mmap:
    """Create a read buffer, page-aligned on Linux for O_DIRECT compatibility.

    Args:
        size: Buffer size in bytes.

    Returns:
        A buffer suitable for os.readinto or os.read.
    """
    if _SYSTEM == "Linux" and hasattr(os, "O_DIRECT"):
        return mmap.mmap(-1, size)
    return bytearray(size)


# ---------------------------------------------------------------------------
# Benchmark execution
# ---------------------------------------------------------------------------


def _run_write_pass(filepath: str, data: bytes | mmap.mmap, total_bytes: int) -> float:
    """Execute a single write pass and return elapsed seconds.

    Args:
        filepath: Path to write to.
        data: Block data to write repeatedly.
        total_bytes: Total bytes to write.

    Returns:
        Elapsed wall-clock seconds.
    """
    block_size = len(data)
    num_blocks = total_bytes // block_size

    fd, _is_direct = _open_for_write(filepath)
    try:
        start = time.perf_counter()
        for _ in range(num_blocks):
            if isinstance(data, mmap.mmap):
                data.seek(0)
            os.write(fd, data)
        os.fsync(fd)
        elapsed = time.perf_counter() - start
    finally:
        os.close(fd)
    return elapsed


def _run_read_pass(filepath: str, block_size: int) -> tuple[float, int]:
    """Execute a single read pass and return elapsed seconds and bytes read.

    Args:
        filepath: Path to read from.
        block_size: Size of each read operation in bytes.

    Returns:
        Tuple of (elapsed_seconds, total_bytes_read).
    """
    fd, _is_direct = _open_for_read(filepath)
    try:
        total_read = 0
        start = time.perf_counter()
        while True:
            chunk = os.read(fd, block_size)
            if not chunk:
                break
            total_read += len(chunk)
        elapsed = time.perf_counter() - start
    finally:
        os.close(fd)
    return elapsed, total_read


def run_disk_benchmark(
    target_dir: Path | str | None = None,
    file_size_mb: int = _DEFAULT_FILE_SIZE_MB,
    block_size_kb: int = _DEFAULT_BLOCK_SIZE_KB,
    num_passes: int = _DEFAULT_PASSES,
    warmup: bool = True,
    log: logging.Logger | None = None,
) -> BenchmarkSummary:
    """Run a disk read/write benchmark on the specified directory.

    Writes a temporary file of the given size, measures sequential write
    throughput, then reads it back measuring sequential read throughput.
    Repeats for the specified number of passes and reports statistics.

    Args:
        target_dir: Directory to benchmark. Defaults to system temp dir.
        file_size_mb: Size of test file in megabytes (default: 256).
        block_size_kb: I/O block size in kilobytes (default: 1024).
        num_passes: Number of write+read passes (default: 3).
        warmup: If True, run one untimed pass first (default: True).
        log: Optional logger for progress messages.

    Returns:
        BenchmarkSummary with per-pass and aggregate results.

    Raises:
        OSError: If target_dir is not writable or disk is full.
        ValueError: If file_size_mb, block_size_kb, or num_passes are invalid.
    """
    if file_size_mb <= 0:
        raise ValueError(f"file_size_mb must be positive, got {file_size_mb}")
    if block_size_kb <= 0:
        raise ValueError(f"block_size_kb must be positive, got {block_size_kb}")
    if num_passes <= 0:
        raise ValueError(f"num_passes must be positive, got {num_passes}")

    # Resolve target directory
    if target_dir is None:
        resolved_dir = Path(tempfile.gettempdir())
    else:
        resolved_dir = Path(target_dir).expanduser().resolve()

    if not resolved_dir.is_dir():
        raise OSError(f"Target directory does not exist: {resolved_dir}")

    block_size = block_size_kb * 1024
    total_bytes = file_size_mb * 1024 * 1024
    benchmark_file = str(resolved_dir / f"takeout_benchmark_{os.getpid()}.tmp")

    if log:
        log.info(f"Benchmark: {file_size_mb} MB, {block_size_kb} KB blocks, {num_passes} passes")
        log.info(f"Target: {resolved_dir}")

    # Generate random data and prepare aligned buffer
    raw_data = os.urandom(block_size)
    write_buf = _make_write_buffer(raw_data)

    platform_info = _get_platform_info()
    summary = BenchmarkSummary(
        target_dir=str(resolved_dir),
        file_size_mb=file_size_mb,
        block_size_kb=block_size_kb,
        num_passes=num_passes,
        platform_info=platform_info,
    )

    try:
        # Warmup pass (results discarded)
        if warmup:
            if log:
                log.info("Running warmup pass...")
            _run_write_pass(benchmark_file, write_buf, total_bytes)
            _run_read_pass(benchmark_file, block_size)
            try:
                os.unlink(benchmark_file)
            except OSError:
                pass

        # Measured passes
        for i in range(1, num_passes + 1):
            if log:
                log.info(f"Pass {i}/{num_passes}...")

            # Write pass
            write_elapsed = _run_write_pass(benchmark_file, write_buf, total_bytes)
            write_result = BenchmarkResult(
                operation="write",
                pass_number=i,
                bytes_transferred=total_bytes,
                elapsed_seconds=write_elapsed,
            )
            summary.write_speeds.append(write_result.speed_mb_s)

            # Read pass
            read_elapsed, bytes_read = _run_read_pass(benchmark_file, block_size)
            read_result = BenchmarkResult(
                operation="read",
                pass_number=i,
                bytes_transferred=bytes_read,
                elapsed_seconds=read_elapsed,
            )
            summary.read_speeds.append(read_result.speed_mb_s)

            # Clean up between passes
            try:
                os.unlink(benchmark_file)
            except OSError:
                pass

    finally:
        # Ensure cleanup even on error
        try:
            os.unlink(benchmark_file)
        except OSError:
            pass
        # Close mmap buffer if used
        if isinstance(write_buf, mmap.mmap):
            write_buf.close()

    return summary


def format_benchmark_results(summary: BenchmarkSummary) -> str:
    """Format benchmark results as a human-readable string.

    Args:
        summary: The benchmark results to format.

    Returns:
        Multi-line formatted string with results table.
    """
    sep = "=" * 60
    lines = [
        "",
        "Disk Benchmark Results",
        sep,
        f"  Target:      {summary.target_dir}",
        f"  File size:   {summary.file_size_mb} MB",
        f"  Block size:  {summary.block_size_kb // 1024 if summary.block_size_kb >= 1024 else summary.block_size_kb} "
        f"{'MB' if summary.block_size_kb >= 1024 else 'KB'}",
        f"  Passes:      {summary.num_passes}",
        f"  Platform:    {summary.platform_info}",
        "",
    ]

    if summary.num_passes == 1:
        if summary.write_speeds:
            lines.append(f"  Sequential Write:  {summary.write_speeds[0]:>8.1f} MB/s")
        if summary.read_speeds:
            lines.append(f"  Sequential Read:   {summary.read_speeds[0]:>8.1f} MB/s")
    else:
        if summary.write_speeds:
            lines.append(
                f"  Sequential Write:  "
                f"min {summary.write_min:>8.1f}  "
                f"avg {summary.write_avg:>8.1f}  "
                f"max {summary.write_max:>8.1f}  MB/s"
            )
        if summary.read_speeds:
            lines.append(
                f"  Sequential Read:   "
                f"min {summary.read_min:>8.1f}  "
                f"avg {summary.read_avg:>8.1f}  "
                f"max {summary.read_max:>8.1f}  MB/s"
            )

    lines.append(sep)
    lines.append("")
    return "\n".join(lines)
