"""Integration tests for CLI commands."""

from __future__ import annotations

import zipfile
from unittest.mock import patch

import pytest

from takeout_photos.cli.commands import cmd_process, cmd_recovery, cmd_reset, cmd_status
from takeout_photos.cli.main import main
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB


class TestCliCommands:
    """Test CLI command functions."""

    def test_cmd_process_empty(self, tmp_path):
        """Test cmd_process with no ZIPs."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        # Should complete without error
        cmd_process(config)

    def test_cmd_process_with_zip(self, tmp_path):
        """Test cmd_process with a minimal ZIP."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")

        cmd_process(config)

        # Verify pipeline completed
        assert config.db_path.exists()

    def test_cmd_status_no_pipeline(self, tmp_path, capsys):
        """Test cmd_status when pipeline hasn't been started."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        cmd_status(config)

        captured = capsys.readouterr()
        assert "No pipeline started yet" in captured.out

    def test_cmd_status_with_pipeline(self, tmp_path, capsys):
        """Test cmd_status after pipeline has run."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        # Run process first
        cmd_process(config)

        # Check status
        cmd_status(config)

        captured = capsys.readouterr()
        assert "PIPELINE STATUS" in captured.out
        assert "ZIPs:" in captured.out
        assert "Duplicates found:" in captured.out

    def test_cmd_status_with_deleted_zip(self, tmp_path, capsys):
        """Test cmd_status displays deleted ZIPs correctly."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create and process a ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        cmd_process(config)

        # Manually mark ZIP as deleted in database
        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        from datetime import datetime

        db.conn.execute(
            "UPDATE zips SET deleted_at = ? WHERE name = ?",
            (datetime.now().isoformat(), "test.zip"),
        )
        db.commit()
        db.close()

        # Check status
        cmd_status(config)

        captured = capsys.readouterr()
        assert "[DELETED]" in captured.out

    def test_cmd_status_with_error_message(self, tmp_path, capsys):
        """Test cmd_status displays ZIP error messages."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP
        zip_path = config.zips_dir / "broken.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        # Initialize database and set error
        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        db.register_zip("broken.zip")
        db.update_zip_status("broken.zip", "error", error_msg="Extraction failed: corrupted ZIP")
        db.commit()
        db.close()

        # Check status
        cmd_status(config)

        captured = capsys.readouterr()
        assert "ERROR:" in captured.out
        assert "Extraction failed" in captured.out

    def test_cmd_status_file_statistics(self, tmp_path, capsys):
        """Test cmd_status shows file statistics by status."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create and process a ZIP to get files in the database
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo1.jpg", b"\xff\xd8\xff\xe0\x00\x01")
            zf.writestr("photo2.jpg", b"\xff\xd8\xff\xe0\x00\x02")

        cmd_process(config)

        # Check status
        cmd_status(config)

        captured = capsys.readouterr()
        assert "Files by status:" in captured.out
        # Should show organized files
        assert "organized:" in captured.out

    def test_cmd_status_with_duplicates(self, tmp_path, capsys):
        """Test cmd_status displays duplicate count."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create two ZIPs with duplicate content
        for i, name in enumerate(["first.zip", "second.zip"]):
            zip_path = config.zips_dir / name
            with zipfile.ZipFile(zip_path, "w") as zf:
                # Same content = duplicate
                zf.writestr(f"photo{i}.jpg", b"\xff\xd8\xff\xe0DUPLICATE")

        cmd_process(config)

        # Check status - should show duplicates
        cmd_status(config)

        captured = capsys.readouterr()
        assert "Duplicates found:" in captured.out
        # At least one duplicate should exist
        assert "Duplicates found: 1" in captured.out or "Duplicates found: 2" in captured.out

    def test_cmd_reset_no_pipeline(self, tmp_path, capsys):
        """Test cmd_reset when pipeline hasn't been started."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        cmd_reset(config)

        captured = capsys.readouterr()
        assert "No pipeline to reset" in captured.out

    def test_cmd_reset_specific_zip(self, tmp_path, capsys):
        """Test resetting a specific ZIP."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create and process a ZIP
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff")

        cmd_process(config)

        # Reset the ZIP
        cmd_reset(config, zip_name="test.zip")

        captured = capsys.readouterr()
        assert "Resetting ZIP: test.zip" in captured.out
        assert "Reset complete" in captured.out

    def test_cmd_reset_all_cancelled(self, tmp_path, capsys):
        """Test cancelling full reset."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        # Run process first
        cmd_process(config)

        # Mock input to return "NO"
        with patch("builtins.input", return_value="NO"):
            cmd_reset(config)

        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    def test_cmd_reset_all_confirmed(self, tmp_path, capsys):
        """Test full reset with confirmation."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        # Run process first
        cmd_process(config)

        # Mock input to return "YES"
        with patch("builtins.input", return_value="YES"):
            cmd_reset(config)

        captured = capsys.readouterr()
        assert "Resetting entire pipeline" in captured.out
        assert "Reset complete" in captured.out


class TestCliMain:
    """Test CLI main function and argparse."""

    def test_main_no_args_shows_help(self, capsys):
        """Test that running with no args shows friendly quick start message."""
        with patch("sys.argv", ["takeout-photos"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0  # Friendly exit, not an error

        captured = capsys.readouterr()
        assert "takeout-photos - Google Photos Takeout Organizer" in captured.out
        assert "Quick start:" in captured.out
        assert "--doctor" in captured.out
        assert "--workdir" in captured.out

    def test_main_help_flag(self, capsys):
        """Test --help flag."""
        with patch("sys.argv", ["takeout-photos", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Google Photos Takeout Pipeline" in captured.out

    def test_main_process_command(self, tmp_path):
        """Test process command via main()."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        # Check pipeline ran
        assert (workdir / "pipeline.db").exists()

    def test_main_status_command(self, tmp_path, capsys):
        """Test status command via main()."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "status"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        captured = capsys.readouterr()
        assert "No pipeline started yet" in captured.out

    def test_main_reset_command_with_zip(self, tmp_path, capsys):
        """Test reset command with --zip flag."""
        workdir = tmp_path / "work"

        # Create minimal pipeline
        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        # Reset specific ZIP
        with patch(
            "sys.argv",
            ["takeout-photos", "--workdir", str(workdir), "reset", "--zip", "test.zip"],
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        captured = capsys.readouterr()
        assert "test.zip" in captured.out

    def test_main_workers_option(self, tmp_path):
        """Test --workers option."""
        workdir = tmp_path / "work"

        with patch(
            "sys.argv", ["takeout-photos", "--workdir", str(workdir), "--workers", "8", "process"]
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        # Verify it completed (workers option was used)
        assert (workdir / "pipeline.db").exists()

    def test_main_verbose_option(self, tmp_path):
        """Test --verbose option."""
        workdir = tmp_path / "work"

        with patch(
            "sys.argv", ["takeout-photos", "--workdir", str(workdir), "--verbose", "process"]
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        # Check log file was created
        log_files = list((workdir / "logs").glob("*_run.log"))
        assert len(log_files) >= 1

    def test_main_dry_run_option(self, tmp_path):
        """Test --dry-run option."""
        workdir = tmp_path / "work"

        with patch(
            "sys.argv", ["takeout-photos", "--workdir", str(workdir), "--dry-run", "process"]
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                main()

        # Database created even in dry-run (tracks what would be done)
        assert (workdir / "pipeline.db").exists()

    def test_main_skip_deps_check(self, tmp_path):
        """Test --skip-deps-check option."""
        workdir = tmp_path / "work"

        with patch(
            "sys.argv",
            ["takeout-photos", "--workdir", str(workdir), "--skip-deps-check", "process"],
        ):
            # Don't mock check_dependencies - it should be skipped
            main()

        assert (workdir / "pipeline.db").exists()

    def test_main_dependency_check_failure(self, tmp_path, capsys):
        """Test behavior when dependency check fails."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=False):
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Required dependencies not satisfied" in captured.out

    def test_main_keyboard_interrupt(self, tmp_path, capsys):
        """Test handling of keyboard interrupt."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch("takeout_photos.cli.main.cmd_process", side_effect=KeyboardInterrupt):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 130

        captured = capsys.readouterr()
        assert "Interrupted by user" in captured.out

    def test_main_exception_handling(self, tmp_path, capsys):
        """Test handling of exceptions."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch(
                    "takeout_photos.cli.main.cmd_process",
                    side_effect=ValueError("Test error"),
                ):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error: Test error" in captured.out

    def test_main_dated_filenames_flag(self, tmp_path):
        """Test --dated-filenames flag is parsed correctly."""
        workdir = tmp_path / "work"

        # We need to capture the Config object to verify the flag was passed
        captured_config = None

        def mock_cmd_process(config):
            nonlocal captured_config
            captured_config = config

        with patch(
            "sys.argv",
            ["takeout-photos", "--workdir", str(workdir), "--dated-filenames", "process"],
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch("takeout_photos.cli.main.cmd_process", side_effect=mock_cmd_process):
                    main()

        assert captured_config is not None
        assert captured_config.dated_filenames is True

    def test_main_dated_filenames_default(self, tmp_path):
        """Test dated_filenames defaults to False."""
        workdir = tmp_path / "work"

        # We need to capture the Config object to verify the default value
        captured_config = None

        def mock_cmd_process(config):
            nonlocal captured_config
            captured_config = config

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "process"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch("takeout_photos.cli.main.cmd_process", side_effect=mock_cmd_process):
                    main()

        assert captured_config is not None
        assert captured_config.dated_filenames is False

    def test_main_doctor_command(self, tmp_path, capsys):
        """Test --doctor command works without workdir."""
        with patch("sys.argv", ["takeout-photos", "--doctor"]):
            with patch(
                "takeout_photos.utils.diagnostics.cmd_doctor", return_value=0
            ) as mock_doctor:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0
                mock_doctor.assert_called_once()

    def test_main_doctor_command_with_workdir(self, tmp_path, capsys):
        """Test --doctor command with workdir."""
        workdir = tmp_path / "work"
        workdir.mkdir()

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "--doctor"]):
            with patch(
                "takeout_photos.utils.diagnostics.cmd_doctor", return_value=0
            ) as mock_doctor:
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 0
                # Should be called with a Config object
                assert mock_doctor.call_count == 1
                call_args = mock_doctor.call_args
                assert call_args[1]["config"] is not None

    def test_main_no_command_shows_help(self, tmp_path, capsys):
        """Test that providing workdir but no command shows help."""
        workdir = tmp_path / "work"

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "usage:" in captured.out.lower() or "usage:" in captured.err.lower()

    def test_main_recovery_command(self, tmp_path):
        """Test recovery command dispatch."""
        workdir = tmp_path / "work"
        workdir.mkdir()

        with patch("sys.argv", ["takeout-photos", "--workdir", str(workdir), "recovery"]):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch("takeout_photos.cli.main.cmd_recovery") as mock_recovery:
                    main()

                    mock_recovery.assert_called_once()
                    call_args = mock_recovery.call_args
                    # Check that dry_run parameter is passed
                    assert "dry_run" in call_args[1]

    def test_main_recovery_command_dry_run(self, tmp_path):
        """Test recovery command with --dry-run flag."""
        workdir = tmp_path / "work"
        workdir.mkdir()

        with patch(
            "sys.argv", ["takeout-photos", "--workdir", str(workdir), "--dry-run", "recovery"]
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch("takeout_photos.cli.main.cmd_recovery") as mock_recovery:
                    main()

                    # Verify recovery command was called (covers line 254-255)
                    mock_recovery.assert_called_once()
                    # dry_run parameter is passed to cmd_recovery
                    call_args = mock_recovery.call_args
                    assert "dry_run" in call_args.kwargs

    def test_main_exception_with_verbose(self, tmp_path, capsys):
        """Test exception handling with verbose flag shows traceback."""
        workdir = tmp_path / "work"

        with patch(
            "sys.argv", ["takeout-photos", "--workdir", str(workdir), "--verbose", "process"]
        ):
            with patch("takeout_photos.core.pipeline.check_dependencies", return_value=True):
                with patch(
                    "takeout_photos.cli.main.cmd_process", side_effect=RuntimeError("Test error")
                ):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == 1
                    captured = capsys.readouterr()
                    # Should show error message
                    assert "Test error" in captured.out
                    # Should show traceback with verbose (printed to stderr)
                    assert "Traceback" in captured.err


class TestCliRecovery:
    """Test CLI recovery command."""

    def test_cmd_recovery_no_issues(self, tmp_path, capsys):
        """Test cmd_recovery when there are no issues."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))

        # Run process first to create a clean pipeline
        cmd_process(config)

        # Run recovery check
        cmd_recovery(config, dry_run=True)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK (dry-run mode)" in captured.out
        assert "No issues found" in captured.out
        assert "Pipeline state is consistent" in captured.out

    def test_cmd_recovery_dry_run_mode(self, tmp_path, capsys):
        """Test cmd_recovery in dry-run mode with issues."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP and process it
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        cmd_process(config)

        # Manually create an inconsistent state: orphaned file in organized/
        assert config.db_path is not None
        db = PipelineDB(config.db_path)

        # Create a file in organized/ that's not in the database
        orphan_file = config.organized_dir / "orphan.jpg"
        orphan_file.write_bytes(b"\xff\xd8\xff\xe0")

        db.close()

        # Run recovery in dry-run mode
        cmd_recovery(config, dry_run=True)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK (dry-run mode)" in captured.out
        assert "detected" in captured.out
        assert "Run 'recovery' without --dry-run to fix these issues" in captured.out

    def test_cmd_recovery_fixes_orphaned_organized(self, tmp_path, capsys):
        """Test cmd_recovery actually fixes orphaned files in organized/."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP and process it
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        cmd_process(config)

        # Create orphaned files in organized/ with different content
        orphan1 = config.organized_dir / "orphan1.jpg"
        orphan1.write_bytes(b"\xff\xd8\xff\xe0\x00\x10ORPHAN1DATA")
        orphan2 = config.organized_dir / "subdir"
        orphan2.mkdir(exist_ok=True)
        (orphan2 / "orphan2.jpg").write_bytes(b"\xff\xd8\xff\xe0\x00\x10ORPHAN2DATA")

        # Verify files exist before recovery
        assert orphan1.exists()
        assert (orphan2 / "orphan2.jpg").exists()

        # Run recovery (not dry-run)
        cmd_recovery(config, dry_run=False)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK" in captured.out
        assert "(dry-run mode)" not in captured.out
        assert "fixed" in captured.out
        assert "orphaned file(s) in organized/" in captured.out

        # Verify orphaned files were tracked in database
        # The test created 2 orphaned files, they should now be in organized_files table
        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        count_before_recovery = 1  # One file from original cmd_process
        organized_count = db.conn.execute("SELECT COUNT(*) FROM organized_files").fetchone()[0]
        db.close()

        # Should have original file + 2 orphans
        assert organized_count >= count_before_recovery + 2

    def test_cmd_recovery_intermediate_zips(self, tmp_path, capsys):
        """Test cmd_recovery fixes intermediate ZIPs stuck in processing."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP and register it but don't complete processing
        zip_path = config.zips_dir / "stuck.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        # Initialize database and register ZIP in intermediate state
        config.workdir.mkdir(parents=True, exist_ok=True)
        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        db.register_zip("stuck.zip")
        db.update_zip_status("stuck.zip", "extracting")  # Intermediate state
        db.commit()
        db.close()

        # Run recovery
        cmd_recovery(config, dry_run=False)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK" in captured.out
        assert "fixed" in captured.out or "detected" in captured.out
        assert "intermediate ZIP(s)" in captured.out

        # Verify ZIP was reset to pending
        db = PipelineDB(config.db_path)
        zip_status = db.get_zip_status("stuck.zip")
        db.close()
        assert zip_status == "pending"

    def test_cmd_recovery_missing_files(self, tmp_path, capsys):
        """Test cmd_recovery detects missing files referenced in database."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create a ZIP and extract it
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        # Initialize database and register file in intermediate state
        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        db.register_zip("test.zip")

        # Create extracted file path
        config.extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_file = config.extracted_dir / "photo.jpg"
        extracted_file.write_bytes(b"\xff\xd8\xff\xe0")

        # Register file in database with 'extracted' status
        db.register_file(zip_name="test.zip", original_path=str(extracted_file))
        db.update_file_status(str(extracted_file), "extracted")
        db.commit()
        db.close()

        # Now delete the file but keep database reference
        extracted_file.unlink()

        # Run recovery
        cmd_recovery(config, dry_run=True)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK" in captured.out
        # Should detect missing file
        assert "missing file(s)" in captured.out or "detected" in captured.out

    def test_cmd_recovery_multiple_issue_types(self, tmp_path, capsys):
        """Test cmd_recovery with multiple types of issues at once."""
        workdir = tmp_path / "work"
        config = Config(workdir=str(workdir))
        config.zips_dir.mkdir(parents=True, exist_ok=True)

        # Create base pipeline
        zip_path = config.zips_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("photo.jpg", b"\xff\xd8\xff\xe0")

        cmd_process(config)

        # Create multiple issues:
        # 1. Orphaned file in organized/
        orphan = config.organized_dir / "orphan.jpg"
        orphan.write_bytes(b"\xff\xd8\xff\xe0")

        # 2. Add another ZIP in intermediate state
        zip_path2 = config.zips_dir / "stuck.zip"
        with zipfile.ZipFile(zip_path2, "w") as zf:
            zf.writestr("photo2.jpg", b"\xff\xd8\xff\xe0")

        assert config.db_path is not None
        db = PipelineDB(config.db_path)
        db.register_zip("stuck.zip")
        db.update_zip_status("stuck.zip", "processing")
        db.commit()
        db.close()

        # Run recovery
        cmd_recovery(config, dry_run=False)

        captured = capsys.readouterr()
        assert "RECOVERY CHECK" in captured.out
        assert "fixed" in captured.out

        # Verify summary shows multiple issue types
        output = captured.out
        # At least one type of issue should be mentioned
        assert (
            "intermediate ZIP(s)" in output
            or "orphaned file(s) in organized/" in output
            or "orphaned file(s) in extracted/" in output
            or "missing file(s)" in output
        )
