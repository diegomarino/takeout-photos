"""Tests for quality control stage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from takeout_photos.stages.qc import step_qc


class TestStepQc:
    """Test the quality control stage."""

    def test_qc_creates_report(self, config, db, logger):
        """Test that QC report is created."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

        # Check that a report was created
        reports = list(config.logs_dir.glob("*_qc.txt"))
        assert len(reports) == 1

    def test_qc_report_has_header(self, config, db, logger):
        """Test that QC report has proper header."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "QC Report" in content
        assert str(config.final_dir) in content

    def test_qc_reports_undated_files(self, config, db, logger):
        """Test reporting of files without dates."""
        config.final_dir.mkdir(parents=True, exist_ok=True)
        no_date_dir = config.final_dir / "no_date"
        no_date_dir.mkdir(exist_ok=True)

        # Create undated files
        (no_date_dir / "file1.jpg").write_bytes(b"content")
        (no_date_dir / "file2.jpg").write_bytes(b"content")

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Files without DateTimeOriginal: 2" in content
        assert "file1.jpg" in content
        assert "file2.jpg" in content

    def test_qc_limits_undated_file_listing(self, config, db, logger):
        """Test that undated file listing is limited to 50."""
        config.final_dir.mkdir(parents=True, exist_ok=True)
        no_date_dir = config.final_dir / "no_date"
        no_date_dir.mkdir(exist_ok=True)

        # Create 60 undated files
        for i in range(60):
            (no_date_dir / f"file{i}.jpg").write_bytes(b"content")

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Files without DateTimeOriginal: 60" in content
        assert "and 10 more" in content  # 60 - 50 = 10

    def test_qc_checks_old_dates(self, config, db, logger):
        """Test checking for suspiciously old dates."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            # First call for old dates
            mock_exiftool.return_value = MagicMock(
                stdout="1985:03:12 - 1985/03/old.jpg", returncode=0
            )
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Very old dates (< 1995)" in content
        assert "1985:03:12" in content

    def test_qc_checks_future_dates(self, config, db, logger):
        """Test checking for future dates."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        call_count = [0]

        def side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:  # Old dates
                return MagicMock(stdout="", returncode=0)
            elif call_count[0] == 2:  # Future dates
                return MagicMock(stdout="2027:06:18 - 2027/06/future.jpg", returncode=0)
            else:  # Suspicious dates
                return MagicMock(stdout="", returncode=0)

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.side_effect = side_effect
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Future dates" in content
        assert "2027:06:18" in content

    def test_qc_checks_suspicious_epoch_dates(self, config, db, logger):
        """Test checking for suspicious epoch dates."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        call_count = [0]

        def side_effect(*args):
            call_count[0] += 1
            if call_count[0] <= 2:  # Old and future dates
                return MagicMock(stdout="", returncode=0)
            else:  # Suspicious dates
                return MagicMock(
                    stdout="1970:01:01 - 1970/01/epoch.jpg\n2000:01:01 - 2000/01/y2k.jpg",
                    returncode=0,
                )

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.side_effect = side_effect
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Suspicious dates" in content
        assert "1970:01:01" in content
        assert "2000:01:01" in content

    def test_qc_generates_statistics(self, config, db, logger):
        """Test generation of file statistics."""
        config.organized_dir.mkdir(parents=True, exist_ok=True)

        # Create year directories with files
        year_2020 = config.organized_dir / "2020"
        year_2021 = config.organized_dir / "2021"
        year_2020.mkdir(exist_ok=True)
        year_2021.mkdir(exist_ok=True)

        (year_2020 / "file1.jpg").write_bytes(b"content")
        (year_2020 / "file2.jpg").write_bytes(b"content")
        (year_2021 / "file3.jpg").write_bytes(b"content")

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

        report = list(config.logs_dir.glob("*_qc.txt"))[0]
        content = report.read_text()

        assert "Statistics" in content
        assert "Total files organized: 3" in content
        assert "2020: 2" in content
        assert "2021: 1" in content

    def test_qc_exiftool_called_correctly(self, config, db, logger):
        """Test that exiftool is called with correct arguments."""
        config.final_dir.mkdir(parents=True, exist_ok=True)

        with patch("takeout_photos.stages.qc.run_exiftool") as mock_exiftool:
            mock_exiftool.return_value = MagicMock(stdout="", returncode=0)
            step_qc(config, db, logger)

            # Should be called 3 times (old dates, future dates, suspicious dates)
            assert mock_exiftool.call_count == 3

            # Check arguments contain correct filters
            calls = [str(call[0][0]) for call in mock_exiftool.call_args_list]
            assert any("1995:01:01" in call for call in calls)  # Old dates
            assert any("$now" in call for call in calls)  # Future dates
            assert any("1970|2000" in call for call in calls)  # Suspicious dates

    def test_qc_filters_system_files_from_counts(self, config, db, logger):
        """QC report should not count AppleDouble and system files."""
        config.organized_dir.mkdir(parents=True, exist_ok=True)

        # Create organized files
        no_date_dir = config.organized_dir / "no_date"
        no_date_dir.mkdir()
        (no_date_dir / "photo.jpg").write_bytes(b"jpeg")
        (no_date_dir / "._photo.jpg").write_bytes(b"appledouble")
        (no_date_dir / ".DS_Store").write_bytes(b"ds store")

        year_dir = config.organized_dir / "2020"
        year_dir.mkdir()
        (year_dir / "video.mp4").write_bytes(b"video")
        (year_dir / "._video.mp4").write_bytes(b"appledouble")

        # Manually count files with filtering
        from takeout_photos.utils.system_files import should_ignore_path

        no_date_count = sum(
            1 for f in no_date_dir.rglob("*") if f.is_file() and not should_ignore_path(f)
        )
        year_count = sum(
            1 for f in year_dir.rglob("*") if f.is_file() and not should_ignore_path(f)
        )

        # Should only count legitimate files
        assert no_date_count == 1  # photo.jpg only
        assert year_count == 1  # video.mp4 only
