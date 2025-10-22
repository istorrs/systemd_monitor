# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive pre-commit hook documentation in `PRE_COMMIT_HOOK.md`
- Detailed PR #2 analysis document in `PR2_ANALYSIS.md`
- This CHANGELOG to track all notable changes

## [2.0.0] - 2025-07-07

### Major Changes - Architecture Rewrite

This release represents a complete architectural overhaul of the systemd monitoring system.

### Changed - Breaking
- **ARCHITECTURE**: Converted from polling-based to event-driven D-Bus callback system
  - Removed periodic polling logic
  - Now uses D-Bus `PropertiesChanged` signals for real-time state change detection
  - More efficient and responsive monitoring
  - Reduced CPU usage by eliminating continuous polling

- **CODE ORGANIZATION**: Separated configuration into dedicated module
  - Created `systemd_monitor/config.py` for configuration management
  - Configuration supports JSON files and command-line arguments
  - Better separation of concerns

### Added
- **TESTING**: Comprehensive test suite with 53 unit tests
  - 28 tests for `config.py` module (100% passing)
  - 25 tests for `systemd_monitor.py` module (skip gracefully without dbus)
  - All tests properly mock D-Bus interactions
  - Test coverage for state management, service monitoring, signal handling

- **CODE QUALITY**: Pylint compliance enforcement
  - All code achieves 10/10 pylint score
  - Added `.pylintrc` configuration file
  - Configured to ignore logging-related false positives
  - Added `pylint>=2.0` to `requirements-dev.txt`

- **PRE-COMMIT HOOKS**: Automated quality gates
  - Pre-commit hook runs pylint on all staged Python files
  - Pre-commit hook executes full unit test suite
  - Prevents commits with failing tests or pylint violations
  - Color-coded output for clear feedback
  - Detailed error messages with fix instructions

- **PROJECT INFRASTRUCTURE**:
  - Modern `pyproject.toml` for project configuration
  - `Makefile` for common development tasks
  - `.pre-commit-config.yaml` for pre-commit framework
  - `config.json.example` template file
  - `requirements-windows.txt` for Windows compatibility
  - Proper package entry points in setup

- **DOCUMENTATION**:
  - Significantly expanded README.md
  - Added usage examples and configuration guide
  - Documented all command-line options
  - Installation instructions for various scenarios

### Fixed
- **REPOSITORY HYGIENE**: Removed venv/ from version control
  - Added `venv/` to `.gitignore`
  - Removed accidentally committed virtual environment files
  - Cleaner repository structure

### Improved
- **CODE STYLE**: Better formatting and docstrings
  - Improved inline documentation
  - More descriptive function and variable names
  - Consistent code style throughout

- **ERROR HANDLING**: More robust error management
  - Better exception handling in state persistence
  - Graceful degradation when D-Bus unavailable
  - Improved logging for debugging

- **PERFORMANCE**: More efficient resource usage
  - Event-driven architecture uses less CPU
  - Reduced memory footprint
  - Faster response to service state changes

## [1.0.0] - 2025-06-25

### Added
- Initial release with basic systemd service monitoring
- Polling-based state checking
- Simple logging to file
- Basic service state tracking

---

## Migration Guide

### Upgrading from 1.x to 2.x

#### Breaking Changes

1. **Architecture Change**: The monitoring system no longer uses polling. If you have custom code that interacts with polling intervals, it will need to be updated.

2. **Configuration Module**: Configuration handling has been refactored into a separate module. Direct imports of configuration constants may need updating.

3. **Requirements**: New dependencies added for testing and development. Run:
   ```bash
   pip install -e ".[dev]"
   ```

#### What Stays the Same

- Service monitoring functionality remains the same from a user perspective
- Log file format is unchanged
- Command-line interface is backward compatible
- Monitored services list is identical

#### Recommended Migration Steps

1. **Update Installation**:
   ```bash
   git pull origin main
   pip install -e ".[dev]"
   ```

2. **Install Pre-commit Hooks** (for contributors):
   ```bash
   pre-commit install
   ```

3. **Verify Operation**:
   ```bash
   systemd-monitor --debug
   ```

4. **Review Configuration**: If using custom config files, verify they still work:
   ```bash
   systemd-monitor --config your-config.json
   ```

#### Benefits of Upgrading

- **Better Performance**: Event-driven architecture is more efficient
- **Better Reliability**: Tests ensure code quality
- **Better Maintainability**: Pylint compliance and pre-commit hooks
- **Better Documentation**: Comprehensive docs and examples

---

## Development Practices

### Code Quality Standards

All code in this project must:
- Achieve 10/10 pylint score
- Pass all unit tests
- Follow the pre-commit hook requirements

### Contributing

Before submitting changes:

1. Run tests: `pytest tests/`
2. Check pylint: `pylint systemd_monitor/ tests/`
3. Let pre-commit hook validate your changes (automatic on commit)

The pre-commit hook will automatically enforce these standards.

---

[Unreleased]: https://github.com/istorrs/systemd_monitor/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/istorrs/systemd_monitor/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/istorrs/systemd_monitor/releases/tag/v1.0.0
