# Integration Tests

This directory contains integration tests that validate the Jeepney pure-Python implementation works correctly with real systemd services.

## What This Tests

**Single comprehensive test** that validates the Jeepney implementation:
- ✅ Service START detection
- ✅ Service STOP detection
- ✅ Service CRASH detection
- ✅ Service RESTART detection
- ✅ State persistence across monitor restarts
- ✅ Prometheus metrics accuracy
- ✅ Graceful shutdown handling
- ✅ All 12 monitoring scenarios

**Container**: Ubuntu 22.04 with systemd

**Duration**: ~60 seconds

## Why Ubuntu?

We need a systemd-based distribution to test systemd monitoring.

Ubuntu 22.04 provides:
- ✅ systemd for actual service monitoring
- ✅ Common production environment
- ✅ Well-supported in Docker

## Running Tests

### Locally

```bash
cd tests/integration
./run_all_tests.sh
```

### In GitHub Actions

Tests run automatically on every push/PR to the Jeepney branch.

## Test Services

The test creates 4 systemd services:

1. **stable.service** - Long-running service for start/stop tests
2. **flaky.service** - Crashes after 2 seconds (crash detection)
3. **restart.service** - Auto-restarts on failure (restart detection)
4. **oneshot.service** - Runs once and exits (oneshot type)

## Expected Output

```
============================================================
Systemd Integration Test
============================================================

Test 1: Verify systemd environment
  ✓ systemd is running

Test 2: Install test services
  ✓ All services installed

[... 12 tests total ...]

============================================================
Test Summary
============================================================
Passed: 12
Failed: 0

✓ ALL TESTS PASSED!
```

## Documentation

- `INTEGRATION_TEST_GUIDE.md` - Comprehensive guide
- `test_systemd_integration.py` - Test implementation (500+ lines)

## What This Proves

✅ Jeepney implementation works correctly with systemd
✅ All monitoring features work (feature parity with dbus-python)
✅ State persistence works across restarts
✅ Prometheus metrics are accurate
✅ Ready for production deployment
