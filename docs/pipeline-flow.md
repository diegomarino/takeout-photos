# Pipeline Flow Diagrams

Visual flowcharts for each stage of the Google Photos Takeout processing pipeline.

---

## Table of Contents

- [Pipeline Flow Diagrams](#pipeline-flow-diagrams)
  - [Table of Contents](#table-of-contents)
  - [Complete Pipeline Overview](#complete-pipeline-overview)
  - [Phase 1: ZIP Extraction](#phase-1-zip-extraction)
  - [Phase 1b: Format Validation](#phase-1b-format-validation)
  - [Phase 2: Metadata Application](#phase-2-metadata-application)
  - [Phase 3: Content Hashing](#phase-3-content-hashing)
  - [Phase 4: Organization + Inline Deduplication](#phase-4-organization--inline-deduplication)
  - [Phase 5: Quality Control](#phase-5-quality-control)
  - [Database State Transitions](#database-state-transitions)
  - [Performance Characteristics](#performance-characteristics)
  - [Error Recovery](#error-recovery)
  - [Recovery System](#recovery-system)
  - [See Also](#see-also)

---

## Complete Pipeline Overview

High-level view of the entire pipeline processing flow.

```mermaid
flowchart TD
    START([Start: ZIPs in zips/]) --> PHASE1[Phase 1: Extract ZIPs]
    PHASE1 --> |extracted/| PHASE1B[Phase 1b: Validate Formats]
    PHASE1B --> PHASE2[Phase 2: Apply Metadata]
    PHASE2 --> PHASE3[Phase 3: Compute Hashes]
    PHASE3 --> PHASE4[Phase 4: Organize + Inline Dedup]
    PHASE4 --> |organized_dir/| PHASE5[Phase 5: Quality Control]
    PHASE5 --> |logs/qc_*.txt| END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style PHASE1 fill:#e3f2fd,color:#333333
    style PHASE1B fill:#e3f2fd,color:#333333
    style PHASE2 fill:#fff3e0,color:#333333
    style PHASE3 fill:#fff3e0,color:#333333
    style PHASE4 fill:#f3e5f5,color:#333333
    style PHASE5 fill:#e0f2f1,color:#333333
```

**Processing Model:**

- **Phase 1**: Merge-extract all ZIPs to a shared `extracted/` directory
- **Phases 1b-4**: Per-ZIP processing (validate → metadata → hash → organize + inline dedupe)
- **Phase 5**: Global QC report (run once at end)

---

## Phase 1: ZIP Extraction

Extract ZIP files and register media files with associated JSON metadata.

```mermaid
flowchart TD
    START([Start: ZIP file]) --> REGISTER[Register ZIP\nStatus: pending]
    REGISTER --> UPDATE1[Update status:\nextracting]
    UPDATE1 --> EXTRACT[Extract ZIP\nto extracted/ merge-extract]
    EXTRACT --> SCAN_JSON[Scan for all\nJSON files]
    SCAN_JSON --> REGISTER_JSON[Register JSON files\nin json_files table\nIndexed by base_media_name]
    REGISTER_JSON --> SCAN_MEDIA[Scan for all\nmedia files]
    SCAN_MEDIA --> LOOP_START{More media\nfiles?}
    LOOP_START --> |Yes| CHECK_EXT{Is media\nfile?}
    CHECK_EXT --> |Yes| FIND_JSON[Look up JSON in DB\nby filename]
    FIND_JSON --> HAS_JSON{JSON\nfound?}
    HAS_JSON --> |Yes| REGISTER_WITH[Register file\nwith JSON path]
    HAS_JSON --> |No| REGISTER_NO[Register file\nwithout JSON]
    REGISTER_WITH --> LOOP_START
    REGISTER_NO --> LOOP_START
    CHECK_EXT --> |No| LOOP_START
    LOOP_START --> |No| UPDATE2[Update ZIP status:\nextracted\nfile_count=N]
    UPDATE2 --> COMMIT[Commit to DB]
    COMMIT --> END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style EXTRACT fill:#bbdefb,color:#333333
    style REGISTER_JSON fill:#c5e1a5,color:#333333
    style LOOP_START fill:#fff9c4,color:#333333
    style CHECK_EXT fill:#fff9c4,color:#333333
    style HAS_JSON fill:#fff9c4,color:#333333
```

**Key Operations:**

1. Extract ZIP to shared `extracted/` directory (merge-extract)
2. Validate paths to prevent Zip Slip attacks (rejects `../` and absolute paths)
3. Handle path collisions with checksum comparison (rename conflicts with `_conflict_N` suffix)
4. Register all JSON files for fast lookup (indexed table)
5. Register media files with associated JSON paths
6. Update ZIP status: `pending` → `extracting` → `extracted`

**Security & Safety:**

- Path traversal protection prevents malicious ZIPs from writing outside extraction directory
- Checksum-based collision detection prevents data loss when different ZIPs have files with same paths

**Database Tables Used:**

- `zips`: Track extraction state
- `json_files`: Indexed JSON file lookups
- `files`: Media file registry

---

## Phase 1b: Format Validation

Validate file formats and correct mismatched extensions using parallel workers.

```mermaid
flowchart TD
    START([Start: ZIP extracted]) --> GET_FILES[Get all files\nfor this ZIP]
    GET_FILES --> POOL[Create worker pool\nN=config.workers]
    POOL --> PARALLEL[Dispatch validation\ntasks to workers]
    PARALLEL --> WORKER1[Worker 1:\nDetect type + Read EXIF\nvia exiftool]
    PARALLEL --> WORKER2[Worker 2:\nDetect type + Read EXIF\nvia exiftool]
    PARALLEL --> WORKERN[Worker N:\nDetect type + Read EXIF\nvia exiftool]
    WORKER1 --> COLLECT
    WORKER2 --> COLLECT
    WORKERN --> COLLECT[Main thread:\nCollect results]
    COLLECT --> LOOP{More\nresults?}
    LOOP --> |Yes| CHECK{Extension\nmatches type?}
    CHECK --> |No| MAP[Map type to\ncorrect extension\nJPEG→jpg, HEIC→heic]
    MAP --> RENAME[Rename file:\noriginal.HEIC\n→ original.HEIC.jpg]
    RENAME --> UPDATE_DB[Update file path\nin database]
    UPDATE_DB --> STORE_EXIF[Store existing EXIF\ndatetime if present]
    CHECK --> |Yes| LOOP
    STORE_EXIF --> LOOP
    LOOP --> |No| COMMIT[Commit changes]
    COMMIT --> END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style POOL fill:#b3e5fc,color:#333333
    style PARALLEL fill:#c5e1a5,color:#333333
    style RENAME fill:#fff59d,color:#333333
    style CHECK fill:#fff9c4,color:#333333
```

**Key Operations:**

1. Create ProcessPoolExecutor with N workers (configurable via `config.workers`)
2. Dispatch file validation tasks to parallel workers (I/O-bound exiftool calls)
3. Workers detect real file type and read EXIF metadata in a single exiftool call
4. Main thread collects results and handles file renaming (avoids race conditions)
5. Correct extension if mismatched: `IMG_6486.HEIC` → `IMG_6486.HEIC.jpg`
6. Update database with corrected paths
7. Store existing EXIF datetime for comparison

**Parallelization:**

- Uses ProcessPoolExecutor for parallel exiftool subprocess calls
- 3-4x speedup on I/O-bound file type detection operations
- Worker pool size configurable (default: 4 workers)
- Main thread handles file renaming to prevent race conditions

**Common Corrections:**

- `.HEIC` → `.jpg` (HEIC files that are actually JPEG)
- `.PNG` → `.jpg` (PNG files that are actually JPEG)

---

## Phase 2: Metadata Application

Apply JSON metadata to EXIF tags using batch exiftool operations with validation.

```mermaid
flowchart TD
    START([Start: Validated files]) --> GET[Get pending files\nfor ZIP]
    GET --> CREATE_ARGS[Create exiftool\nargs file for batch]
    CREATE_ARGS --> LOOP{More\nfiles?}
    LOOP --> |Yes| PARSE[Parse JSON:\nphotoTakenTime\ngeoData]
    PARSE --> HAS_TS{Has\nphotoTakenTime?}
    HAS_TS --> |Yes| CONVERT[Convert UNIX ts\nto EXIF format\nYYYY:MM:DD HH:MM:SS]
    CONVERT --> ADD_DATE[Add to args:\n-DateTimeOriginal\n-CreateDate]
    HAS_TS --> |No| HAS_GPS{Has\ngeoData?}
    ADD_DATE --> HAS_GPS{Has\ngeoData?}
    HAS_GPS --> |Yes| ADD_GPS[Add to args:\n-GPSLatitude\n-GPSLongitude\n-GPSLatitudeRef\n-GPSLongitudeRef]
    HAS_GPS --> |No| LOOP
    ADD_GPS --> LOOP
    LOOP --> |No| RUN[Run exiftool\nbatch mode -@]
    RUN --> CHECK{returncode\n== 0?}
    CHECK --> |Yes| UPDATE[Mark files:\nmeta_applied\nStore exif_datetime]
    CHECK --> |No| STAY[Files remain:\npending\nLog error]
    UPDATE --> COMMIT[Commit to DB]
    STAY --> END
    COMMIT --> END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style PARSE fill:#ffe0b2,color:#333333
    style RUN fill:#c5cae9,color:#333333
    style CHECK fill:#fff9c4,color:#333333
    style HAS_TS fill:#fff9c4,color:#333333
    style HAS_GPS fill:#fff9c4,color:#333333
    style STAY fill:#ffccbc,color:#333333
```

**Key Operations:**

1. Retrieve all pending files for the ZIP
2. Parse JSON for `photoTakenTime` and `geoData`
3. Generate exiftool arguments file (batch mode)
4. Execute single exiftool command for all files
5. Validate exiftool return code
6. If success (returncode=0): Mark files as `meta_applied`, store `exif_datetime`
7. If failure: Files stay `pending` for automatic retry

**Why Batch Mode:**

- 1 exiftool process for N files (not N processes)
- 10x+ faster than per-file execution
- Typical: 30-60 seconds for 1000 files

**EXIF Tags Written:**

- `DateTimeOriginal`: From JSON `photoTakenTime`
- `CreateDate`: Same as DateTimeOriginal
- `GPSLatitude`, `GPSLongitude`: From JSON `geoData`
- `GPSLatitudeRef`, `GPSLongitudeRef`: N/S, E/W based on coordinate signs

**Idempotency & Retry:**

- Validation ensures files only advance on success
- exiftool failures leave files in `pending` state
- Next run automatically retries failed files
- Prevents partial metadata corruption from crashes

---

## Phase 3: Content Hashing

Compute content hashes for deduplication using parallel workers.

```mermaid
flowchart TD
    START([Start: Metadata applied]) --> GET[Get files without\ncontent_hash]
    GET --> CHECK{xxhash\navailable?}
    CHECK --> |Yes| SET_ALGO[Use xxhash\n2-3x faster]
    CHECK --> |No| SET_ALGO2[Use SHA256\nstdlib fallback]
    SET_ALGO --> POOL
    SET_ALGO2 --> POOL[Create worker pool\nN=config.workers]
    POOL --> PARALLEL[Process files\nin parallel]
    PARALLEL --> WORKER1[Worker 1:\nCompute hash\n64KB chunks]
    PARALLEL --> WORKER2[Worker 2:\nCompute hash\n64KB chunks]
    PARALLEL --> WORKER3[Worker N:\nCompute hash\n64KB chunks]
    WORKER1 --> STORE1[Store hash\nin database]
    WORKER2 --> STORE2[Store hash\nin database]
    WORKER3 --> STORE3[Store hash\nin database]
    STORE1 --> WAIT{All\ncomplete?}
    STORE2 --> WAIT
    STORE3 --> WAIT
    WAIT --> |Yes| COMMIT[Commit to DB]
    COMMIT --> END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style CHECK fill:#fff9c4,color:#333333
    style POOL fill:#b3e5fc,color:#333333
    style PARALLEL fill:#c5e1a5,color:#333333
    style WAIT fill:#fff9c4,color:#333333
```

**Key Operations:**

1. Identify files without content hashes
2. Select hash algorithm (xxhash or SHA256)
3. Create ProcessPoolExecutor with N workers
4. Compute hashes in parallel (CPU-bound)
5. Store hashes in database
6. Mark files as `status='error'` if hashing fails (file deleted, permissions, I/O errors)

**Hash Algorithm Selection:**

| Algorithm | Speed | Digest | Use |
| --- | --- | --- | --- |
| xxhash | 2-3x faster | 16 chars | Preferred |
| SHA256 | Baseline | 64 chars | Fallback |

**Performance:**

- For 1000 files @ 2MB each with 8 workers:
  - xxhash: ~30 seconds
  - SHA256: ~90 seconds

---

## Phase 4: Organization + Inline Deduplication

Organize files into the final directory structure and deduplicate inline using transactional DB-before-move pattern.

```mermaid
flowchart TD
    START([Start: ZIP ready\nhash complete]) --> GET["Get files\nwith content_hash\nstatus NOT IN\n{organized, staged}"]
    GET --> RECOVER{Staged files\nfrom crash?}
    RECOVER --> |Yes| CHECK_MOVED{File\nat staged_path?}
    CHECK_MOVED --> |Yes| COMPLETE[Complete staging:\nInsert organized_files\nMark organized]
    CHECK_MOVED --> |No| REVERT[Revert to pending:\nClear staged_path]
    COMPLETE --> GET
    REVERT --> GET
    RECOVER --> |No| LOOP{More\nfiles?}
    LOOP --> |Yes| CHECK_DUP{Hash already\nin organized_files?}
    CHECK_DUP --> |Yes| MOVE_DUP["Move to duplicates/\n(preserve relative path)\nMark organized"]
    CHECK_DUP --> |No| COMPUTE[Compute dest path:\nYYYY/MM/ or no_date/]
    COMPUTE --> STAGE[DB-before-move:\nstatus='staged'\nstaged_path=relative]
    STAGE --> MKDIR[Create destination\ndirectory]
    MKDIR --> MOVE[Move file to\ndestination]
    MOVE --> FINALIZE[Insert organized_files\nUpdate status='organized'\nfinal_path=staged_path]
    MOVE_DUP --> LOOP
    FINALIZE --> LOOP
    LOOP --> |No| END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style CHECK_DUP fill:#fff9c4,color:#333333
    style RECOVER fill:#fff9c4,color:#333333
    style CHECK_MOVED fill:#fff9c4,color:#333333
    style STAGE fill:#ffeb3b,color:#333333
    style MOVE fill:#81c784,color:#333333
    style REVERT fill:#ffccbc,color:#333333
```

**Key Operations:**

1. **Recovery**: Check for staged files from previous crash
   - If file exists at `staged_path`: Complete staging → `organized`
   - If file missing: Revert to `pending` for retry
2. Iterate files with hashes for a ZIP
3. Skip files with `status='organized'` or `status='staged'` (retry support)
4. If hash exists in `organized_files`, move to `duplicates/`
5. **DB-before-move pattern** (crash-safe):
   - Compute destination path
   - Mark `status='staged'`, store `staged_path` in DB
   - Move file to destination
   - Insert into `organized_files`, mark `status='organized'`
   - Commit per batch (recovery detects `staged` files after a crash)
6. Track errors and mark ZIP as `'error'` if any files fail

**Idempotency & Crash Safety:**

- Files with `status='organized'` or `status='staged'` are skipped
- Local recovery: staged files from previous run are detected and completed/reverted
- DB-before-move ensures crash-safety (database tracks intent before filesystem change)
- Failed files can be retried without re-processing successful ones
- Prevents moving already-organized files to duplicates/ on subsequent runs

**Organization Layouts:**

| Layout | Example Path |
| --- | --- |
| `yyyy/mm` (default) | `organized_dir/2023/05/photo.jpg` |
| `no_date` (no EXIF date) | `organized_dir/no_date/photo.jpg` |

**Crash Scenarios:**

| Crash Point | DB State | Filesystem | Recovery |
| --- | --- | --- | --- |
| Before staging | `pending` | In extracted/ | Retry organize |
| After staging, before move | `staged` | In extracted/ | Revert to `pending` |
| After move, before finalize | `staged` | In organized/ | Complete: mark `organized` |
| After finalize | `organized` | In organized/ | Skip (already done) |

---

## Phase 5: Quality Control

Generate quality control report identifying potential metadata issues.

```mermaid
flowchart TD
    START([Start: Organized]) --> SCAN[Scan\norganized_dir/]
    SCAN --> GET_NO_DATE[Count files in\nno_date/]
    GET_NO_DATE --> QUERY_OLD[Query exiftool:\nDateTimeOriginal < 1995]
    QUERY_OLD --> QUERY_FUTURE[Query exiftool:\nDateTimeOriginal > now]
    QUERY_FUTURE --> QUERY_SUSPICIOUS[Query exiftool:\n1970-01-01, 2000-01-01]
    QUERY_SUSPICIOUS --> QUERY_STATS[Count files by year\nfrom filesystem]
    QUERY_STATS --> BUILD[Build QC report:\nAll findings + statistics]
    BUILD --> WRITE[Write report to:\nlogs/YYYYMMDD_HHMMSS_qc.txt]
    WRITE --> LOG[Log summary to console]
    LOG --> END([Complete])

    style START fill:#e1f5e1,color:#333333
    style END fill:#ffe1e1,color:#333333
    style BUILD fill:#ffab91,color:#333333
    style WRITE fill:#a5d6a7,color:#333333
```

**Key Operations:**

1. Find files without DateTimeOriginal (in `no_date/`)
2. Detect suspiciously old dates (< 1995)
3. Detect future dates (> today)
4. Detect suspicious epoch dates (1970-01-01, 2000-01-01)
5. Generate statistics by year
6. Write comprehensive report to `logs/YYYYMMDD_HHMMSS_qc.txt`

**QC Report Contents:**

| Section | Description |
| --- | --- |
| **No Date** | Files in `no_date/` directory |
| **Very Old** | Dates before 1995 (unlikely) |
| **Future Dates** | Dates after today (incorrect clock) |
| **Suspicious** | Epoch dates (1970-01-01, 2000-01-01) |
| **Statistics** | File count by year |

**Use Cases:**

- Identify files needing manual date correction
- Verify pipeline processed files correctly
- Generate statistics for reporting
- Detect metadata corruption or export issues

---

## Database State Transitions

How each phase updates the database state:

```mermaid
stateDiagram-v2
    [*] --> pending: ZIP registered
    pending --> extracting: Phase 1 start
    extracting --> extracted: Extraction complete
    extracted --> processing: Phase 2 start
    processing --> organized: Phase 2 complete
    organized --> [*]: All phases done

    note right of pending
        No files registered yet
    end note

    note right of extracted
        Files registered
        JSON lookup table populated
    end note

    note right of processing
        Validate + metadata
        Hash + organize
    end note

    note right of organized
        Files in organized_dir/
        Ready for QC
    end note
```

**File Status Transitions:**

```mermaid
stateDiagram-v2
    [*] --> pending: File registered
    pending --> meta_applied: Phase 2a (metadata applied)
    meta_applied --> staged: Phase 4 (DB-before-move)
    staged --> organized: Phase 4 (move complete)
    meta_applied --> organized: Phase 4 (duplicate → duplicates/)
    organized --> [*]
    pending --> error: Hash/move failure
```

---

## Performance Characteristics

Expected duration for each phase (200K photos, ~50GB, SSD):

| Phase | Duration | Bottleneck | Parallelizable |
| --- | --- | --- | --- |
| **1: Extract** | 30-60 min | I/O (disk read) | Per ZIP |
| **1b: Validate** | 5-7 min | exiftool calls (I/O-bound) | ✅ Per file (ProcessPoolExecutor) |
| **2: Metadata** | 20-40 min | exiftool batch | Per ZIP |
| **3: Hash** | 30-60 min | CPU (hashing) | ✅ Per file (ProcessPoolExecutor) |
| **4: Organize + Dedupe** | 30-60 min | I/O (move) | Per ZIP |
| **5: QC** | 1-5 min | exiftool scans | No |
| **Total** | **2-4 hours** | --- | --- |

**Optimization Opportunities:**

1. **Install xxhash**: 2-3x faster hashing (Phase 3)
2. **Use SSD**: 10x+ faster I/O (all phases)
3. **Adjust workers**: Match CPU cores (Phases 1b, 3 use `config.workers`)
4. **Process in parallel**: Run multiple ZIPs through Phases 1-4 simultaneously (when safe)

**Parallelized Phases:**

- **Phase 1b (Validate)**: Uses ProcessPoolExecutor for parallel exiftool calls (3-4x speedup)
- **Phase 3 (Hash)**: Uses ProcessPoolExecutor for parallel content hashing (N-worker speedup)

---

## Error Recovery

How the pipeline handles failures at each stage:

```mermaid
flowchart TD
    FAIL([Phase fails]) --> CHECK{Which\nphase?}
    CHECK --> |Phase 1-4| ZIP_LEVEL[ZIP-level failure]
    CHECK --> |Phase 5| GLOBAL_LEVEL[Global failure]

    ZIP_LEVEL --> MARK_ERROR[Mark ZIP as error\nRecord error_msg]
    MARK_ERROR --> OTHER[Other ZIPs\ncontinue processing]
    OTHER --> RETRY1[Rerun: Reset ZIP\nthen process again]

    GLOBAL_LEVEL --> STOP[Stop pipeline\nState saved]
    STOP --> RETRY2[Rerun: Resume from\nlast checkpoint]

    RETRY1 --> SUCCESS{Success?}
    RETRY2 --> SUCCESS
    SUCCESS --> |Yes| COMPLETE([Complete])
    SUCCESS --> |No| INVESTIGATE[Investigate error\nCheck logs/]

    style FAIL fill:#ffcdd2,color:#333333
    style COMPLETE fill:#c8e6c9,color:#333333
    style CHECK fill:#fff9c4,color:#333333
    style SUCCESS fill:#fff9c4,color:#333333
```

**Recovery Commands:**

```bash
# Reset failed ZIP
takeout-photos --workdir ~/work reset --zip takeout-003.zip

# Resume processing
takeout-photos --workdir ~/work process
```

---

## Recovery System

Automatic recovery runs at pipeline startup to detect and fix inconsistencies from crashes or interruptions.

```mermaid
flowchart TD
    START([Pipeline Start]) --> RECOVERY[Run Recovery Check]
    RECOVERY --> CHECK_ZIPS[Check for ZIPs in\nintermediate states]
    CHECK_ZIPS --> RESET_ZIPS{Found\nextracting/processing?}
    RESET_ZIPS --> |Yes| RESET_Z[Reset to pending/extracted]
    RESET_ZIPS --> |No| CHECK_STAGED
    RESET_Z --> CHECK_STAGED[Check for files\nin staged state]
    CHECK_STAGED --> STAGED{Found\nstaged files?}
    STAGED --> |Yes| CHECK_MOVED{File exists at\nstaged_path?}
    CHECK_MOVED --> |Yes| COMP[Complete staging:\nMark organized]
    CHECK_MOVED --> |No| REV[Revert to pending:\nClear staged_path]
    COMP --> CHECK_ORPHAN
    REV --> CHECK_ORPHAN
    STAGED --> |No| CHECK_ORPHAN[Scan organized/\nfor orphaned files]
    CHECK_ORPHAN --> ORPHAN{Unregistered\nfiles found?}
    ORPHAN --> |Yes| REG[Register in DB\nCompute hash\nUpdate files table]
    ORPHAN --> |No| CHECK_MISSING
    REG --> CHECK_MISSING[Sample DB files\nfor missing paths]
    CHECK_MISSING --> MISSING{Files\nmissing?}
    MISSING --> |Yes| ERR[Mark as error\nwith error_msg]
    MISSING --> |No| REPORT
    ERR --> REPORT[Log recovery summary]
    REPORT --> CONTINUE([Continue Pipeline])

    style START fill:#e1f5e1,color:#333333
    style CONTINUE fill:#c8e6c9,color:#333333
    style RESET_ZIPS fill:#fff9c4,color:#333333
    style STAGED fill:#fff9c4,color:#333333
    style CHECK_MOVED fill:#fff9c4,color:#333333
    style ORPHAN fill:#fff9c4,color:#333333
    style MISSING fill:#fff9c4,color:#333333
    style COMP fill:#81c784,color:#333333
    style REV fill:#ffccbc,color:#333333
    style ERR fill:#ffccbc,color:#333333
```

**Recovery Operations:**

1. **Intermediate ZIPs**: Reset stuck states
   - `extracting` → `pending` (re-extract)
   - `processing` → `extracted` (re-process)

2. **Staged Files**: Complete or revert (see Phase 4 crash scenarios)
   - File at `staged_path`: Complete staging → `organized`
   - File missing: Revert to `pending` for retry

3. **Orphaned Organized Files**: Register in database
   - Scan `organized/` for unregistered files
   - Compute hash and insert into `organized_files`
   - Update `files` table if matching record exists

4. **Orphaned Extracted Files**: Register with "unknown" ZIP
   - Scan `extracted/` for unregistered files
   - Register with `zip_name='unknown'`

5. **Missing Files**: Mark as error
   - Sample files table (500 random for large datasets)
   - Verify paths exist on filesystem
   - Mark missing files with `status='error'`, `error_msg='File not found'`

**Performance:**

- Recovery check: ~30-45 seconds for 300k files
- Runs automatically at pipeline startup
- Only processes inconsistent records

**Recovery Log:**
All recovery operations are logged in the `recovery_log` table with counts and timestamps.

---

## See Also

- [API Reference](api.md) - Complete API documentation
- [Architecture](architecture.md) - Design decisions and module structure
- [Recovery and Retries](recovery-and-retries.md) - Detailed retry behavior and idempotency guarantees
- [README](../README.md) - Getting started and overview
