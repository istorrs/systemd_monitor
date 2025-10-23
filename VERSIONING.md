# Versioning Strategy

## Overview

This project uses **semantic versioning** (SemVer) with a **single source of truth** approach.

## Version Format

```
MAJOR.MINOR.PATCH[-SUFFIX]
```

- **MAJOR**: Incompatible API changes
- **MINOR**: Backwards-compatible functionality additions
- **PATCH**: Backwards-compatible bug fixes
- **SUFFIX**: Optional (e.g., `-dev`, `-rc1`, `-alpha`)

## Single Source of Truth

**The version is defined ONLY in `pyproject.toml`:**

```toml
[project]
name = "systemd_monitor"
version = "0.1.0"
```

## Runtime Version Access

The version is automatically available at runtime via `importlib.metadata`:

```python
# In code
from systemd_monitor import __version__
print(__version__)  # "0.1.0"

# Command line
systemd-monitor --version  # "systemd-monitor version: 0.1.0"
```

## How It Works

1. **Package Metadata**: Version is defined in `pyproject.toml`
2. **Runtime Import**: `systemd_monitor/__init__.py` reads version using `importlib.metadata.version()`
3. **Fallback**: If package is not installed, falls back to `"0.1.0-dev"`
4. **CLI Access**: The `--version` flag displays the version

## Development Setup

For version to work correctly in development, install package in editable mode:

```bash
pip install -e .
```

This makes the package metadata available to `importlib.metadata`.

## Releasing a New Version

### 1. Update Version

Edit `pyproject.toml`:

```toml
[project]
version = "0.2.0"  # Bump version here
```

### 2. Update CHANGELOG.md

Document what changed:

```markdown
## [0.2.0] - 2025-01-15

### Added
- New feature X
- Enhancement Y

### Fixed
- Bug Z
```

### 3. Commit and Tag

```bash
# Commit version bump
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to 0.2.0"

# Create git tag
git tag -a v0.2.0 -m "Release version 0.2.0"

# Push changes and tags
git push origin main
git push origin v0.2.0
```

### 4. Build and Publish (Optional)

```bash
# Build distribution
python -m build

# Publish to PyPI
python -m twine upload dist/*
```

## Version Checking

Verify version is correct:

```bash
# Check installed version
python -c "from systemd_monitor import __version__; print(__version__)"

# Check via CLI
systemd-monitor --version

# Check package metadata
pip show systemd_monitor | grep Version
```

## Automated Testing

The test suite includes version tests:

```python
def test_version_attribute_exists():
    """Test that __version__ attribute exists."""
    assert hasattr(systemd_monitor, "__version__")
    assert isinstance(systemd_monitor.__version__, str)
```

## Why This Approach?

✅ **Single Source of Truth**: Version only in `pyproject.toml`
✅ **PEP 621 Compliant**: Uses modern Python packaging standards
✅ **Simple**: No complex build tools or version file generation
✅ **Reliable**: Works both in development and production
✅ **Testable**: Easy to verify version is correct

## Alternative Approaches Considered

### ❌ setuptools_scm (Git Tag Based)

- **Pros**: Automatic version from git tags
- **Cons**: Requires git, more complex, harder to debug
- **Decision**: Too complex for this project

### ❌ Separate __version__.py File

- **Pros**: Explicit version file
- **Cons**: Duplication, needs to be kept in sync with pyproject.toml
- **Decision**: Violates single source of truth principle

### ❌ Hardcoded Version

- **Pros**: Simple
- **Cons**: Easy to forget to update, no connection to package metadata
- **Decision**: Not maintainable

## References

- [PEP 440 - Version Identification](https://peps.python.org/pep-0440/)
- [PEP 621 - Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Python Packaging User Guide](https://packaging.python.org/)
