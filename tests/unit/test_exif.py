"""
Unit tests for EXIF module.

Tests cover exiftool operations, format detection, and date validation.
Uses mocked subprocess calls to avoid requiring exiftool installation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

from takeout_photos.exif.format_detection import correct_file_extension_fast
from takeout_photos.exif.operations import (
    get_file_type_and_exif,
    run_exiftool,
    ts_to_exif_date,
    write_exif_warning,
)
from takeout_photos.exif.validation import is_suspicious_date


class TestExiftoolOperations:
    """Test exiftool wrapper and basic operations."""

    @patch("subprocess.run")
    def test_run_exiftool_success(self, mock_run):
        """Should execute exiftool command successfully."""
        mock_run.return_value = MagicMock(returncode=0, stdout="JPEG", stderr="", text=True)

        result = run_exiftool(["-FileType", "photo.jpg"])

        assert result.returncode == 0
        assert result.stdout == "JPEG"
        mock_run.assert_called_once()
        # Check that exiftool path was prepended to args (can be full path or just 'exiftool')
        cmd_used = mock_run.call_args[0][0][0]
        assert cmd_used.endswith("exiftool") or cmd_used == "exiftool"

    @patch("subprocess.run")
    def test_run_exiftool_with_capture_output_false(self, mock_run):
        """Should pass capture_output parameter correctly."""
        mock_run.return_value = MagicMock(returncode=0)

        run_exiftool(["-ver"], capture_output=False)

        assert mock_run.call_args[1]["capture_output"] is False

    def test_ts_to_exif_date_converts_timestamp(self):
        """Should convert Unix timestamp to EXIF format."""
        # 2021-01-01 00:00:00 UTC
        timestamp = 1609459200

        exif_date = ts_to_exif_date(timestamp)

        # Note: result depends on system timezone
        assert "2021" in exif_date
        assert "01" in exif_date
        assert ":" in exif_date

    @patch("subprocess.run")
    def test_get_file_type_and_exif_success(self, mock_run):
        """Should extract both file type and EXIF data."""
        mock_output = json.dumps(
            [
                {
                    "FileType": "jpeg",
                    "DateTimeOriginal": "2021:01:01 12:00:00",
                    "GPSLatitude": 40.4168,
                    "GPSLongitude": -3.7038,
                }
            ]
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        file_type, exif_dict = get_file_type_and_exif(Path("photo.jpg"))

        assert file_type == "JPEG"
        assert exif_dict["DateTimeOriginal"] == "2021:01:01 12:00:00"
        assert exif_dict["GPSLatitude"] == 40.4168
        assert "FileType" not in exif_dict  # Should be excluded

    @patch("subprocess.run")
    def test_get_file_type_and_exif_no_file_type(self, mock_run):
        """Should handle missing FileType field."""
        mock_output = json.dumps([{"DateTimeOriginal": "2021:01:01 12:00:00"}])
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        file_type, exif_dict = get_file_type_and_exif(Path("photo.jpg"))

        assert file_type is None
        assert exif_dict["DateTimeOriginal"] == "2021:01:01 12:00:00"

    @patch("subprocess.run")
    def test_get_file_type_and_exif_invalid_json(self, mock_run):
        """Should handle invalid JSON gracefully."""
        mock_run.return_value = MagicMock(returncode=0, stdout="invalid json", stderr="")

        file_type, exif_dict = get_file_type_and_exif(Path("photo.jpg"))

        assert file_type is None
        assert exif_dict == {}

    @patch("subprocess.run")
    def test_get_file_type_and_exif_command_failure(self, mock_run):
        """Should handle exiftool command failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        file_type, exif_dict = get_file_type_and_exif(Path("photo.jpg"))

        assert file_type is None
        assert exif_dict == {}


class TestDateValidation:
    """Test EXIF date validation."""

    def test_is_suspicious_date_epoch(self):
        """Should detect Unix epoch date."""
        assert is_suspicious_date("1970:01:01 00:00:00") is True

    def test_is_suspicious_date_y2k(self):
        """Should detect Y2K default date."""
        assert is_suspicious_date("2000:01:01 00:00:00") is True

    def test_is_suspicious_date_too_old(self):
        """Should reject dates before 1995."""
        assert is_suspicious_date("1990:06:15 10:00:00") is True
        assert is_suspicious_date("1994:12:31 23:59:59") is True

    def test_is_suspicious_date_future(self):
        """Should reject future dates."""
        assert is_suspicious_date("2030:01:01 00:00:00") is True

    def test_is_suspicious_date_valid(self):
        """Should accept valid dates."""
        assert is_suspicious_date("2021:06:15 14:30:00") is False
        assert is_suspicious_date("1995:01:01 00:00:00") is False
        assert is_suspicious_date("2024:12:31 23:59:59") is False

    def test_is_suspicious_date_empty_string(self):
        """Should treat empty string as suspicious."""
        assert is_suspicious_date("") is True

    def test_is_suspicious_date_invalid_format(self):
        """Should treat invalid format as suspicious."""
        assert is_suspicious_date("invalid date") is True
        assert is_suspicious_date("2021-01-01 12:00:00") is True  # Wrong format


class TestFormatDetection:
    """Test file format detection and extension correction."""

    def test_correct_file_extension_fast_no_change_needed(self, temp_dir):
        """Should return original path if extension is correct."""
        log = logging.getLogger(__name__)
        file_path = temp_dir / "photo.jpg"
        file_path.touch()

        result = correct_file_extension_fast(file_path, "JPEG", {}, log)

        assert result == file_path
        assert file_path.exists()

    def test_correct_file_extension_fast_corrects_mismatched(self, temp_dir):
        """Should correct mismatched extension."""
        log = logging.getLogger(__name__)
        file_path = temp_dir / "photo.HEIC"
        file_path.touch()

        result = correct_file_extension_fast(file_path, "JPEG", {}, log)

        expected = temp_dir / "photo.HEIC.jpg"
        assert result == expected
        assert expected.exists()
        assert not file_path.exists()  # Original should be renamed

    def test_correct_file_extension_fast_handles_special_cases(self, temp_dir):
        """Should use special case mapping for JPEG."""
        log = logging.getLogger(__name__)
        file_path = temp_dir / "photo.jpeg"
        file_path.touch()

        result = correct_file_extension_fast(file_path, "JPEG", {}, log)

        # .jpeg should match .jpg (special case)
        expected = temp_dir / "photo.jpeg.jpg"
        assert result == expected

    def test_correct_file_extension_fast_lowercase_extensions(self, temp_dir):
        """Should produce lowercase extensions."""
        log = logging.getLogger(__name__)
        file_path = temp_dir / "photo.TXT"
        file_path.touch()

        result = correct_file_extension_fast(file_path, "PNG", {}, log)

        expected = temp_dir / "photo.TXT.png"
        assert result == expected
        assert expected.suffix == ".png"  # lowercase


class TestExifIntegration:
    """Integration tests for EXIF module."""

    @patch("subprocess.run")
    def test_get_file_type_and_exif_with_correct_extension(self, mock_run, temp_dir):
        """Should detect file type and EXIF, then correct extension if needed."""
        log = logging.getLogger(__name__)
        file_path = temp_dir / "photo.HEIC"
        file_path.touch()

        mock_output = json.dumps(
            [
                {
                    "FileType": "jpeg",
                    "DateTimeOriginal": "2021:01:01 12:00:00",
                }
            ]
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")

        # Get file type and EXIF
        file_type, exif_dict = get_file_type_and_exif(file_path)
        assert file_type == "JPEG"
        assert exif_dict["DateTimeOriginal"] == "2021:01:01 12:00:00"

        # Correct extension using the data we just got
        corrected = correct_file_extension_fast(file_path, file_type, exif_dict, log)
        expected = temp_dir / "photo.HEIC.jpg"
        assert corrected == expected

    def test_ts_to_exif_date_with_suspicious_validation(self):
        """Should convert timestamp and validate result."""
        # Generate a valid date
        timestamp = 1609459200  # 2021-01-01 00:00:00 UTC

        exif_date = ts_to_exif_date(timestamp)
        is_suspicious = is_suspicious_date(exif_date)

        assert is_suspicious is False  # Should be valid

    def test_epoch_timestamp_is_suspicious(self):
        """Should detect epoch timestamp as suspicious."""
        epoch_timestamp = 0  # 1970-01-01 00:00:00

        exif_date = ts_to_exif_date(epoch_timestamp)
        is_suspicious = is_suspicious_date(exif_date)

        assert is_suspicious is True  # Epoch dates are suspicious


class TestExifWarningCapture:
    """Test EXIF warning file capture functionality."""

    def test_write_exif_warning_creates_file(self, tmp_path):
        """Test that write_exif_warning creates file with content."""
        warning_file = tmp_path / "warnings.txt"
        message = "Warning: Test warning\n"

        write_exif_warning(warning_file, message)

        assert warning_file.exists()
        assert warning_file.read_text() == message

    def test_write_exif_warning_appends_content(self, tmp_path):
        """Test that write_exif_warning appends to existing file."""
        warning_file = tmp_path / "warnings.txt"
        warning_file.write_text("First warning\n")

        write_exif_warning(warning_file, "Second warning\n")

        content = warning_file.read_text()
        assert "First warning" in content
        assert "Second warning" in content

    def test_write_exif_warning_adds_newline_if_missing(self, tmp_path):
        """Test that write_exif_warning adds newline if not present."""
        warning_file = tmp_path / "warnings.txt"

        write_exif_warning(warning_file, "Warning without newline")

        assert warning_file.read_text() == "Warning without newline\n"

    def test_write_exif_warning_skips_if_none(self, tmp_path):
        """Test that write_exif_warning skips if warning_file is None."""
        # Should not raise exception
        write_exif_warning(None, "Some warning")

    def test_write_exif_warning_skips_empty_message(self, tmp_path):
        """Test that write_exif_warning skips empty messages."""
        warning_file = tmp_path / "warnings.txt"

        write_exif_warning(warning_file, "")
        write_exif_warning(warning_file, "   ")

        assert not warning_file.exists()

    @patch("subprocess.run")
    def test_run_exiftool_writes_stderr_to_warnings_file(self, mock_run, tmp_path):
        """Test that run_exiftool captures stderr to warnings file."""
        warning_file = tmp_path / "warnings.txt"

        # Mock subprocess.run to return stderr
        mock_run.return_value = MagicMock(
            returncode=0, stdout="JPEG", stderr="Warning: Minor issue\n"
        )

        run_exiftool(["-FileType", "test.jpg"], exif_warnings_file=warning_file)

        assert warning_file.exists()
        assert "Warning: Minor issue" in warning_file.read_text()

    @patch("subprocess.run")
    def test_run_exiftool_logs_errors_to_console(self, mock_run, tmp_path, caplog):
        """Test that run_exiftool logs Error: messages to console."""
        warning_file = tmp_path / "warnings.txt"
        log = logging.getLogger("test")

        # Mock subprocess.run to return error in stderr
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: Can't write AVI\nWarning: Minor issue\nError: Another error\n",
        )

        with caplog.at_level(logging.ERROR):
            run_exiftool(["-test"], exif_warnings_file=warning_file, log=log)

        # Should log error count
        assert "2 error(s)" in caplog.text
        # Should reference warnings file
        assert "warnings.txt" in caplog.text

    def test_get_file_type_and_exif_writes_warnings(self, tmp_path, monkeypatch):
        """Test that get_file_type_and_exif passes warnings file to run_exiftool."""
        warning_file = tmp_path / "warnings.txt"
        test_file = tmp_path / "test.jpg"
        test_file.write_text("fake jpeg")

        # Track calls to run_exiftool
        calls = []

        def mock_run_exiftool(*args, **kwargs):
            calls.append(kwargs)

            class Result:
                returncode = 0
                stdout = '[{"FileType": "JPEG"}]'
                stderr = "Warning: Test\n"

            return Result()

        monkeypatch.setattr("takeout_photos.exif.operations.run_exiftool", mock_run_exiftool)

        file_type, exif = get_file_type_and_exif(test_file, exif_warnings_file=warning_file)

        # Verify run_exiftool was called with warnings file
        assert len(calls) == 1
        assert calls[0].get("exif_warnings_file") == warning_file
