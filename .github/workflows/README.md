# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the takeout-photos project.

## Available Workflows

### `test.yml` - Automated Testing
- **Trigger:** Push to any branch, Pull Requests
- **Purpose:** Run test suite across multiple Python versions
- **Python Versions:** 3.8, 3.9, 3.10, 3.11, 3.12
- **Coverage:** Generates coverage reports

### `lint.yml` - Code Quality Checks
- **Trigger:** Push to any branch, Pull Requests
- **Purpose:** Enforce code style and quality standards
- **Tools:**
  - Black (code formatting)
  - Ruff (linting)
  - mypy (type checking)

### `release.yml` - Automated Releases
- **Trigger:** Manual workflow dispatch
- **Purpose:** Create releases and publish to PyPI
- **Features:**
  - Semantic versioning
  - Automated changelog generation
  - GitHub release creation
  - PyPI package publishing (when configured)

## Workflow Status

Check the [Actions tab](https://github.com/diegomarino/takeout-photos/actions) to see workflow runs and status.
