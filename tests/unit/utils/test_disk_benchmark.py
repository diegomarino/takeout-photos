"""Tests for disk benchmark utility."""

from __future__ import annotations

import platform

import pytest

from takeout_photos.utils.disk_benchmark import (
    BenchmarkResult,
    BenchmarkSummary,
    format_benchmark_results,
    run_disk_benchmark,
)

# ---------------------------------------------------------------------------
# BenchmarkResult tests
# ---------------------------------------------------------------------------


class TestBenchmarkResult:
    def test_speed_calculation(self) -> None:
        """Verify MB/s calculation: 100 MB in 2 seconds = 50 MB/s."""
        result = BenchmarkResult(
            operation="write",
            pass_number=1,
            bytes_transferred=100_000_000,
            elapsed_seconds=2.0,
        )
        assert result.speed_mb_s == pytest.approx(50.0)

    def test_speed_zero_time(self) -> None:
        """Zero elapsed time should return 0.0, not raise."""
        result = BenchmarkResult(
            operation="read",
            pass_number=1,
            bytes_transferred=1_000_000,
            elapsed_seconds=0.0,
        )
        assert result.speed_mb_s == 0.0

    def test_speed_negative_time(self) -> None:
        """Negative elapsed time should return 0.0."""
        result = BenchmarkResult(
            operation="read",
            pass_number=1,
            bytes_transferred=1_000_000,
            elapsed_seconds=-1.0,
        )
        assert result.speed_mb_s == 0.0


# ---------------------------------------------------------------------------
# BenchmarkSummary tests
# ---------------------------------------------------------------------------


class TestBenchmarkSummary:
    def test_statistics_with_data(self) -> None:
        """Verify min/avg/max calculations with known values."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=256,
            block_size_kb=1024,
            num_passes=3,
            write_speeds=[100.0, 200.0, 300.0],
            read_speeds=[400.0, 500.0, 600.0],
        )
        assert summary.write_min == pytest.approx(100.0)
        assert summary.write_avg == pytest.approx(200.0)
        assert summary.write_max == pytest.approx(300.0)
        assert summary.read_min == pytest.approx(400.0)
        assert summary.read_avg == pytest.approx(500.0)
        assert summary.read_max == pytest.approx(600.0)

    def test_statistics_empty(self) -> None:
        """Empty speed lists should return 0.0 for all stats."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=256,
            block_size_kb=1024,
            num_passes=0,
        )
        assert summary.write_min == 0.0
        assert summary.write_avg == 0.0
        assert summary.read_max == 0.0

    def test_statistics_single_pass(self) -> None:
        """Single pass: min == avg == max."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            write_speeds=[150.0],
            read_speeds=[300.0],
        )
        assert summary.write_min == summary.write_avg == summary.write_max == 150.0
        assert summary.read_min == summary.read_avg == summary.read_max == 300.0


# ---------------------------------------------------------------------------
# format_benchmark_results tests
# ---------------------------------------------------------------------------


class TestFormatBenchmarkResults:
    def test_contains_expected_fields(self) -> None:
        """Output should contain key benchmark parameters."""
        summary = BenchmarkSummary(
            target_dir="/tmp/bench",
            file_size_mb=64,
            block_size_kb=512,
            num_passes=2,
            write_speeds=[100.0, 120.0],
            read_speeds=[200.0, 240.0],
            platform_info="macOS (F_NOCACHE)",
        )
        output = format_benchmark_results(summary)
        assert "/tmp/bench" in output
        assert "64 MB" in output
        assert "macOS (F_NOCACHE)" in output
        assert "Sequential Write" in output
        assert "Sequential Read" in output
        assert "min" in output
        assert "avg" in output
        assert "max" in output

    def test_single_pass_format(self) -> None:
        """Single pass should show direct speed, not min/avg/max."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            write_speeds=[150.0],
            read_speeds=[300.0],
            platform_info="Linux (O_DIRECT)",
        )
        output = format_benchmark_results(summary)
        assert "150.0" in output
        assert "300.0" in output
        assert "min" not in output

    def test_block_size_mb_display(self) -> None:
        """Block size >= 1024 KB should display in MB."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=1,
            block_size_kb=1024,
            num_passes=1,
            write_speeds=[100.0],
            read_speeds=[200.0],
        )
        output = format_benchmark_results(summary)
        assert "1 MB" in output

    def test_block_size_kb_display(self) -> None:
        """Block size < 1024 KB should display in KB."""
        summary = BenchmarkSummary(
            target_dir="/tmp",
            file_size_mb=1,
            block_size_kb=512,
            num_passes=1,
            write_speeds=[100.0],
            read_speeds=[200.0],
        )
        output = format_benchmark_results(summary)
        assert "512 KB" in output


# ---------------------------------------------------------------------------
# run_disk_benchmark integration tests (small files)
# ---------------------------------------------------------------------------


class TestRunDiskBenchmark:
    def test_small_file(self, tmp_path: pytest.TempPathFactory) -> None:
        """Run benchmark with a tiny file to verify structure and positive speeds."""
        summary = run_disk_benchmark(
            target_dir=tmp_path,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            warmup=False,
        )
        assert summary.file_size_mb == 1
        assert summary.block_size_kb == 64
        assert summary.num_passes == 1
        assert len(summary.write_speeds) == 1
        assert len(summary.read_speeds) == 1
        assert summary.write_speeds[0] > 0
        assert summary.read_speeds[0] > 0

    def test_multiple_passes(self, tmp_path: pytest.TempPathFactory) -> None:
        """Multiple passes should produce the correct number of results."""
        summary = run_disk_benchmark(
            target_dir=tmp_path,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=2,
            warmup=False,
        )
        assert len(summary.write_speeds) == 2
        assert len(summary.read_speeds) == 2

    def test_with_warmup(self, tmp_path: pytest.TempPathFactory) -> None:
        """Warmup pass should not increase the number of recorded results."""
        summary = run_disk_benchmark(
            target_dir=tmp_path,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            warmup=True,
        )
        assert len(summary.write_speeds) == 1
        assert len(summary.read_speeds) == 1

    def test_default_tempdir(self) -> None:
        """target_dir=None should use system temp and succeed."""
        summary = run_disk_benchmark(
            target_dir=None,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            warmup=False,
        )
        assert summary.target_dir != ""
        assert summary.write_speeds[0] > 0

    def test_nonexistent_dir(self) -> None:
        """Non-existent target directory should raise OSError."""
        with pytest.raises(OSError, match="does not exist"):
            run_disk_benchmark(
                target_dir="/nonexistent/path/for/benchmark",
                file_size_mb=1,
                block_size_kb=64,
                num_passes=1,
                warmup=False,
            )

    def test_cleanup(self, tmp_path: pytest.TempPathFactory) -> None:
        """No temp files should remain after benchmark completes."""
        run_disk_benchmark(
            target_dir=tmp_path,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            warmup=False,
        )
        remaining = list(tmp_path.glob("takeout_benchmark_*"))
        assert remaining == []

    def test_invalid_file_size(self) -> None:
        """Zero or negative file_size_mb should raise ValueError."""
        with pytest.raises(ValueError, match="file_size_mb"):
            run_disk_benchmark(file_size_mb=0, num_passes=1, warmup=False)

    def test_invalid_passes(self) -> None:
        """Zero or negative num_passes should raise ValueError."""
        with pytest.raises(ValueError, match="num_passes"):
            run_disk_benchmark(num_passes=0, warmup=False)

    def test_platform_info_set(self, tmp_path: pytest.TempPathFactory) -> None:
        """Platform info string should be non-empty."""
        summary = run_disk_benchmark(
            target_dir=tmp_path,
            file_size_mb=1,
            block_size_kb=64,
            num_passes=1,
            warmup=False,
        )
        assert summary.platform_info != ""


# ---------------------------------------------------------------------------
# Platform-specific tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_platform_info_macos(tmp_path: pytest.TempPathFactory) -> None:
    """On macOS, platform_info should mention F_NOCACHE."""
    summary = run_disk_benchmark(
        target_dir=tmp_path,
        file_size_mb=1,
        block_size_kb=64,
        num_passes=1,
        warmup=False,
    )
    assert "F_NOCACHE" in summary.platform_info


@pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
def test_platform_info_linux(tmp_path: pytest.TempPathFactory) -> None:
    """On Linux, platform_info should mention O_DIRECT."""
    summary = run_disk_benchmark(
        target_dir=tmp_path,
        file_size_mb=1,
        block_size_kb=64,
        num_passes=1,
        warmup=False,
    )
    assert "O_DIRECT" in summary.platform_info
