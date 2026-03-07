# Recovery and Retry Behavior

## Overview

The pipeline is designed to be interrupted and resumed safely at any point. All operations are idempotent and the database is the source of truth.

## File States and Transitions

```
pending → meta_applied → staged → organized
   ↓           ↓           ↓
error ← ────────────────────
```

### State Definitions

- **pending**: File extracted, awaiting metadata application
- **meta_applied**: Metadata written to EXIF, ready for hashing
- **staged**: Database updated with destination path, ready for move
- **organized**: File moved to final location and registered
- **error**: File failed processing (requires manual intervention)

## Retry Behavior

### Metadata Stage

**Normal case:**
- exiftool succeeds (returncode=0) → files advance to `meta_applied`

**Failure case:**
- exiftool fails (returncode!=0) → files stay `pending`
- Next run: automatic retry
- Rationale: exiftool failures are typically transient (memory, I/O)

**Individual file errors:**
- Logged to `logs/exif_warnings.txt`
- Files still marked `meta_applied` (optimistic)
- User can review warnings for corrupted files

### Organize Stage

**Transactional staging:**
1. Database updated: `status='staged'`, `staged_path='2020/05/photo.jpg'`
2. Database committed (crash-safe checkpoint)
3. File moved: `extracted/photo.jpg` → `organized/2020/05/photo.jpg`
4. Database updated: `status='organized'`
5. Database committed

**Crash scenarios:**

| Crash point | State | Recovery action |
|-------------|-------|-----------------|
| Before step 1 | `pending` | Retry organize |
| After step 2, before step 3 | `staged`, file not moved | Revert to `pending` |
| After step 3, before step 4 | `staged`, file moved | Complete: mark `organized` |
| After step 4 | `organized` | Skip (already done) |

## Recovery System

Recovery runs automatically at pipeline startup and reconciles:

1. **Intermediate ZIPs**: Reset stuck states (`extracting` → `pending`)
2. **Staged files**: Complete or revert (see table above)
3. **Orphaned organized files**: Register in database
4. **Orphaned extracted files**: Register with "unknown" ZIP
5. **Missing files**: Mark as error

## Manual Recovery

If automatic recovery doesn't resolve issues:

```bash
# View recovery history
takeout-photos --workdir ~/work status

# Reset all files to pending (nuclear option)
takeout-photos --workdir ~/work reset --files

# Reset specific ZIP
takeout-photos --workdir ~/work reset --zip takeout-001.zip
```

## Error Handling

Files marked as `error` require manual intervention:

```bash
# Check errors
takeout-photos --workdir ~/work status

# Review error details in database
sqlite3 ~/work/pipeline.db "SELECT original_path, error_msg FROM files WHERE status='error'"

# Fix issues, then reset errors to retry
takeout-photos --workdir ~/work reset --errors
```
