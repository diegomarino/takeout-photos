"""Tests for RecoveryManager."""

from __future__ import annotations

import logging

from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
from takeout_photos.core.recovery import RecoveryManager, RecoveryStats


def test_recovery_manager_init(tmp_path):
    """Test RecoveryManager initialization."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Normal mode
    mgr = RecoveryManager(config, db, log)
    assert mgr.dry_run is False

    # Dry-run mode
    mgr_dry = RecoveryManager(config, db, log, dry_run=True)
    assert mgr_dry.dry_run is True


def test_recovery_stats_total(tmp_path):
    """Test RecoveryStats total calculation."""
    stats = RecoveryStats()
    assert stats.total == 0

    stats.intermediate_zips = 2
    stats.orphaned_organized = 5
    stats.orphaned_extracted = 3
    stats.missing_files = 1

    assert stats.total == 11


def test_check_and_recover_no_issues(tmp_path):
    """Test recovery check with clean state."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    mgr = RecoveryManager(config, db, log)
    stats = mgr.check_and_recover()

    assert stats.total == 0


def test_detect_intermediate_zips(tmp_path):
    """Test detection of ZIPs stuck in intermediate states."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Create intermediate ZIPs
    db.register_zip("test1")
    db.update_zip_status("test1", "extracting")  # Stuck in extracting

    db.register_zip("test2")
    db.update_zip_status("test2", "processing")  # Stuck in processing

    db.register_zip("test3")
    db.update_zip_status("test3", "extracted")  # Normal state

    # Run recovery
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_intermediate_zips()

    # Verify intermediate ZIPs were reset
    assert mgr.stats.intermediate_zips == 2

    # Verify statuses were reset
    test1_status = db.get_zip_status("test1")
    assert test1_status == "pending", "extracting should reset to pending"

    test2_status = db.get_zip_status("test2")
    assert test2_status == "extracted", "processing should reset to extracted"

    # test3 should be unchanged
    test3_status = db.get_zip_status("test3")
    assert test3_status == "extracted"


def test_intermediate_zips_dry_run(tmp_path):
    """Test dry-run mode only detects without fixing."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    db.register_zip("test")
    db.update_zip_status("test", "extracting")

    # Dry-run mode
    mgr = RecoveryManager(config, db, log, dry_run=True)
    mgr._detect_and_recover_intermediate_zips()

    # Should detect but not fix
    assert mgr.stats.intermediate_zips == 1

    # Status should NOT be changed
    status = db.get_zip_status("test")
    assert status == "extracting", "Dry-run should not modify status"


def test_detect_orphaned_organized(tmp_path):
    """Test detection of files in organized/ without DB entry."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Create organized files without DB entries
    organized_dir = config.organized_dir / "2020" / "05"
    organized_dir.mkdir(parents=True)

    orphan1 = organized_dir / "orphan1.jpg"
    orphan1.write_bytes(b"test1")

    orphan2 = organized_dir / "orphan2.jpg"
    orphan2.write_bytes(b"test2")

    # Run recovery
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_orphaned_organized()

    # Verify orphans were detected
    assert mgr.stats.orphaned_organized == 2

    # Verify files were registered in DB
    rows = db.conn.execute("SELECT COUNT(*) FROM organized_files").fetchone()
    assert rows[0] == 2, "Both orphans should be registered"


def test_orphaned_organized_with_existing_entries(tmp_path):
    """Test that recovery skips files already in DB."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Create organized file
    organized_dir = config.organized_dir / "2020" / "05"
    organized_dir.mkdir(parents=True)

    file1 = organized_dir / "file1.jpg"
    file1.write_bytes(b"test1")

    # Register it in DB
    db.insert_organized_file(
        hash="hash1",
        original_name="file1.jpg",
        final_path="2020/05/file1.jpg",
        source_zip="test.zip",
        file_size=5,
    )

    # Run recovery
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_orphaned_organized()

    # Should not detect as orphan (already in DB)
    assert mgr.stats.orphaned_organized == 0


def test_detect_orphaned_extracted(tmp_path):
    """Test detection of files in extracted/ without DB entry."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Create extracted files without DB entries
    config.extracted_dir.mkdir(parents=True)

    orphan1 = config.extracted_dir / "orphan1.jpg"
    orphan1.write_bytes(b"test1")

    orphan2 = config.extracted_dir / "orphan2.jpg"
    orphan2.write_bytes(b"test2")

    # Need at least one ZIP for association
    db.register_zip("unknown")

    # Run recovery
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_orphaned_extracted()

    # Verify orphans were detected
    assert mgr.stats.orphaned_extracted == 2

    # Verify files were registered in DB
    rows = db.conn.execute("SELECT COUNT(*) FROM files").fetchone()
    assert rows[0] == 2, "Both orphans should be registered"


def test_detect_missing_files(tmp_path):
    """Test detection of files with invalid paths."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Register files with invalid paths
    db.register_zip("test")

    db.register_file(
        zip_name="test",
        original_path="/nonexistent/path1.jpg",
        file_size=100,
    )
    db.conn.commit()
    file_id1 = db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    db.register_file(
        zip_name="test",
        original_path="/nonexistent/path2.jpg",
        file_size=100,
    )
    db.conn.commit()
    file_id2 = db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Run recovery
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_missing_files()

    # Verify missing files were detected
    assert mgr.stats.missing_files == 2

    # Verify files were marked as error
    file1_status = db.conn.execute("SELECT status FROM files WHERE id = ?", (file_id1,)).fetchone()[
        "status"
    ]
    assert file1_status == "error"

    file2_status = db.conn.execute("SELECT status FROM files WHERE id = ?", (file_id2,)).fetchone()[
        "status"
    ]
    assert file2_status == "error"


def test_missing_files_sampling(tmp_path):
    """Test that recovery samples large datasets."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    # Register many files (simulate large dataset)
    db.register_zip("test")

    for i in range(1000):
        db.register_file(
            zip_name="test",
            original_path=f"/nonexistent/path{i}.jpg",
            file_size=100,
        )

    # Run recovery (should sample, not check all 1000)
    mgr = RecoveryManager(config, db, log)
    mgr._detect_and_recover_missing_files()

    # Should detect missing files (sampling means not all are marked)
    assert mgr.stats.missing_files > 0

    # Cleanup
    db.close()


def test_recovery_filters_system_files_from_orphans(tmp_path):
    """Recovery should not register AppleDouble and system files as orphans."""
    config = Config(workdir=tmp_path)
    db = PipelineDB(config.db_path)
    log = logging.getLogger(__name__)

    workdir = tmp_path / "work"
    workdir.mkdir()
    extracted_dir = workdir / "extracted"
    extracted_dir.mkdir()

    # Create orphan files (not in DB)
    (extracted_dir / "photo.jpg").write_bytes(b"jpeg")
    (extracted_dir / "._photo.jpg").write_bytes(b"appledouble")
    (extracted_dir / ".DS_Store").write_bytes(b"ds store")

    config = Config(workdir=workdir)
    db = PipelineDB(config.db_path)

    # Register unknown ZIP for orphans
    db.register_zip("unknown")
    db.commit()

    recovery = RecoveryManager(config, db, log)
    recovery._detect_and_recover_orphaned_extracted()

    # Verify only legitimate file was registered
    files = db.conn.execute("SELECT original_path FROM files").fetchall()
    paths = [row["original_path"] for row in files]

    assert any("photo.jpg" in p and "._" not in p for p in paths)
    assert not any("._photo.jpg" in p for p in paths)
    assert not any(".DS_Store" in p for p in paths)

    db.close()
