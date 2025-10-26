# Integration Tests

This directory contains integration tests that run in Docker containers to verify real-world functionality.

## Test Types

### 1. Alpine Installation Test (`test_alpine_install.sh`)
**Purpose**: Verify the package installs and runs on Alpine Linux without a C compiler.

**What it tests**:
- Pure Python installation (no compilation required)
- Import and module loading
- Basic functionality without systemd

**Container**: `python:3.11-alpine`

### 2. Systemd Integration Test (`test_systemd_integration.py`)
**Purpose**: Verify actual systemd service monitoring in a real systemd environment.

**What it tests**:
- Service start detection
- Service stop detection
- Service crash detection
- Service restart detection
- Prometheus metrics accuracy
- State persistence across monitor restarts

**Container**: `ubuntu:22.04` with systemd enabled

## Running Tests Locally

### Prerequisites
- Docker installed and running
- Python 3.8+ (for test orchestration)

### Run All Integration Tests
```bash
cd tests/integration
./run_all_tests.sh
```

### Run Individual Tests

#### Alpine Installation Test
```bash
docker build -f Dockerfile.alpine -t systemd-monitor-alpine .
docker run --rm systemd-monitor-alpine
```

#### Systemd Integration Test
```bash
docker build -f Dockerfile.systemd -t systemd-monitor-systemd .
docker run --rm --privileged -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    systemd-monitor-systemd
```

## GitHub Actions

Integration tests run automatically on:
- Pull requests to `main`
- Pushes to `main` and `develop`
- Manual workflow dispatch

See `.github/workflows/integration-tests.yml`

## Test Service Definitions

The systemd integration tests create the following test services:

1. **stable.service** - Long-running service that stays up
2. **flaky.service** - Service that crashes after 2 seconds
3. **restart.service** - Service with auto-restart enabled
4. **oneshot.service** - Service that runs once and exits

These services allow us to test all state transitions.
