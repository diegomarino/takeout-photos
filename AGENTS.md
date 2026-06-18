# Takeout Photos - Development Reference

Essential development standards and references for AI-assisted development sessions.

**Tech Stack:** Black (line-length=100) • Ruff • mypy • pytest • exiftool

---

## Code Standards

### Style and Formatting

| Tool       | Configuration                                | Purpose                   |
| ---------- | -------------------------------------------- | ------------------------- |
| **Black**  | `line-length = 100`                          | Automatic code formatting |
| **Ruff**   | Pycodestyle, pyflakes, isort, flake8-bugbear | Linting with auto-fix     |
| **mypy**   | `--ignore-missing-imports`                   | Type checking             |
| **pytest** | With coverage                                | Testing                   |

### Naming Conventions

| Element             | Convention                   | Example                       |
| ------------------- | ---------------------------- | ----------------------------- |
| Modules/packages    | `lowercase_with_underscores` | `json_parser.py`              |
| Classes             | `PascalCase`                 | `PipelineDB`, `Config`        |
| Functions/variables | `snake_case`                 | `compute_hash()`, `file_path` |
| Constants           | `UPPER_CASE`                 | `MEDIA_EXTENSIONS`            |
| Privates            | `_leading_underscore`        | `_internal_func()`            |

### Import Order

```python
# 1. Standard library
import json
import logging
from pathlib import Path

# 2. Third-party
import pytest
from tqdm import tqdm

# 3. Local (absolute imports only)
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
```

### Docstrings (Google Style)

```python
def compute_hash(filepath: Path) -> str:
    """Compute the content hash of a file for deduplication.

    Args:
        filepath: Path to the file to hash

    Returns:
        Hex digest of the file content hash

    Raises:
        FileNotFoundError: If the file does not exist

    Example:
        >>> hash_val = compute_hash(Path("photo.jpg"))
        >>> print(hash_val)
        'abc123def456'
    """
    pass
```

### Type Hints

```python
from __future__ import annotations  # Always first import

from pathlib import Path
from typing import Any

def process_files(
    files: list[Path],
    config: Config,
    dry_run: bool = False
) -> dict[str, Any]:
    """Process files with configuration."""
    pass
```

---

## Conventional Commits

### Format

```text
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type       | Use                     | Example                                   |
| ---------- | ----------------------- | ----------------------------------------- |
| `feat`     | New functionality       | `feat(cli): add --resume flag`            |
| `fix`      | Bug fix                 | `fix(hash): handle empty files correctly` |
| `docs`     | Documentation           | `docs(api): update Pipeline examples`     |
| `test`     | Tests                   | `test(database): add transaction tests`   |
| `refactor` | Refactoring             | `refactor(stages): extract common logic`  |
| `perf`     | Performance improvement | `perf(hash): use xxhash by default`       |
| `style`    | Formatting, style       | `style: apply black formatting`           |
| `chore`    | Maintenance             | `chore(deps): update pytest to 9.0`       |
| `build`    | Build system            | `build: add dev extras to pyproject`      |
| `ci`       | CI/CD                   | `ci: add GitHub Actions workflow`         |

### Scopes

| Scope     | Module                                                   |
| --------- | -------------------------------------------------------- |
| `core`    | `core/config.py`, `core/database.py`, `core/pipeline.py` |
| `stages`  | `stages/*.py`                                            |
| `takeout` | `takeout/json_parser.py`, `takeout/json_finder.py`       |
| `exif`    | `exif/*.py`                                              |
| `hashing` | `hashing/hasher.py`                                      |
| `cli`     | `cli/*.py`                                               |
| `utils`   | `utils/*.py`                                             |
| `tests`   | `tests/`                                                 |
| `docs`    | `docs/`, `README.md`                                     |
| `build`   | `pyproject.toml`, build configuration                    |

### Examples

```bash
# Simple feature
git commit -m "feat(cli): add --resume flag for interrupted pipelines"

# Fix with description
git commit -m "fix(database): handle concurrent writes correctly

- Add database locking mechanism
- Retry on SQLITE_BUSY errors
- Add tests for concurrent access"

# With issue reference
git commit -m "fix(hash): handle empty files correctly

Fixes #123"
```

---

## Project Structure

```text
takeout-photos/
├── src/takeout_photos/
│   ├── core/          # config.py, database.py, pipeline.py, constants.py
│   ├── stages/        # 8 stages: extract, validate, metadata, hash, stage, dedupe, organize, qc
│   ├── takeout/       # json_parser.py, json_finder.py
│   ├── exif/          # operations.py, format_detection.py, validation.py
│   ├── hashing/       # hasher.py (xxhash/SHA256)
│   ├── cli/           # commands.py, main.py
│   └── utils/         # logging_setup.py, progress.py, dependencies.py
├── tests/
│   ├── unit/          # Per-module tests + stages/
│   └── integration/   # test_full_pipeline.py, test_cli.py
└── docs/              # api.md, pipeline-flow.md, architecture.md
```

### Module Responsibility

| Module              | Responsibility     | Lines      | Tests      |
| ------------------- | ------------------ | ---------- | ---------- |
| `core/config.py`    | Configuration      | ~100       | ✅         |
| `core/database.py`  | SQLite state       | ~450       | ✅ 32      |
| `core/pipeline.py`  | Orchestration      | ~250       | ✅ 18      |
| `stages/*.py`       | 8 stages (8 files) | ~1200      | ✅ 66      |
| `takeout/*.py`      | JSON parsing       | ~300       | ✅ 24      |
| `exif/*.py`         | EXIF operations    | ~350       | ✅ 27      |
| `hashing/hasher.py` | Content hashing    | ~110       | ✅ 18      |
| `cli/*.py`          | Command-line       | ~400       | ✅ 21      |
| `utils/*.py`        | Utilities          | ~250       | ✅ 27      |
| **Total**           | **22 modules**     | **~3,400** | **✅ 231** |

---

## Essential Commands

**IMPORTANT:** All commands below require activating the virtual environment first:

```bash
# Activate virtual environment (required for all commands below)
source .venv/bin/activate

# When done, deactivate with:
deactivate
```

### Testing

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Unit tests only
pytest tests/unit/

# Test by name
pytest -k "test_compute_hash"

# With coverage
pytest --cov=takeout_photos --cov-report=html

# Terminal coverage report
pytest --cov=takeout_photos --cov-report=term-missing
```

### Quality Checks

```bash
# Check formatting
black --check --line-length=100 src/ tests/

# Apply formatting
black --line-length=100 src/ tests/

# Linting
ruff check src/ tests/

# Auto-fix lint errors
ruff check --fix src/ tests/

# Type checking
mypy src/ --ignore-missing-imports

# All-in-one check
black --check --line-length=100 src/ tests/ && \
ruff check src/ tests/ && \
mypy src/ --ignore-missing-imports && \
pytest tests/ -v
```

### Git

```bash
# Show status and changes
git status
git diff
git diff --staged

# View recent history
git log --oneline -10

# Stage and commit
git add <files>
git commit -m "type(scope): description"
```

---

## CLI Reference

### CLI Options Reference

| Option                        | Purpose                                     | Example                                                               |
| ----------------------------- | ------------------------------------------- | --------------------------------------------------------------------- |
| `--doctor`                    | Run dependency + pipeline health checks     | `takeout-photos --doctor`                                             |
| `--workdir PATH`              | Base working directory (required)           | `takeout-photos --workdir ~/test_data process`                        |
| `--workers N`                 | Parallel workers for hashing (default: 4)   | `takeout-photos --workdir ~/work --workers 8 process`                 |
| `--dry-run`                   | Simulate without making changes             | `takeout-photos --workdir ~/work --dry-run process`                   |
| `--verbose, -v`               | Enable debug logging                        | `takeout-photos --workdir ~/work --verbose process`                   |
| `--layout LAYOUT`             | Organization: `yyyy_mm` (default) or `yyyy` | `takeout-photos --workdir ~/work --layout yyyy process`               |
| `--dated-filenames`           | Prefix filenames with YYYY-MM-DD\_          | `takeout-photos --workdir ~/work --dated-filenames process`           |
| `--organized-dir PATH`        | Custom output directory                     | `takeout-photos --workdir ~/work --organized-dir ~/Photos process`    |
| `--keep-extracted-files`      | Preserve extracted/ after organizing        | `takeout-photos --workdir ~/work --keep-extracted-files process`      |
| `--delete-zips-after-extract` | ⚠️ Delete ZIPs after extraction             | `takeout-photos --workdir ~/work --delete-zips-after-extract process` |
| `--checkpoint-interval N`     | Commit database every N files/hashes        | `takeout-photos --workdir ~/work --checkpoint-interval 1000 process`  |
| `--skip-deps-check`           | Skip dependency verification                | `takeout-photos --workdir ~/work --skip-deps-check process`           |

### Common Development Workflows

**Testing changes safely:**

```bash
# Dry-run with verbose output to see what would happen
takeout-photos --workdir ~/test_data --dry-run --verbose process
```

**Development testing:**

```bash
# Quick test run with dependency checks skipped
takeout-photos --workdir ~/test_data --skip-deps-check --verbose process
```

**Performance testing:**

```bash
# Test with maximum parallelization
takeout-photos --workdir ~/test_data --workers 8 --verbose process
```

**Integration testing:**

```bash
# Full pipeline test with all options
takeout-photos \
  --workdir ~/test_data \
  --layout yyyy \
  --dated-filenames \
  --keep-extracted-files \
  --verbose \
  process
```

**Pre-deployment check:**

```bash
# Verify all dependencies before running
takeout-photos --doctor
```

---

## Quick Reference

- **Line length:** 100 characters
- **Import style:** Absolute imports only (`from takeout_photos.core import Config`)
- **Test coverage:** Maintain existing coverage levels
- **Commit format:** Always use conventional commits with appropriate scope
- **Type hints:** Required for all public functions
- **Docstrings:** Google style for all public APIs
