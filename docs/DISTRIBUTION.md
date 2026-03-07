# Package Distribution Guide

This guide covers building, testing, and publishing the `takeout-photos` package to PyPI.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Building the Package](#building-the-package)
- [Testing Locally](#testing-locally)
- [Publishing to TestPyPI](#publishing-to-testpypi)
- [Publishing to PyPI](#publishing-to-pypi)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

Install the build and upload tools:

```bash
pip install --upgrade build twine
```

### PyPI Accounts

You'll need accounts on both:

1. **TestPyPI** (for testing): https://test.pypi.org/account/register/
2. **PyPI** (for production): https://pypi.org/account/register/

### API Tokens

Create API tokens for secure authentication:

**TestPyPI:**
1. Go to https://test.pypi.org/manage/account/token/
2. Create a new token with scope: "Entire account"
3. Save the token securely (you won't see it again)

**PyPI:**
1. Go to https://pypi.org/manage/account/token/
2. Create a new token with scope: "Entire account"
3. Save the token securely

**Configure tokens:**

Create or edit `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR-PRODUCTION-TOKEN-HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR-TEST-TOKEN-HERE
```

Set proper permissions:

```bash
chmod 600 ~/.pypirc
```

---

## Building the Package

### 1. Prepare for Build

Ensure your working directory is clean:

```bash
# Check for uncommitted changes
git status

# Ensure all tests pass
source .venv/bin/activate
pytest tests/ -v

# Run quality checks
black --check --line-length=100 src/ tests/
ruff check src/ tests/
mypy src/ --ignore-missing-imports
```

### 2. Clean Previous Builds

Remove old build artifacts:

```bash
rm -rf dist/ build/ src/*.egg-info
```

### 3. Build Distribution Archives

```bash
source .venv/bin/activate
python -m build
```

This creates two files in `dist/`:
- `takeout_photos-VERSION-py3-none-any.whl` - Wheel (preferred format)
- `takeout_photos-VERSION.tar.gz` - Source distribution

### 4. Verify Build

Check the package with twine:

```bash
twine check dist/*
```

Expected output:
```
Checking dist/takeout_photos-1.0.0-py3-none-any.whl: PASSED
Checking dist/takeout_photos-1.0.0.tar.gz: PASSED
```

Inspect wheel contents:

```bash
unzip -l dist/takeout_photos-*.whl
```

Verify:
- ✅ Contains `takeout_photos/` package
- ✅ No `tests/` directory
- ✅ No `.git/` or other VCS files
- ✅ Includes `LICENSE` in metadata

---

## Testing Locally

### 1. Create Test Environment

Use a clean virtual environment to test installation:

```bash
# Create temporary test environment
python3 -m venv /tmp/test_takeout_env
source /tmp/test_takeout_env/bin/activate
```

### 2. Install from Wheel

```bash
pip install /path/to/takeout-photos/dist/takeout_photos-*.whl
```

### 3. Verify Installation

**Test CLI:**

```bash
# Help should work
takeout-photos --help

# Doctor command should work
takeout-photos --doctor
```

**Test library imports:**

```bash
python -c "
from takeout_photos import Config, Pipeline
from takeout_photos.core.database import PipelineDB
print('✅ All imports successful')
"
```

**Test fast extras:**

```bash
# Install with fast extras
pip install "/path/to/takeout-photos/dist/takeout_photos-*.whl[fast]"

# Verify xxhash is available
python -c "import xxhash; print(f'✅ xxhash {xxhash.VERSION} installed')"
```

### 4. Cleanup

```bash
deactivate
rm -rf /tmp/test_takeout_env
```

---

## Publishing to TestPyPI

Always test on TestPyPI before publishing to production PyPI.

### 1. Upload to TestPyPI

```bash
twine upload --repository testpypi dist/*
```

You'll see output like:
```
Uploading distributions to https://test.pypi.org/legacy/
Uploading takeout_photos-1.0.0-py3-none-any.whl
Uploading takeout_photos-1.0.0.tar.gz
```

### 2. Verify Upload

Visit your project page:
```
https://test.pypi.org/project/takeout-photos/
```

### 3. Test Installation from TestPyPI

Create a fresh environment and install:

```bash
python3 -m venv /tmp/test_pypi_install
source /tmp/test_pypi_install/bin/activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ takeout-photos

# Test it works
takeout-photos --help
```

**Note:** Dependencies won't be available from TestPyPI. To install with dependencies:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    takeout-photos[fast]
```

### 4. Cleanup

```bash
deactivate
rm -rf /tmp/test_pypi_install
```

---

## Publishing to PyPI

⚠️ **Warning:** Once published to PyPI, you cannot delete or replace a version. Double-check everything!

### Pre-Release Checklist

- [ ] All tests pass
- [ ] Quality checks pass (black, ruff, mypy)
- [ ] Version number is correct in `pyproject.toml`
- [ ] CHANGELOG.md is updated
- [ ] README.md is up to date
- [ ] Tested successfully on TestPyPI
- [ ] Git tag created: `git tag v1.0.0 && git push origin v1.0.0`

### 1. Upload to PyPI

```bash
twine upload dist/*
```

### 2. Verify Upload

Visit your project page:
```
https://pypi.org/project/takeout-photos/
```

### 3. Test Installation

```bash
# Create fresh environment
python3 -m venv /tmp/test_production
source /tmp/test_production/bin/activate

# Install from PyPI
pip install takeout-photos

# Test it works
takeout-photos --help

# Test with extras
pip install takeout-photos[fast]
python -c "import xxhash; print('✅ Fast extras work')"

# Cleanup
deactivate
rm -rf /tmp/test_production
```

---

## Troubleshooting

### Build Errors

**Problem:** `error: invalid command 'bdist_wheel'`

**Solution:** Install build tools:
```bash
pip install --upgrade build wheel setuptools
```

---

**Problem:** Package is empty (no source files in wheel)

**Solution:** Check `[tool.hatch.build.targets.wheel]` in `pyproject.toml`:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/takeout_photos"]
```

---

**Problem:** Tests included in wheel

**Solution:** Verify `pyproject.toml` excludes tests and that your package structure follows:
```
src/takeout_photos/  # Package code
tests/               # Tests (not in src/)
```

---

### Upload Errors

**Problem:** `403 Forbidden` during upload

**Solution:**
1. Check your API token is valid
2. Verify `~/.pypirc` is configured correctly
3. Ensure token has correct scope (entire account or this project)

---

**Problem:** `400 Bad Request: File already exists`

**Solution:**
- PyPI doesn't allow replacing versions
- Increment version in `pyproject.toml`
- Rebuild: `rm -rf dist/ && python -m build`

---

**Problem:** `twine: command not found`

**Solution:**
```bash
pip install --upgrade twine
```

---

### Installation Errors

**Problem:** `ModuleNotFoundError` after installation

**Solution:**
1. Verify package structure: `unzip -l dist/*.whl`
2. Check `[project.scripts]` in `pyproject.toml`
3. Ensure `__init__.py` exports are correct

---

**Problem:** CLI not found after pip install

**Solution:** Check `[project.scripts]` in `pyproject.toml`:
```toml
[project.scripts]
takeout-photos = "takeout_photos.cli.main:main"
```

---

**Problem:** Extras not installing dependencies

**Solution:** Check `[project.optional-dependencies]` syntax:
```toml
[project.optional-dependencies]
fast = [
    "xxhash>=3.0.0",
    "tqdm>=4.65.0",
]
```

---

## Version Management

### Semantic Versioning

Follow semantic versioning (semver):

- **Major (1.0.0 → 2.0.0):** Breaking changes
- **Minor (1.0.0 → 1.1.0):** New features, backwards compatible
- **Patch (1.0.0 → 1.0.1):** Bug fixes

### Updating Version

1. Edit `pyproject.toml`:
   ```toml
   version = "1.0.1"
   ```

2. Update `src/takeout_photos/__init__.py`:
   ```python
   __version__ = "1.0.1"
   ```

3. Update CHANGELOG.md

4. Commit changes:
   ```bash
   git add pyproject.toml src/takeout_photos/__init__.py CHANGELOG.md
   git commit -m "build: bump version to 1.0.1"
   git tag v1.0.1
   git push origin master --tags
   ```

5. Build and publish

---

## Automation

### GitHub Actions (Future)

Consider automating releases with GitHub Actions:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install build twine
      - name: Build package
        run: python -m build
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: twine upload dist/*
```

---

## Resources

- **Python Packaging User Guide:** https://packaging.python.org/
- **PyPI:** https://pypi.org/
- **TestPyPI:** https://test.pypi.org/
- **Twine Documentation:** https://twine.readthedocs.io/
- **Build Documentation:** https://build.pypa.io/

---

## Quick Reference

### Complete Release Process

```bash
# 1. Prepare
git checkout master
git pull
source .venv/bin/activate
pytest tests/ -v

# 2. Update version
# Edit pyproject.toml and __init__.py

# 3. Build
rm -rf dist/
python -m build
twine check dist/*

# 4. Test locally
python3 -m venv /tmp/test_env
source /tmp/test_env/bin/activate
pip install dist/takeout_photos-*.whl
takeout-photos --help
deactivate && rm -rf /tmp/test_env

# 5. Upload to TestPyPI
twine upload --repository testpypi dist/*

# 6. Test TestPyPI installation
python3 -m venv /tmp/test_pypi
source /tmp/test_pypi/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ takeout-photos
takeout-photos --help
deactivate && rm -rf /tmp/test_pypi

# 7. Upload to PyPI
twine upload dist/*

# 8. Tag release
git tag v1.0.0
git push origin master --tags
```
