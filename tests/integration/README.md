# Integration Tests

This directory contains integration tests that validate the Jeepney pure-Python implementation works correctly with real systemd services.

## What This Tests

**Single comprehensive test** that validates:
- ✅ Package installs **without a C compiler** (proves pure Python works)
- ✅ Service START detection
- ✅ Service STOP detection
- ✅ Service CRASH detection
- ✅ Service RESTART detection
- ✅ State persistence across monitor restarts
- ✅ Prometheus metrics accuracy
- ✅ Graceful shutdown handling
- ✅ All 12 monitoring scenarios

**Container**: Ubuntu 22.04 with systemd (NO build tools installed)

**Duration**: ~60 seconds

## Why Ubuntu and Not Alpine?

**Short answer**: You can't test systemd monitoring without systemd.

Alpine Linux uses OpenRC, not systemd. Testing on Alpine would be pointless because:
- ❌ Alpine doesn't have systemd
- ❌ Can't validate monitoring features
- ❌ Would only test imports (meaningless)

Instead, we use Ubuntu with systemd but **explicitly verify no build tools** are installed. This proves both:
1. Pure Python installation (no gcc required)
2. Actual monitoring functionality

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

✅ Jeepney pure-Python implementation works on production systems
✅ No C compiler needed for installation
✅ All monitoring features work identically to dbus-python
✅ Ready for production deployment
