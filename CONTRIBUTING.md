# Contributing to Takeout Photos

Thank you for your interest in contributing! This guide will help you set up your development environment and understand our development workflow.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Environment Setup](#development-environment-setup)
- [Development Workflow](#development-workflow)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8+** (Python 3.11 or 3.12 recommended)
- **Git**
- **exiftool** (required for EXIF operations)

### Installing exiftool

**macOS (Homebrew):**

```bash
brew install exiftool
```

**Ubuntu/Debian:**

```bash
sudo apt-get install libimage-exiftool-perl
```

**Windows:**
Download from [exiftool.org](https://exiftool.org/)

---

## Development Environment Setup

### 1. Fork and Clone the Repository

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/diegomarino/takeout-photos.git
cd takeout-photos
```

### 2. Create a Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

```bash
# Install the package in editable mode with all dev dependencies
pip install -e ".[dev,fast]"

# Verify installation
takeout-photos --version
```

### 4. Install Pre-commit Hooks

Pre-commit hooks automatically run code quality checks before each commit:

```bash
# Install pre-commit (already included in dev dependencies)
# If needed: pip install pre-commit

# Install the git hooks (both pre-commit and commit-msg)
pre-commit install
pre-commit install --hook-type commit-msg

# (Optional) Run on all files to test
pre-commit run --all-files
```

### 5. Configure Your Editor

#### VS Code (Recommended)

The repository includes `.vscode/settings.json` with pre-configured settings:

1. **Install recommended extensions:**
   - VS Code will prompt you to install recommended extensions
   - Or manually install:
     - Python (`ms-python.python`)
     - Ruff (`charliermarsh.ruff`)
     - MyPy Type Checker (`ms-python.mypy-type-checker`)

2. **Select Python interpreter:**
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type "Python: Select Interpreter"
   - Choose `./.venv/bin/python`

3. **Verify settings:**
   - Format on save: ✅ Enabled
   - Ruff linting: ✅ Enabled
   - Auto-fix on save: ✅ Enabled

#### PyCharm/IntelliJ

1. **Configure Python interpreter:**
   - Go to **Settings** → **Project** → **Python Interpreter**
   - Add interpreter → Existing environment → Select `.venv/bin/python`

2. **Enable Black formatter:**
   - **Settings** → **Tools** → **Black**
   - Configure line length: 100

3. **Enable Ruff:**
   - **Settings** → **Tools** → **External Tools**
   - Add Ruff with path: `.venv/bin/ruff`

#### Other Editors

The `.editorconfig` file provides basic settings compatible with most editors.

---

## Development Workflow

### Project Structure

```text
takeout-photos/
├── src/takeout_photos/
│   ├── core/          # Configuration, database, pipeline orchestration
│   ├── stages/        # 8 pipeline stages
│   ├── takeout/       # Google Takeout JSON parsing
│   ├── exif/          # EXIF operations
│   ├── hashing/       # Content hashing (xxhash/SHA256)
│   ├── cli/           # Command-line interface
│   └── utils/         # Utilities (logging, progress, dependencies)
├── tests/
│   ├── unit/          # Unit tests per module
│   └── integration/   # Full pipeline integration tests
└── docs/              # Documentation
```

### Making Changes

1. **Create a feature branch:**

   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/bug-description
   ```

2. **Make your changes:**
   - Follow the code style guidelines below
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests:**

   ```bash
   # Run all tests
   pytest

   # Run with coverage
   pytest --cov=takeout_photos --cov-report=term-missing

   # Run specific test file
   pytest tests/unit/test_database.py

   # Run tests matching a pattern
   pytest -k "test_hash"
   ```

4. **Check code quality:**

   ```bash
   # Check formatting (don't modify)
   black --check --line-length=100 src/ tests/

   # Apply formatting
   black --line-length=100 src/ tests/

   # Check linting
   ruff check src/ tests/

   # Auto-fix linting issues
   ruff check --fix src/ tests/

   # Type checking
   mypy src/ --ignore-missing-imports

   # Run all checks
   black --check --line-length=100 src/ tests/ && \
   ruff check src/ tests/ && \
   mypy src/ --ignore-missing-imports && \
   pytest tests/ -v
   ```

---

## Code Quality

### Code Style

We use the following tools to maintain code quality:

| Tool       | Purpose                   | Configuration              |
| ---------- | ------------------------- | -------------------------- |
| **Black**  | Automatic code formatting | `line-length = 100`        |
| **Ruff**   | Linting & import sorting  | Pycodestyle + flake8       |
| **mypy**   | Static type checking      | `--ignore-missing-imports` |
| **pytest** | Testing framework         | With coverage reporting    |

### Naming Conventions

| Element             | Convention        | Example                    |
| ------------------- | ----------------- | -------------------------- |
| Modules/packages    | `snake_case`      | `json_parser.py`           |
| Classes             | `PascalCase`      | `PipelineDB`, `Config`     |
| Functions/variables | `snake_case`      | `compute_hash()`, `config` |
| Constants           | `UPPER_CASE`      | `MEDIA_EXTENSIONS`         |
| Private members     | `_leading_prefix` | `_internal_method()`       |

### Import Order

Always use absolute imports:

```python
from __future__ import annotations  # Always first

# 1. Standard library
import json
import logging
from pathlib import Path

# 2. Third-party packages
import pytest
from tqdm import tqdm

# 3. Local imports (absolute only)
from takeout_photos.core.config import Config
from takeout_photos.core.database import PipelineDB
```

### Type Hints

All public functions must have type hints:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

def process_files(
    files: list[Path],
    config: Config,
    dry_run: bool = False
) -> dict[str, Any]:
    """Process files with configuration.

    Args:
        files: List of file paths to process
        config: Configuration object
        dry_run: If True, don't make actual changes

    Returns:
        Dictionary with processing results
    """
    pass
```

### Docstrings

Use Google style for all public APIs:

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

---

## Testing

### Test Structure

- **Unit tests:** Test individual functions/methods in isolation
- **Integration tests:** Test complete workflows and CLI commands

### Writing Tests

```python
from __future__ import annotations

import pytest
from pathlib import Path

from takeout_photos.core.database import PipelineDB


def test_database_creation(tmp_path: Path):
    """Test that database is created correctly."""
    db_path = tmp_path / "test.db"
    db = PipelineDB(db_path)

    assert db_path.exists()
    assert db.conn is not None


def test_register_zip_file(tmp_path: Path):
    """Test registering a ZIP file in the database."""
    db = PipelineDB(tmp_path / "test.db")

    db.register_zip_file("takeout-001.zip", "/path/to/takeout-001.zip")
    db.commit()

    row = db.conn.execute(
        "SELECT * FROM zip_files WHERE zip_name = ?",
        ("takeout-001.zip",)
    ).fetchone()

    assert row is not None
    assert row[1] == "takeout-001.zip"
```

### Running Tests

```bash
# All tests
pytest

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Only unit tests
pytest tests/unit/

# Only integration tests
pytest tests/integration/

# With coverage report
pytest --cov=takeout_photos --cov-report=html
open htmlcov/index.html

# Test specific module
pytest tests/unit/test_database.py -v
```

---

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) for clear and structured commit history.

### Commit Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type       | Use                     | Example                                   |
| ---------- | ----------------------- | ----------------------------------------- |
| `feat`     | New feature             | `feat(cli): add --resume flag`            |
| `fix`      | Bug fix                 | `fix(hash): handle empty files correctly` |
| `docs`     | Documentation only      | `docs(api): update Pipeline examples`     |
| `test`     | Adding/updating tests   | `test(database): add transaction tests`   |
| `refactor` | Code refactoring        | `refactor(stages): extract common logic`  |
| `perf`     | Performance improvement | `perf(hash): use xxhash by default`       |
| `style`    | Formatting/style only   | `style: apply black formatting`           |
| `chore`    | Maintenance tasks       | `chore(deps): update pytest to 9.0`       |

### Scopes

| Scope     | Description                               |
| --------- | ----------------------------------------- |
| `core`    | Configuration, database, pipeline         |
| `stages`  | Pipeline stages (extract, validate, etc.) |
| `takeout` | JSON parsing                              |
| `exif`    | EXIF operations                           |
| `hashing` | Content hashing                           |
| `cli`     | Command-line interface                    |
| `utils`   | Utilities                                 |
| `tests`   | Test infrastructure                       |
| `docs`    | Documentation                             |

### Examples

```bash
# Simple feature
git commit -m "feat(cli): add --resume flag for interrupted pipelines"

# Bug fix with description
git commit -m "fix(database): handle concurrent writes correctly

- Add database locking mechanism
- Retry on SQLITE_BUSY errors
- Add tests for concurrent access"

# Breaking change
git commit -m "feat(core)!: change Config API to use Path objects

BREAKING CHANGE: All path parameters now require Path objects instead of strings"
```

---

## Pull Request Process

### Before Creating a PR

1. **Ensure all tests pass:**

   ```bash
   pytest tests/ -v
   ```

2. **Run code quality checks:**

   ```bash
   black --check --line-length=100 src/ tests/
   ruff check src/ tests/
   mypy src/ --ignore-missing-imports
   ```

3. **Update documentation:**
   - Update `README.md` if adding new features
   - Update docstrings for new/modified functions
   - Add examples if appropriate

4. **Commit your changes:**

   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push to your fork:**

   ```bash
   git push origin feature/your-feature-name
   ```

### Creating the PR

1. Go to the original repository on GitHub
2. Click "New Pull Request"
3. Select your fork and branch
4. Fill in the PR template:

   ```markdown
   ## Description

   Brief description of the changes

   ## Type of Change

   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing

   - [ ] All tests pass
   - [ ] Added new tests for new functionality
   - [ ] Tested manually (describe scenarios)

   ## Checklist

   - [ ] Code follows project style guidelines
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] No new warnings introduced
   ```

5. Submit the pull request

### PR Review Process

- Maintainers will review your PR
- Address any feedback or requested changes
- Once approved, your PR will be merged

---

## Questions or Issues?

- **Documentation:** See [`CLAUDE.md`](CLAUDE.md) for development reference
- **Issues:** Open an issue on GitHub
- **Discussions:** Use GitHub Discussions for questions

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
