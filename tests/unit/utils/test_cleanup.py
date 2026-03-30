"""Tests for cleanup utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.utils.cleanup import log_pipeline_summary, remove_empty_directories


class TestRemoveEmptyDirectories:
    """Tests for remove_empty_directories()."""

    def test_remove_single_empty_directory(self, tmp_path: Path):
        """Remove a single empty directory."""
        log = logging.getLogger(__name__)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        count = remove_empty_directories(tmp_path, log)

        assert count == 1
        assert not empty_dir.exists()

    def test_remove_nested_empty_directories(self, tmp_path: Path):
        """Remove multiple nested empty directories (bottom-up)."""
        log = logging.getLogger(__name__)

        # Create nested structure: a/b/c/
        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        count = remove_empty_directories(tmp_path, log)

        # Should remove all 3 directories (c, b, a)
        assert count == 3
        assert not (tmp_path / "a").exists()

    def test_preserve_directory_with_file(self, tmp_path: Path):
        """Do not remove directories containing files."""
        log = logging.getLogger(__name__)

        # Create directory with a file
        dir_with_file = tmp_path / "has_file"
        dir_with_file.mkdir()
        (dir_with_file / "file.txt").write_text("content")

        count = remove_empty_directories(tmp_path, log)

        assert count == 0
        assert dir_with_file.exists()
        assert (dir_with_file / "file.txt").exists()

    def test_mixed_tree_removes_only_empty(self, tmp_path: Path):
        """Remove only empty directories in mixed tree."""
        log = logging.getLogger(__name__)

        # Create complex structure:
        # root/
        #   empty1/
        #   has_files/
        #     file.txt
        #     subdir_empty/
        #   empty2/
        #     nested_empty/

        (tmp_path / "empty1").mkdir()
        has_files = tmp_path / "has_files"
        has_files.mkdir()
        (has_files / "file.txt").write_text("content")
        (has_files / "subdir_empty").mkdir()

        empty2 = tmp_path / "empty2"
        empty2.mkdir()
        (empty2 / "nested_empty").mkdir()

        count = remove_empty_directories(tmp_path, log)

        # Should remove: empty1, subdir_empty, nested_empty, empty2 = 4
        assert count == 4
        assert not (tmp_path / "empty1").exists()
        assert has_files.exists()
        assert (has_files / "file.txt").exists()
        assert not (has_files / "subdir_empty").exists()
        assert not (tmp_path / "empty2").exists()

    def test_nonexistent_directory(self, tmp_path: Path):
        """Handle non-existent root directory gracefully."""
        log = logging.getLogger(__name__)
        nonexistent = tmp_path / "does_not_exist"

        count = remove_empty_directories(nonexistent, log)

        assert count == 0

    def test_bottom_up_traversal_order(self, tmp_path: Path):
        """Verify bottom-up traversal (deepest first)."""
        log = logging.getLogger(__name__)

        # Create: a/b/c/ (all empty)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        # Track removal order
        removed = []

        # Monkey-patch rmdir to track calls
        original_rmdir = Path.rmdir

        def tracking_rmdir(path):
            removed.append(path.name)
            original_rmdir(path)

        Path.rmdir = tracking_rmdir

        try:
            remove_empty_directories(tmp_path, log)
        finally:
            Path.rmdir = original_rmdir

        # Should remove c, then b, then a (deepest first)
        assert removed == ["c", "b", "a"]

    def test_permission_error_handling(self, tmp_path: Path, caplog):
        """Handle permission errors gracefully."""
        log = logging.getLogger(__name__)

        # Create empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Simulate permission error
        def raise_permission_error(path):
            raise OSError("Permission denied")

        original_rmdir = Path.rmdir
        Path.rmdir = raise_permission_error

        try:
            with caplog.at_level(logging.DEBUG):
                count = remove_empty_directories(tmp_path, log)
        finally:
            Path.rmdir = original_rmdir

        # Should handle error gracefully
        assert count == 0
        assert "Could not remove" in caplog.text


class TestLogPipelineSummary:
    """Tests for log_pipeline_summary()."""

    def test_basic_summary_output(self, tmp_path: Path, caplog):
        """Log complete summary with all statistics."""
        # Setup
        config = Config(
            workdir=tmp_path,
            logs_dir=tmp_path / "logs",
            organized_dir=tmp_path / "organized",
            exif_warnings_file=tmp_path / "logs" / "20260130_120000_exif_warnings.txt",
        )
        config.logs_dir.mkdir(parents=True)

        # Create mock database
        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        # Mock database queries
        def mock_execute(query):
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (12543,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (234,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (3,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 12543,
                    "with_json": 12000,
                    "with_date": 11800,
                    "with_gps": 4000,
                }
            return result

        mock_conn.execute = mock_execute

        # Create exif warnings file with errors
        config.exif_warnings_file.write_text(
            "Warning: Minor issue\n" "Error: Can't write AVI\n" "Error: Another error\n"
        )

        log = logging.getLogger(__name__)
        cleanup_stats = {"extracted": 15, "duplicates": 3, "organized": 0}

        # Execute
        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, cleanup_stats)

        # Verify
        output = caplog.text

        # Check main statistics
        assert "PIPELINE COMPLETED" in output
        assert "ZIPs processed: 3" in output
        assert "Files organized: 12543" in output
        assert "Duplicates found: 234" in output
        assert "Errors encountered: 2" in output

        # Check cleanup stats
        assert "Cleanup:" in output
        assert "extracted: 15 empty directories removed" in output
        assert "duplicates: 3 empty directories removed" in output
        # Note: organized count is 0, so it's not shown (only non-zero counts are displayed)

        # Check paths
        assert f"Logs: {config.logs_dir}" in output
        assert f"Organized media: {config.organized_dir}" in output

        # Check formatting
        assert "=" * 60 in output

    def test_summary_without_exif_warnings_file(self, tmp_path: Path, caplog):
        """Handle missing exif warnings file gracefully."""
        config = Config(
            workdir=tmp_path,
            logs_dir=tmp_path / "logs",
            organized_dir=tmp_path / "organized",
            exif_warnings_file=None,  # No warnings file
        )

        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        def mock_execute(query):
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (100,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (0,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (1,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 100,
                    "with_json": 90,
                    "with_date": 90,
                    "with_gps": 30,
                }
            return result

        mock_conn.execute = mock_execute

        log = logging.getLogger(__name__)
        cleanup_stats = {}

        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, cleanup_stats)

        output = caplog.text
        assert "Errors encountered: 0" in output

    def test_summary_with_nonexistent_warnings_file(self, tmp_path: Path, caplog):
        """Handle non-existent warnings file gracefully."""
        config = Config(
            workdir=tmp_path,
            logs_dir=tmp_path / "logs",
            organized_dir=tmp_path / "organized",
            exif_warnings_file=tmp_path / "logs" / "nonexistent.txt",
        )

        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        def mock_execute(query):
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (100,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (0,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (1,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 100,
                    "with_json": 90,
                    "with_date": 90,
                    "with_gps": 30,
                }
            return result

        mock_conn.execute = mock_execute

        log = logging.getLogger(__name__)
        cleanup_stats = {}

        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, cleanup_stats)

        output = caplog.text
        assert "Errors encountered: 0" in output

    def test_summary_with_no_cleanup(self, tmp_path: Path, caplog):
        """Show message when no directories were cleaned."""
        config = Config(
            workdir=tmp_path,
            logs_dir=tmp_path / "logs",
            organized_dir=tmp_path / "organized",
        )

        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        def mock_execute(query):
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (100,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (0,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (1,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 100,
                    "with_json": 90,
                    "with_date": 90,
                    "with_gps": 30,
                }
            return result

        mock_conn.execute = mock_execute

        log = logging.getLogger(__name__)
        cleanup_stats = {"extracted": 0, "duplicates": 0, "organized": 0}

        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, cleanup_stats)

        output = caplog.text
        assert "No empty directories found" in output

    def test_error_count_from_warnings_file(self, tmp_path: Path, caplog):
        """Count only Error lines, not Warning lines."""
        config = Config(
            workdir=tmp_path,
            logs_dir=tmp_path / "logs",
            organized_dir=tmp_path / "organized",
            exif_warnings_file=tmp_path / "logs" / "warnings.txt",
        )
        config.logs_dir.mkdir(parents=True)

        # Create warnings file with mixed content
        config.exif_warnings_file.write_text(
            "Warning: [minor] Some warning\n"
            "Error: Can't write AVI\n"
            "Warning: Another warning\n"
            "Error: Second error\n"
            "Some other text\n"
            "Error: Third error\n"
        )

        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        def mock_execute(query):
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (0,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (0,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (0,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 0,
                    "with_json": 0,
                    "with_date": 0,
                    "with_gps": 0,
                }
            return result

        mock_conn.execute = mock_execute

        log = logging.getLogger(__name__)

        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, {})

        output = caplog.text
        # Should count 3 EXIF errors + 0 pipeline errors
        assert "Errors encountered: 3 (EXIF: 3, pipeline: 0)" in output

    def test_summary_statistics_accuracy(self, tmp_path: Path, caplog):
        """Verify database queries are called correctly."""
        config = Config(
            workdir=tmp_path, logs_dir=tmp_path / "logs", organized_dir=tmp_path / "organized"
        )

        db = MagicMock(spec=PipelineDB)
        mock_conn = MagicMock()
        db.conn = mock_conn

        # Track queries
        queries_executed = []

        def mock_execute(query):
            queries_executed.append(query)
            result = MagicMock()
            if "status = 'organized'" in query:
                result.fetchone.return_value = (42,)
            elif "status = 'error'" in query:
                result.fetchone.return_value = (0,)
            elif "content_hash IN (SELECT hash FROM organized_files)" in query:
                result.fetchone.return_value = (5,)
            elif "COUNT(DISTINCT name)" in query:
                result.fetchone.return_value = (2,)
            elif "has_json" in query:
                result.fetchone.return_value = {
                    "total": 42,
                    "with_json": 40,
                    "with_date": 40,
                    "with_gps": 15,
                }
            return result

        mock_conn.execute = mock_execute

        log = logging.getLogger(__name__)

        with caplog.at_level(logging.INFO):
            log_pipeline_summary(config, db, log, {})

        # Verify correct queries were executed
        assert len(queries_executed) == 5
        assert any("status = 'organized'" in q for q in queries_executed)
        assert any("status = 'error'" in q for q in queries_executed)
        assert any(
            "content_hash IN (SELECT hash FROM organized_files)" in q for q in queries_executed
        )
        assert any("COUNT(DISTINCT name)" in q for q in queries_executed)
        assert any("has_json" in q for q in queries_executed)

        # Verify correct values in output
        output = caplog.text
        assert "ZIPs processed: 2" in output
        assert "Files organized: 42" in output
        assert "Duplicates found: 5" in output
