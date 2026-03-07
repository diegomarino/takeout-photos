# Release Process

This document describes how to create a new release of takeout-photos.

## Prerequisites

- Maintainer access to GitHub repository
- PyPI account with maintainer access
- `python-semantic-release` installed (`pip install python-semantic-release`)

## Automated Release (Recommended)

Releases are automated via GitHub Actions when a tag is pushed.

### Step 1: Ensure main branch is ready

```bash
git checkout main
git pull origin main
```

### Step 2: Run semantic-release

```bash
semantic-release version
```

This will:
- Analyze conventional commits since last release
- Determine next version (major, minor, or patch)
- Update version in `pyproject.toml` and `__init__.py`
- Update `CHANGELOG.md`
- Create a git tag

### Step 3: Push tag to trigger release

```bash
git push origin main --tags
```

This triggers the GitHub Actions release workflow which will:
- Run all tests
- Build the package
- Publish to PyPI
- Create GitHub release with changelog

### Step 4: Verify release

- Check GitHub releases: `https://github.com/diegomarino/takeout-photos/releases`
- Check PyPI: `https://pypi.org/project/takeout-photos/`
- Test installation: `pip install --upgrade takeout-photos`

## Manual Release (Emergency)

If automated release fails:

### Step 1: Update version manually

Edit `pyproject.toml` and `src/takeout_photos/__init__.py`

### Step 2: Update CHANGELOG.md

Add section for new version following Keep a Changelog format.

### Step 3: Commit and tag

```bash
git add pyproject.toml src/takeout_photos/__init__.py CHANGELOG.md
git commit -m "chore: release v1.1.0"
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin main --tags
```

### Step 4: Build and publish

```bash
# Build package
python -m build

# Publish to PyPI
twine upload dist/*
```

### Step 5: Create GitHub release

Go to GitHub releases and create a new release from the tag.

## Version Bumping Rules

Based on [Semantic Versioning](https://semver.org/):

- **Major (X.0.0)**: Breaking changes
  - Changes to CLI interface that break existing scripts
  - Removal of features
  - Changes to library API

- **Minor (1.X.0)**: New features, backwards compatible
  - New CLI flags
  - New library methods
  - Performance improvements

- **Patch (1.0.X)**: Bug fixes, backwards compatible
  - Bug fixes
  - Documentation updates
  - Dependency updates

## Commit Message Guidelines

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - Minor version bump
- `fix:` - Patch version bump
- `feat!:` or `BREAKING CHANGE:` - Major version bump
- `docs:`, `style:`, `refactor:`, `test:`, `chore:` - No version bump

## Pre-release Checklist

Before triggering a release:

- [ ] All tests passing on main
- [ ] CHANGELOG.md is up to date (if manual release)
- [ ] Documentation is current
- [ ] No open P0/blocking issues
- [ ] Version bump is appropriate for changes
- [ ] Dependencies are up to date
- [ ] Security vulnerabilities addressed

## Post-release Checklist

After release is published:

- [ ] Verify package on PyPI
- [ ] Test installation: `pip install --upgrade takeout-photos`
- [ ] Verify CLI works: `takeout-photos --version`
- [ ] Verify GitHub release created
- [ ] Announce on relevant channels (optional)

## Hotfix Process

For critical bugs requiring immediate release:

1. Create hotfix branch from latest tag: `git checkout -b hotfix/v1.0.1 v1.0.0`
2. Make fix and commit: `git commit -m "fix: critical bug description"`
3. Tag hotfix: `git tag -a v1.0.1 -m "Hotfix v1.0.1"`
4. Push: `git push origin hotfix/v1.0.1 --tags`
5. Merge back to main: `git checkout main && git merge hotfix/v1.0.1`
6. Delete hotfix branch: `git branch -d hotfix/v1.0.1`

## Troubleshooting

### semantic-release fails to determine version

Check commit messages follow conventional commits format.

### PyPI upload fails

Verify PyPI token is correct in GitHub Secrets.

### Tests fail on release workflow

Do not proceed with release. Fix tests first.

### Wrong version bumped

If caught before PyPI publish:
1. Delete the tag: `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`
2. Reset version changes: `git reset --hard HEAD~1`
3. Fix and retry

If already on PyPI:
- Cannot remove version from PyPI
- Release next correct version immediately
