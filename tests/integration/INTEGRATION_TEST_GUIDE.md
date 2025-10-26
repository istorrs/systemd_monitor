# Integration Test Guide

This guide explains how to run, understand, and extend the integration tests for systemd_monitor.

## Overview

The integration test suite validates that systemd_monitor works correctly in real-world environments. It consists of two main test types:

1. **Alpine Installation Test** - Proves the package works on Alpine Linux without build tools
2. **Systemd Integration Test** - Validates actual systemd service monitoring functionality

## Why Integration Tests?

Unit tests with mocks are great, but they can't verify:
- Real D-Bus communication
- Actual systemd service state detection
- Installation on minimal systems
- End-to-end monitoring workflows

Integration tests fill this gap by running the monitor against real services in containers.

## Test Architecture

### 1. Alpine Installation Test

**Purpose**: Prove Jeepney-based implementation works on Alpine Linux

**What it validates**:
- ✅ Package installs without C compiler (no gcc/g++)
- ✅ All Python modules import successfully
- ✅ dbus_shim compatibility layer loads
- ✅ Configuration module works
- ✅ CLI tools are available
- ✅ No dbus-python or PyGObject dependencies

**Container**: `python:3.11-alpine` (minimal, no build tools)

**Duration**: ~30 seconds

**Why Alpine?**
- Alpine uses musl libc (not glibc) - catches compatibility issues
- Alpine doesn't include build tools by default
- Common base for minimal Docker images
- Proves pure Python approach works

### 2. Systemd Integration Test

**Purpose**: Validate actual systemd monitoring in production-like environment

**What it validates**:
- ✅ Service START detection
- ✅ Service STOP detection
- ✅ Service CRASH detection (failed state)
- ✅ Service RESTART detection
- ✅ State persistence across monitor restarts
- ✅ Prometheus metrics accuracy
- ✅ Graceful shutdown handling
- ✅ Log file creation and formatting

**Container**: `ubuntu:22.04` with systemd enabled

**Duration**: ~60 seconds

**Test Services**:
1. `stable.service` - Long-running service for start/stop tests
2. `flaky.service` - Crashes after 2 seconds (crash detection)
3. `restart.service` - Auto-restarts on failure (restart detection)
4. `oneshot.service` - Runs once and exits (oneshot type)

## Running Tests

### Prerequisites

- Docker installed and running
- Internet connection (to pull base images)
- ~500MB disk space for images

### Run All Tests (Recommended)

```bash
cd tests/integration
./run_all_tests.sh
```

This runs both Alpine and systemd tests sequentially.

### Run Individual Tests

#### Alpine Test Only
```bash
cd tests/integration
docker build -f Dockerfile.alpine -t systemd-monitor-alpine ../../
docker run --rm systemd-monitor-alpine
```

#### Systemd Test Only
```bash
cd tests/integration
docker build -f Dockerfile.systemd -t systemd-monitor-systemd ../../
docker run --rm --privileged \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    systemd-monitor-systemd
```

**Note**: Systemd test requires `--privileged` to run systemd in container.

## Understanding Test Output

### Alpine Test Output

```
==========================================
Alpine Linux Integration Test
==========================================

✓ Checking Alpine Linux version...
3.18.4

✓ Verifying no C compiler available...
  No C compiler found (expected) ✓

✓ Installing systemd_monitor package...
Successfully installed jeepney-0.8.0 systemd-monitor-0.1.0

✓ Verifying dependencies...
  jeepney installed ✓
  dbus-python NOT installed ✓

✓ Testing Python imports...
  systemd_monitor version: 0.1.0+g6ab0919
  dbus_shim module loaded ✓
  Config module loaded ✓
  PrometheusMetrics module loaded ✓

✓ All Alpine Linux tests PASSED!
```

### Systemd Test Output

```
============================================================
Systemd Integration Test
============================================================

Test 1: Verify systemd environment
  $ systemctl --version | head -1
    systemd 249 (249.11-ubuntu3)
  ✓ systemd is running

Test 2: Install test services
  ✓ Installed stable.service
  ✓ Installed flaky.service
  ✓ Installed restart.service
  ✓ Installed oneshot.service
  ✓ Reloaded systemd daemon

Test 3: Start systemd_monitor
  ✓ Monitor started (PID: 123)

Test 4: Verify initial state detection
  Waiting for: initial states
    ✓ Found: Initial state for
  ✓ Initial states logged

Test 5: Detect service START
  $ systemctl start stable.service
  Waiting for: stable.service start
    ✓ Found: stable.service
  Waiting for: START event
    ✓ Found: START
  ✓ Service START detected

Test 6: Detect service STOP
  $ systemctl stop stable.service
  Waiting for: STOP event
    ✓ Found: STOP
  ✓ Service STOP detected

Test 7: Detect service CRASH
  $ systemctl start flaky.service
  Waiting for: CRASH event
    ✓ Found: CRASH
  ✓ Service CRASH detected

...

============================================================
Test Summary
============================================================
Passed: 12
Failed: 0
Total:  12

✓ ALL TESTS PASSED!
```

## CI/CD Integration

Integration tests run automatically in GitHub Actions on:
- Push to `main`, `develop`, or `claude/**` branches
- Pull requests to `main` or `develop`
- Manual workflow dispatch

### GitHub Actions Workflow

The workflow (`.github/workflows/integration-tests.yml`) runs both tests in parallel:

```yaml
jobs:
  alpine-test:
    name: Alpine Installation Test
    runs-on: ubuntu-latest
    # Builds and runs Alpine test

  systemd-test:
    name: Systemd Integration Test
    runs-on: ubuntu-latest
    # Builds and runs systemd test with --privileged

  integration-summary:
    name: Integration Test Summary
    needs: [alpine-test, systemd-test]
    # Summarizes results
```

### Viewing Results

1. Go to GitHub repository → Actions tab
2. Click on latest workflow run
3. View "Alpine Installation Test" and "Systemd Integration Test" jobs
4. Check logs for detailed output
5. Download artifacts (logs) if tests fail

## Troubleshooting

### Alpine Test Failures

**Problem**: "gcc found! This test requires an environment without build tools"

**Cause**: Base image includes build tools

**Fix**: Use `python:3.11-alpine` (not `python:3.11`)

---

**Problem**: "ImportError: No module named 'jeepney'"

**Cause**: Jeepney not installed

**Fix**: Check `RUN pip install jeepney` in Dockerfile.alpine

---

### Systemd Test Failures

**Problem**: "systemd not available"

**Cause**: systemd not running in container

**Fix**: Ensure `--privileged` flag and systemd installed

---

**Problem**: "Monitor process not running"

**Cause**: Monitor crashed on startup

**Fix**: Check `/tmp/monitor_stdout.log` for errors:
```bash
# In test script, add:
cat /tmp/monitor_stdout.log
```

---

**Problem**: "Timeout waiting for START event"

**Cause**: Monitor not receiving D-Bus signals

**Fix**:
1. Verify D-Bus is running: `systemctl status dbus`
2. Check monitor logs for "Subscribed to PropertiesChanged"
3. Increase timeout in test (currently 5 seconds)

---

**Problem**: "Prometheus metrics not available"

**Cause**: prometheus-client not installed or port conflict

**Fix**:
1. Check if prometheus-client installed: `pip list | grep prometheus`
2. Verify port 9100 is free
3. Check monitor logs for "Prometheus metrics enabled"

---

## Extending Tests

### Adding New Test Services

1. Create service file in `tests/integration/test_services/`:

```ini
# tests/integration/test_services/mytest.service
[Unit]
Description=My Test Service

[Service]
Type=simple
ExecStart=/bin/sleep 30
Restart=no
```

2. Add to test script:

```python
test_services = [
    "stable.service",
    "flaky.service",
    "restart.service",
    "oneshot.service",
    "mytest.service"  # Add your service
]
```

### Adding New Test Cases

Edit `test_systemd_integration.py`:

```python
# Test 13: My new test
print(f"\n{Colors.BLUE}Test 13: My new test{Colors.RESET}")
run_cmd("systemctl start mytest.service")

if wait_for_log_entry(log_file, "expected pattern", timeout=5):
    print(f"  {Colors.GREEN}✓ Test passed{Colors.RESET}")
    tests_passed += 1
else:
    print(f"  {Colors.RED}✗ Test failed{Colors.RESET}")
    tests_failed += 1
```

### Testing Different Python Versions

Modify `Dockerfile.alpine`:

```dockerfile
# Test on Python 3.8
FROM python:3.8-alpine
# ... rest of dockerfile

# Test on Python 3.12
FROM python:3.12-alpine
# ... rest of dockerfile
```

### Testing Performance

Add timing measurements:

```python
import time

start = time.time()
run_cmd("systemctl start stable.service")
wait_for_log_entry(log_file, "START", timeout=5)
elapsed = time.time() - start

print(f"  Detection latency: {elapsed*1000:.1f}ms")

if elapsed < 0.1:  # Less than 100ms
    print(f"  {Colors.GREEN}✓ Fast detection{Colors.RESET}")
else:
    print(f"  {Colors.YELLOW}⚠ Slow detection{Colors.RESET}")
```

## Best Practices

1. **Keep tests independent** - Each test should clean up after itself
2. **Use timeouts** - Prevent hanging tests with reasonable timeouts
3. **Log everything** - Include debug output for troubleshooting
4. **Test failure modes** - Don't just test happy paths
5. **Version control test data** - Keep test services under version control
6. **Document expectations** - Explain what each test validates
7. **Fast feedback** - Keep tests under 2 minutes total

## Performance Benchmarks

Expected test durations:

| Test | Duration | Notes |
|------|----------|-------|
| Alpine build | ~15s | First build slower (downloads base image) |
| Alpine run | ~10s | Package install + imports |
| Systemd build | ~30s | Installs systemd + Python |
| Systemd run | ~45s | 12 test cases + cleanup |
| **Total** | ~100s | Both tests, first run |
| **Cached** | ~60s | With Docker layer caching |

## Security Notes

**Why `--privileged` for systemd test?**

Systemd requires access to cgroups and other kernel features. The `--privileged` flag is needed to:
- Access `/sys/fs/cgroup` for process management
- Create systemd control groups
- Manage service processes

**Is this safe in CI/CD?**

Yes, for integration tests:
- Container is ephemeral (destroyed after test)
- No network access to host
- Isolated from other jobs
- No sensitive data in container

**Local development:**

When running locally, the privileged container:
- Can see host processes (but not modify them)
- Shares cgroup hierarchy (read-only mount)
- Isolated by Docker namespaces

## FAQ

**Q: Why not use docker-compose?**

A: These tests are simple enough that plain Docker is sufficient. Adding compose would add complexity without benefits.

---

**Q: Can I run tests on macOS/Windows?**

A: Yes, as long as Docker Desktop is installed. However, systemd tests may be slower due to VM overhead.

---

**Q: Why Ubuntu for systemd test instead of Debian/Fedora?**

A: Ubuntu 22.04 provides a good balance of:
- Modern systemd (v249)
- Well-tested Docker images
- Good documentation
- Similar to common production environments

---

**Q: How do I debug a failing test?**

1. Add `set -x` to bash scripts for verbose output
2. Add `print()` statements to Python tests
3. Check `/tmp/*.log` files in container
4. Run container interactively: `docker run -it --rm systemd-monitor-systemd /bin/bash`

---

**Q: Can tests run without internet?**

No, Docker needs to pull base images. After first run, images are cached locally.

---

**Q: How much does this slow down CI/CD?**

About 2 minutes per run. This is acceptable for the confidence gained.

---

## Future Enhancements

Potential improvements:

1. **Multi-platform testing** - Test on ARM64 architectures
2. **Stress testing** - Start/stop 100 services rapidly
3. **Long-running stability** - Run monitor for 24 hours
4. **Memory leak detection** - Monitor RSS over time
5. **Performance regression** - Compare signal detection latency
6. **Network failure simulation** - Test D-Bus connection recovery
7. **Version matrix** - Test against systemd v230, v240, v250
8. **Real services** - Test with nginx, redis, postgresql

## Contributing

When adding integration tests:

1. Update this guide with new test descriptions
2. Add test to `run_all_tests.sh` if new test type
3. Update GitHub Actions workflow
4. Document expected output
5. Add troubleshooting section if complex

## Related Documentation

- [Main README](../../README.md) - Project overview
- [Unit Tests](../README.md) - Unit test documentation
- [CI/CD Workflow](../../.github/workflows/ci.yml) - Main CI pipeline
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
