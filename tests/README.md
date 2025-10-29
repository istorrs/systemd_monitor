# Test Suite Organization

The systemd_monitor test suite is organized into three categories:

## Directory Structure

```
tests/
├── unit/           # Unit tests (run in CI on every PR)
├── smoke/          # Smoke tests (run in CI on every PR)
└── integration/    # Integration tests (manual/local only)
```

## Test Categories

### 1. Unit Tests (`tests/unit/`)

**Purpose:** Test individual components in isolation with mocked dependencies

**Characteristics:**
- Mock D-Bus connections and systemd
- Fast execution (<3 seconds)
- High code coverage
- No external dependencies
- Run on every PR/commit

**Run:**
```bash
pytest tests/unit/ -v
```

**Files:**
- `test_config.py` - Configuration loading and validation
- `test_dbus_shim.py` - Jeepney D-Bus shim layer
- `test_prometheus_metrics.py` - Prometheus metrics
- `test_systemd_monitor.py` - Main monitoring logic

**Coverage:** 133 tests, 91% code coverage

### 2. Smoke Tests (`tests/smoke/`)

**Purpose:** Verify basic package functionality without D-Bus

**Characteristics:**
- No D-Bus or systemd required
- Test package structure and imports
- Verify CLI entry points
- Check configuration modules
- Run on every PR/commit

**Run:**
```bash
pytest tests/smoke/ -v
```

**Files:**
- `test_installation.py` - Package imports and structure
- `test_cli.py` - CLI module and entry points
- `test_basic.py` - Configuration and basic functionality

**Coverage:** 25 tests

### 3. Integration Tests (`tests/integration/`)

**Purpose:** Test actual systemd service monitoring with real D-Bus

**Characteristics:**
- Requires systemd running in Docker
- Tests real service start/stop/crash detection
- Validates Prometheus metrics accuracy
- Tests state persistence
- Manual/local execution only

**Run:**
```bash
cd tests/integration
./run_all_tests.sh
```

**Why Manual?**
Standard GitHub Actions runners don't support systemd in Docker containers reliably. These tests require `--privileged` mode and full systemd initialization.

**Documentation:**
- See `tests/integration/README.md` for detailed guide
- See `tests/integration/INTEGRATION_TEST_GUIDE.md` for comprehensive documentation

## Running All Tests

### Locally
```bash
# Unit + Smoke (fast, no D-Bus required)
pytest tests/unit/ tests/smoke/ -v

# All tests including integration (requires Docker)
pytest tests/ -v
cd tests/integration && ./run_all_tests.sh
```

### CI/CD
GitHub Actions automatically runs:
- ✅ Unit tests (tests/unit/)
- ✅ Smoke tests (tests/smoke/)
- ⏸️ Integration tests (manual trigger only)

## Test Development Guidelines

### When to Write Unit Tests
- Testing individual functions
- Testing error handling
- Testing edge cases
- High coverage requirements

### When to Write Smoke Tests
- Verifying package structure
- Testing imports without D-Bus
- Validating CLI configuration
- Quick sanity checks

### When to Write Integration Tests
- Testing actual systemd interaction
- Validating end-to-end workflows
- Verifying real service monitoring
- Performance testing

## CI Configuration

**Workflow:** `.github/workflows/ci.yml`
- Runs unit + smoke tests on Python 3.8, 3.9, 3.10, 3.11
- Generates coverage reports
- Publishes test results

**Workflow:** `.github/workflows/integration-tests.yml`
- Manual trigger only (`workflow_dispatch`)
- Runs full systemd tests in Docker
- For local development validation

## Quick Reference

| Test Type    | Count | Run Time | D-Bus Required | systemd Required | CI Runs |
|-------------|-------|----------|----------------|------------------|---------|
| Unit        | 133   | ~2.5s    | No (mocked)    | No (mocked)      | ✅ Yes  |
| Smoke       | 25    | ~0.5s    | No             | No               | ✅ Yes  |
| Integration | 12    | ~60s     | Yes            | Yes              | ⏸️ Manual |
| **Total**   | **170** | **~63s** | -            | -                | -       |
