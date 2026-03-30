"""
SQLite database for pipeline state management and deduplication.

This module provides the PipelineDB class which manages all database operations
for the takeout_photos pipeline, including checkpoint tracking, file metadata,
and deduplication records.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class PipelineDB:
    """
    SQLite database for pipeline state management and deduplication.

    This class manages all database operations for the pipeline, including:
    - Tracking ZIP processing state (checkpoints)
    - Recording file metadata and processing status
    - Managing deduplication records
    - Storing pipeline-wide state

    The database enables the pipeline to:
    1. Resume processing after failures
    2. Track which files have been processed
    3. Identify duplicates across all ZIPs
    4. Generate statistics and reports

    Schema:
        zips: Tracks each ZIP file's processing state
        files: Records every media file with metadata, status, and error messages
        pipeline_state: Key-value store for global pipeline state
        json_files: Registry of JSON metadata files for fast lookup
        organized_files: Records organized files by content hash
        recovery_log: Audit log for recovery operations

    Args:
        db_path: Path to SQLite database file (created if doesn't exist)

    Attributes:
        db_path: Path to the database file
        conn: Active SQLite connection

    Example:
        >>> db = PipelineDB(Path("/tmp/pipeline.db"))
        >>> db.register_zip("takeout-001.zip")
        >>> db.update_zip_status("takeout-001.zip", "extracted")
        >>> db.close()
    """

    db_path: Path
    conn: sqlite3.Connection

    def __init__(self, db_path: Path):
        """
        Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file (created if doesn't exist)
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """
        Create database schema if it doesn't exist.

        This method is idempotent - safe to call multiple times.
        Creates tables with appropriate indexes for query performance.

        Side effects:
            Creates 6 tables (zips, files, pipeline_state, json_files,
            organized_files, recovery_log) and indexes if they don't already exist.
        """
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS zips (
                name TEXT PRIMARY KEY,
                -- Status: pending, extracting, extracted, processing, error
                status TEXT DEFAULT 'pending',
                file_count INTEGER,
                extracted_at TEXT,
                deleted_at TEXT,
                error_msg TEXT
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                zip_name TEXT,
                original_path TEXT,
                content_hash TEXT,
                file_size INTEGER,
                has_json INTEGER DEFAULT 0,
                json_path TEXT,

                -- Metadata extracted from JSON
                photo_taken_ts INTEGER,
                geo_lat REAL,
                geo_lon REAL,

                -- Final EXIF data
                exif_datetime TEXT,
                exif_has_gps INTEGER DEFAULT 0,

                -- Processing state
                status TEXT DEFAULT 'pending',  -- pending, meta_applied, staged, organized, error
                staged_path TEXT,  -- Relative path during organize staging
                final_path TEXT,
                error_msg TEXT,  -- Error description for failed files

                -- QC flags
                qc_no_date INTEGER DEFAULT 0,
                qc_suspicious_date INTEGER DEFAULT 0,
                qc_future_date INTEGER DEFAULT 0,

                UNIQUE(zip_name, original_path)
            );

            CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
            CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
            CREATE INDEX IF NOT EXISTS idx_files_zip ON files(zip_name);

            CREATE TABLE IF NOT EXISTS pipeline_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS json_files (
                id INTEGER PRIMARY KEY,
                zip_name TEXT,
                filename TEXT,              -- Base filename: IMG_1234.HEIC.supplemental-metadata.json
                full_path TEXT,             -- Complete path to JSON file
                base_media_name TEXT,       -- Derived media filename: IMG_1234.HEIC

                UNIQUE(zip_name, full_path)
            );

            CREATE INDEX IF NOT EXISTS idx_json_filename ON json_files(filename);
            CREATE INDEX IF NOT EXISTS idx_json_media_name ON json_files(base_media_name);
            CREATE INDEX IF NOT EXISTS idx_json_zip ON json_files(zip_name);

            CREATE TABLE IF NOT EXISTS organized_files (
                hash TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                final_path TEXT NOT NULL,
                organized_at TEXT NOT NULL,
                source_zip TEXT NOT NULL,
                file_size INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_organized_hash ON organized_files(hash);
            CREATE INDEX IF NOT EXISTS idx_organized_zip ON organized_files(source_zip);

            CREATE TABLE IF NOT EXISTS recovery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                recovery_type TEXT NOT NULL,
                affected_count INTEGER DEFAULT 0,
                details TEXT,
                resolved INTEGER DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_recovery_timestamp ON recovery_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_recovery_type ON recovery_log(recovery_type);
        """)
        self.conn.commit()

    def get_state(self, key: str, default=None):
        """
        Retrieve global pipeline state value.

        Args:
            key: State key to retrieve
            default: Default value if key doesn't exist

        Returns:
            Stored value or default if not found
        """
        row = self.conn.execute("SELECT value FROM pipeline_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str):
        """
        Store global pipeline state value.

        Args:
            key: State key
            value: Value to store

        Side effects:
            Inserts or replaces state value in database and commits.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO pipeline_state (key, value) VALUES (?, ?)", (key, value)
        )
        self.conn.commit()

    def register_zip(self, name: str):
        """
        Register a new ZIP file in the database.

        Args:
            name: ZIP filename (e.g., 'takeout-001.zip')

        Side effects:
            Inserts ZIP record with 'pending' status if not exists, then commits.

        Note:
            Uses INSERT OR IGNORE to safely handle re-registration.
        """
        self.conn.execute("INSERT OR IGNORE INTO zips (name) VALUES (?)", (name,))
        self.conn.commit()

    def update_zip_status(self, name: str, status: str, **kwargs):
        """
        Update ZIP processing status and optional metadata.

        Args:
            name: ZIP filename
            status: New status (pending, extracting, extracted,
                    processing, staged, error)
            **kwargs: Additional fields to update (e.g., file_count=123, error_msg="...")

        Side effects:
            Updates ZIP record and commits.

        Example:
            >>> db.update_zip_status("takeout-001.zip", "extracted",
            ...                      file_count=1500, extracted_at="2024-01-20 10:30")
        """
        sets = ["status = ?"]
        values = [status]
        for k, v in kwargs.items():
            sets.append(f"{k} = ?")
            values.append(v)
        values.append(name)
        self.conn.execute(f"UPDATE zips SET {', '.join(sets)} WHERE name = ?", values)
        self.conn.commit()

    def mark_zip_deleted(self, zip_name: str):
        """
        Record that a ZIP file was deleted after extraction.

        Args:
            zip_name: ZIP filename

        Side effects:
            Updates deleted_at timestamp and commits.

        Example:
            >>> db.mark_zip_deleted("takeout-001.zip")
        """
        from datetime import datetime

        deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("UPDATE zips SET deleted_at = ? WHERE name = ?", (deleted_at, zip_name))
        self.conn.commit()

    def get_zip_status(self, name: str) -> str | None:
        """
        Get current processing status of a ZIP file.

        Args:
            name: ZIP filename

        Returns:
            Current status string or None if ZIP not registered
        """
        row = self.conn.execute("SELECT status FROM zips WHERE name = ?", (name,)).fetchone()
        return row["status"] if row else None

    def get_pending_zips(self) -> list[str]:
        """
        Get list of ZIPs that need to be extracted.

        Returns:
            List of ZIP filenames in 'pending' or 'error' state, sorted by name
        """
        rows = self.conn.execute(
            "SELECT name FROM zips WHERE status IN ('pending', 'error') ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_zips_needing_processing(self) -> list[str]:
        """
        Get list of ZIPs that need batch processing (validation, metadata, hashing, organization).

        Returns:
            List of ZIP filenames in 'extracted' or 'processing' state, sorted by name
        """
        rows = self.conn.execute(
            "SELECT name FROM zips WHERE status IN ('extracted', 'processing') ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_intermediate_zips(self) -> list[dict[str, Any]]:
        """
        Get list of ZIPs stuck in intermediate states (for recovery).

        Intermediate states are states that should not persist after a clean
        shutdown (extracting, processing). These indicate interrupted operations
        that need recovery.

        Returns:
            List of dictionaries with ZIP name and status, sorted by name
            Example: [{"name": "takeout-001", "status": "extracting"}, ...]

        Example:
            >>> db.get_intermediate_zips()
            [{"name": "takeout-001", "status": "extracting"},
             {"name": "takeout-002", "status": "processing"}]
        """
        rows = self.conn.execute(
            "SELECT name, status FROM zips WHERE status IN ('extracting', 'processing') ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]

    def register_file(self, zip_name: str, original_path: str, **kwargs):
        """
        Register a media file in the database.

        Args:
            zip_name: ZIP file this media file came from
            original_path: Full path to extracted file
            **kwargs: Additional file metadata (file_size, has_json, json_path, etc.)

        Side effects:
            Inserts or replaces file record (does not auto-commit).

        Note:
            Call commit() after batch operations for performance.
        """
        cols = ["zip_name", "original_path"] + list(kwargs.keys())
        vals = [zip_name, original_path] + list(kwargs.values())
        placeholders = ", ".join(["?"] * len(vals))
        self.conn.execute(
            f"INSERT OR REPLACE INTO files ({', '.join(cols)}) VALUES ({placeholders})", vals
        )

    def update_file_status(self, original_path: str, new_status: str) -> None:
        """
        Update the status of a file in the database.

        Args:
            original_path: Full path to the file (as stored in files.original_path)
            new_status: New status value ('organized', 'error', etc.)

        Side effects:
            Updates the status column for the matching file record.

        Example:
            >>> db.update_file_status("/path/to/file.jpg", "organized")
        """
        self.conn.execute(
            "UPDATE files SET status = ? WHERE original_path = ?",
            (new_status, original_path),
        )

    def get_files_for_zip(self, zip_name: str, status: str | None = None) -> list[dict[str, Any]]:
        """
        Retrieve all files from a specific ZIP, optionally filtered by status.

        Args:
            zip_name: ZIP filename (without .zip extension, will be appended automatically)
            status: Optional status filter ('pending', 'meta_applied', etc.)

        Returns:
            List of file records as dictionaries

        Example:
            >>> db.get_files_for_zip("takeout-001")
            # Searches for files where zip_name = "takeout-001.zip"
        """
        # Add .zip extension for DB lookup (consistent with get_files_with_hash_for_zip)
        full_zip_name = zip_name if zip_name.endswith(".zip") else f"{zip_name}.zip"

        if status:
            rows = self.conn.execute(
                "SELECT * FROM files WHERE zip_name = ? AND status = ?", (full_zip_name, status)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM files WHERE zip_name = ?", (full_zip_name,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_files_with_hash_for_zip(self, zip_name: str) -> list[dict[str, Any]]:
        """
        Retrieve all files with content hashes from a specific ZIP.

        Used in incremental pipeline for organizing files from a single ZIP.
        Only returns files that have been hashed (ready for deduplication check).

        Args:
            zip_name: ZIP filename (without .zip extension)

        Returns:
            List of file records as dictionaries, only files with content_hash set

        Example:
            >>> db.get_files_with_hash_for_zip("takeout-001")
            [{'id': 1, 'original_path': '/extracted/takeout-001/IMG_1234.jpg',
              'content_hash': 'abc123', ...}, ...]
        """
        rows = self.conn.execute(
            """
            SELECT * FROM files
            WHERE zip_name = ? AND content_hash IS NOT NULL
            ORDER BY id
            """,
            (zip_name + ".zip",),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_file(self, file_id: int, **kwargs):
        """
        Update file record fields.

        Args:
            file_id: Database ID of file record
            **kwargs: Fields to update (status='organized', content_hash='abc123', etc.)

        Side effects:
            Updates file record (does not auto-commit).

        Note:
            Call commit() after batch operations for performance.
        """
        sets = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [file_id]
        self.conn.execute(f"UPDATE files SET {', '.join(sets)} WHERE id = ?", values)

    def get_all_hashes(self) -> dict:
        """
        Get mapping of content hashes to first file ID for deduplication.

        Returns:
            Dictionary mapping {hash: first_file_id}

        Note:
            This is used to determine which file to keep when deduplicating.
            The file with the lowest ID (first encountered) is kept as the original.
        """
        rows = self.conn.execute(
            "SELECT content_hash, MIN(id) as first_id FROM files "
            "WHERE content_hash IS NOT NULL GROUP BY content_hash"
        ).fetchall()
        return {r["content_hash"]: r["first_id"] for r in rows}

    def register_json_file(self, zip_name: str, full_path: str):
        """
        Register a JSON metadata file in the database.

        Args:
            zip_name: ZIP file this JSON came from
            full_path: Full path to JSON file

        Side effects:
            Inserts JSON record (does not auto-commit).

        Note:
            Automatically extracts filename and derives base media name
            from the JSON filename by removing known JSON suffixes.
            Call commit() after batch operations for performance.
        """
        json_path = Path(full_path)
        filename = json_path.name

        # Derive base media name by removing JSON suffixes
        base_media_name = filename

        # Remove common JSON suffixes to get media filename
        json_suffixes = [
            ".supplemental-metadata.json",
            ".supplemental-metadat.json",
            ".supplemental-metada.json",
            ".supplemental-metad.json",
            ".supplemental-meta.json",
            ".supplemental-met.json",
            ".supplemental-me.json",
            ".supplemental-m.json",
            ".supplemental-.json",
            ".supplemental.json",
            ".supplementa.json",
            ".supplement.json",
            ".supplemen.json",
            ".suppleme.json",
            ".supplem.json",
            ".supple.json",
            ".suppl.json",
            ".supp.json",
            ".sup.json",
            ".su.json",
            ".s.json",
            ".json",
        ]

        for suffix in json_suffixes:
            if base_media_name.endswith(suffix):
                base_media_name = base_media_name[: -len(suffix)]
                break

        self.conn.execute(
            "INSERT OR IGNORE INTO json_files (zip_name, filename, full_path, base_media_name) VALUES (?, ?, ?, ?)",
            (zip_name, filename, full_path, base_media_name),
        )

    def find_json_for_media_db(self, media_path: str) -> str | None:
        """
        Find JSON metadata file for a media file using database queries.

        This method uses four strategies in order:
        1. Exact match in same directory (most accurate for duplicate filenames)
        2. Exact match on base_media_name globally (fallback)
        3. Try with numbered suffixes (1), (2), etc. in same directory
        4. Truncated filename search (46 char limit) in same directory

        Args:
            media_path: Full path to media file (e.g., '/path/extracted/2009/IMG_1234.HEIC')

        Returns:
            Full path to JSON file if found, None otherwise

        Note:
            This is MUCH faster than filesystem search, especially with many ZIPs.
            Uses indexed SQL queries instead of glob operations.
            Prioritizes JSONs in the same directory to handle duplicate filenames
            in different folders correctly (merge-extract).
        """
        media_path_obj = Path(media_path)
        media_filename = media_path_obj.name
        media_dir = str(media_path_obj.parent)

        # Strategy 1: Exact match in same directory (most accurate)
        row = self.conn.execute(
            """SELECT full_path FROM json_files
               WHERE base_media_name = ? AND full_path LIKE ?
               LIMIT 1""",
            (media_filename, f"{media_dir}/%"),
        ).fetchone()

        if row:
            return row["full_path"]  # type: ignore[no-any-return]

        # Strategy 2: Exact match on base_media_name globally (fallback)
        row = self.conn.execute(
            "SELECT full_path FROM json_files WHERE base_media_name = ? LIMIT 1",
            (media_filename,),
        ).fetchone()

        if row:
            return row["full_path"]  # type: ignore[no-any-return]

        # Strategy 3: Try with numbered suffixes (1), (2), etc. in same directory
        stem = media_path_obj.stem
        suffix = media_path_obj.suffix

        for i in range(1, 10):
            numbered_name = f"{stem}({i}){suffix}"
            row = self.conn.execute(
                """SELECT full_path FROM json_files
                   WHERE base_media_name = ? AND full_path LIKE ?
                   LIMIT 1""",
                (numbered_name, f"{media_dir}/%"),
            ).fetchone()
            if row:
                return row["full_path"]  # type: ignore[no-any-return]

        # Strategy 4: Truncated filename search (46 char limit) in same directory
        if len(media_filename) > 46:
            truncated = media_filename[:46]
            row = self.conn.execute(
                """SELECT full_path FROM json_files
                   WHERE base_media_name LIKE ? AND full_path LIKE ?
                   LIMIT 1""",
                (f"{truncated}%", f"{media_dir}/%"),
            ).fetchone()
            if row:
                return row["full_path"]  # type: ignore[no-any-return]

        return None

    def insert_organized_file(
        self, hash: str, original_name: str, final_path: str, source_zip: str, file_size: int
    ) -> None:
        """
        Record a file that has been successfully organized.

        This method is used for deduplication tracking. Once a file is recorded here,
        any subsequent files with the same hash will be identified as duplicates.

        Args:
            hash: Content hash of the file (unique identifier)
            original_name: Original filename (e.g., 'IMG_1234.jpg')
            final_path: Relative path from organized_dir (e.g., '2020/01/IMG_1234.jpg')
            source_zip: ZIP file this file came from (e.g., 'takeout-001.zip')
            file_size: File size in bytes

        Side effects:
            Inserts record into organized_files table (does not auto-commit).
            Uses INSERT OR IGNORE to safely handle hash collisions.

        Note:
            Call commit() after batch operations for performance.

        Example:
            >>> db.insert_organized_file(
            ...     hash='abc123def456',
            ...     original_name='IMG_1234.jpg',
            ...     final_path='2020/01/IMG_1234.jpg',
            ...     source_zip='takeout-001.zip',
            ...     file_size=5242880
            ... )
        """
        from datetime import datetime

        organized_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            """
            INSERT OR IGNORE INTO organized_files
            (hash, original_name, final_path, organized_at, source_zip, file_size)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (hash, original_name, final_path, organized_at, source_zip, file_size),
        )

    def check_duplicate(self, hash: str) -> bool:
        """
        Check if a file with this hash has already been organized.

        This is the core deduplication check. Returns True if the hash exists
        in the organized_files table, indicating this is a duplicate.

        Args:
            hash: Content hash to check

        Returns:
            True if hash exists (duplicate), False if unique (first occurrence)

        Example:
            >>> if db.check_duplicate('abc123def456'):
            ...     print("This file is a duplicate")
            ... else:
            ...     print("This is a unique file")
        """
        result = self.conn.execute(
            "SELECT 1 FROM organized_files WHERE hash = ? LIMIT 1", (hash,)
        ).fetchone()
        return result is not None

    def log_recovery(self, recovery_type: str, affected_count: int, details: dict) -> None:
        """
        Record recovery action in database for auditing.

        Args:
            recovery_type: Type of recovery ('zip_reset', 'orphaned_organized', etc.)
            affected_count: Number of items affected
            details: Dictionary with additional details (stored as JSON)

        Example:
            >>> db.log_recovery("zip_reset", 2, {"zip_name": "test.zip"})
        """
        import json
        from datetime import datetime

        self.conn.execute(
            """INSERT INTO recovery_log (timestamp, recovery_type, affected_count, details)
               VALUES (?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                recovery_type,
                affected_count,
                json.dumps(details),
            ),
        )
        self.conn.commit()

    def get_recovery_history(self, limit: int = 10) -> list[dict]:
        """
        Get recent recovery operations.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of recovery log records as dictionaries, ordered by most recent first

        Example:
            >>> history = db.get_recovery_history(limit=5)
            >>> for record in history:
            ...     print(f"{record['timestamp']}: {record['recovery_type']}")
        """
        rows = self.conn.execute(
            "SELECT * FROM recovery_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def commit(self):
        """
        Commit pending database transactions.

        Call this after batch operations to persist changes.
        Individual methods like register_zip() and update_zip_status()
        auto-commit, but register_file() and update_file() do not.
        """
        self.conn.commit()

    def close(self):
        """
        Close database connection.

        Should be called when done with the database to release resources.
        """
        self.conn.close()
