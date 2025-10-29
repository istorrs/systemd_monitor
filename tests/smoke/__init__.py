"""
Smoke tests for systemd_monitor.

These are lightweight tests that verify basic functionality without requiring
systemd or D-Bus. They're designed to run in CI environments like GitHub Actions.

Smoke tests check:
- Package installation and imports
- CLI arguments and help text
- Configuration loading
- Basic module structure

For full integration tests with systemd, see tests/integration/
"""
