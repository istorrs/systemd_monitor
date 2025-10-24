# Versioning Strategy

## Overview

This project uses **setuptools_scm** for **automatic git-based versioning**. The version is derived from git tags - no manual version bumping needed!

## Version Format

Versions follow **semantic versioning** (SemVer):

```
MAJOR.MINOR.PATCH[.devN+gSHA][.dDATE]
```

### Examples

| Git State | Version | Meaning |
|-----------|---------|---------|
| On tag `v0.1.0` | `0.1.0` | Official release |
| 3 commits after `v0.1.0` | `0.1.1.dev3+g1234abc` | 3 commits into 0.1.1 development |
| Dirty working tree | `0.1.1.dev3+g1234abc.d20251023` | Uncommitted changes |
| No tags | `0.0.0+unknown` | No version tags exist yet |

**Format breakdown:**
- `0.1.1` - Next release version
- `.dev3` - 3 commits since last tag
- `+g1234abc` - Git commit SHA (first 7 chars)
- `.d20251023` - Dirty tree on 2025-10-23

## How It Works

**Automatic Version Derivation:**
1. setuptools_scm reads git history
2. Finds the most recent tag matching `v*.*.*`
3. Counts commits since that tag
4. Includes git SHA and dirty state
5. Generates `systemd_monitor/_version.py` (auto-generated, in .gitignore)

**No manual version management needed!**

## Runtime Version Access

The version is automatically available at runtime:

```python
# In code
from systemd_monitor import __version__
print(__version__)  # "0.1.1.dev3+g1234abc"

# Command line
systemd-monitor --version  # "systemd-monitor version: 0.1.1.dev3+g1234abc"

# From installed package
pip show systemd_monitor | grep Version
```

## Development Setup

**For version to work correctly in development:**

```bash
# Install setuptools_scm
pip install setuptools_scm

# Install package in editable mode (recommended)
pip install -e .

# Or just import - setuptools_scm works directly from git
python -c "from systemd_monitor import __version__; print(__version__)"
```

## Releasing a New Version

### Simple Release Process

**You only need to create a git tag - everything else is automatic!**

```bash
# 1. Ensure all changes are committed
git status

# 2. Update CHANGELOG.md with release notes
# Document what changed in this release

# 3. Commit changelog
git add CHANGELOG.md
git commit -m "Update changelog for v0.2.0"

# 4. Create annotated tag
git tag -a v0.2.0 -m "Release version 0.2.0

- Feature X added
- Bug Y fixed
- Enhancement Z implemented
"

# 5. Push commits and tags
git push origin main
git push origin v0.2.0

# That's it! Version is now 0.2.0 automatically
```

### Version Bumping

setuptools_scm automatically determines the next version:

- **Patch bump** (0.1.0 → 0.1.1): Default for any commits after a tag
- **Minor bump** (0.1.0 → 0.2.0): Create tag `v0.2.0` explicitly
- **Major bump** (0.1.0 → 1.0.0): Create tag `v1.0.0` explicitly

**The version is in the tag name - that's the single source of truth!**

### Build and Publish (Optional)

```bash
# Build distribution packages
python -m build

# Verify version in built package
tar -tzf dist/systemd_monitor-0.2.0.tar.gz | grep _version.py

# Publish to PyPI
python -m twine upload dist/*
```

## Version Checking

Verify version is correct:

```bash
# Check current version (from git)
python -c "from systemd_monitor import __version__; print(__version__)"

# Check all tags
git tag -l

# Check commits since last tag
git log $(git describe --tags --abbrev=0)..HEAD --oneline

# Check what next version will be
python -m setuptools_scm
```

## Benefits

✅ **Automatic** - No manual version bumping
✅ **Accurate** - Version includes exact commit SHA
✅ **Traceable** - Always know what code is running
✅ **Simple** - Just create git tags
✅ **PEP 440 Compliant** - Standard Python versioning
✅ **Development Versions** - Clear distinction between releases and dev builds
✅ **No Forgotten Bumps** - Impossible to forget to update version

## Configuration

Version behavior is configured in `pyproject.toml`:

```toml
[tool.setuptools_scm]
write_to = "systemd_monitor/_version.py"
version_scheme = "post-release"
local_scheme = "node-and-date"
```

**Options:**
- `write_to` - Where to write version file
- `version_scheme` - How to calculate next version
- `local_scheme` - Format for dev versions (includes git SHA and date)

## Troubleshooting

### "Version shows 0.0.0+unknown"

**Cause**: No git tags exist

**Solution**: Create initial tag
```bash
git tag -a v0.1.0 -m "Initial release"
```

### "Version not updating"

**Cause**: Using old installed version

**Solution**: Reinstall in editable mode
```bash
pip install -e .
```

### "Can't import _version.py"

**Cause**: Package not built/installed

**Solution**: setuptools_scm will use git directly as fallback

## Why setuptools_scm?

### Advantages over manual versioning:

| Manual Version | setuptools_scm |
|----------------|----------------|
| ❌ Easy to forget to bump | ✅ Automatic from git tags |
| ❌ No way to know exact commit | ✅ Includes commit SHA |
| ❌ Dev builds look like releases | ✅ Clear `.dev` marker |
| ❌ Requires discipline | ✅ Foolproof |
| ❌ Can be out of sync | ✅ Always accurate |

### Alternatives Considered

**❌ Manual version in `pyproject.toml`**
- Pro: Simple
- Con: Easy to forget, no commit info
- Decision: Too error-prone

**❌ Separate `__version__.py` file**
- Pro: Explicit
- Con: Still manual, duplication
- Decision: Same problems as manual

**❌ versioneer**
- Pro: Similar to setuptools_scm
- Con: More complex, requires setup step
- Decision: setuptools_scm is simpler

## References

- [setuptools_scm Documentation](https://setuptools-scm.readthedocs.io/)
- [PEP 440 - Version Identification](https://peps.python.org/pep-0440/)
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Python Packaging User Guide](https://packaging.python.org/)

## Quick Reference

```bash
# Check current version
python -c "from systemd_monitor import __version__; print(__version__)"

# Create release
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0

# List all versions
git tag -l

# Show version without installing
python -m setuptools_scm

# Build with correct version
python -m build
```

**Remember: The git tag IS the version. Everything else is automatic!**
