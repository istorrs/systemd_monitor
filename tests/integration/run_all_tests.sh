#!/bin/bash
# Run all integration tests locally
# Requires Docker to be installed and running

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "Running All Integration Tests"
echo "=========================================="
echo ""

ALPINE_IMAGE="systemd-monitor-alpine-test"
SYSTEMD_IMAGE="systemd-monitor-systemd-test"

# Build and run Alpine test
echo ">>> Test 1: Alpine Installation Test"
echo ""
docker build -f Dockerfile.alpine -t $ALPINE_IMAGE ../..
docker run --rm $ALPINE_IMAGE
ALPINE_RESULT=$?

echo ""
echo ">>> Alpine test result: $ALPINE_RESULT"
echo ""

# Build and run systemd test
echo ">>> Test 2: Systemd Integration Test"
echo ""
docker build -f Dockerfile.systemd -t $SYSTEMD_IMAGE ../..

# Run with systemd enabled (requires privileged mode)
docker run --rm \
    --privileged \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    $SYSTEMD_IMAGE

SYSTEMD_RESULT=$?

echo ""
echo ">>> Systemd test result: $SYSTEMD_RESULT"
echo ""

# Summary
echo "=========================================="
echo "Integration Test Summary"
echo "=========================================="
echo "Alpine test:   $([ $ALPINE_RESULT -eq 0 ] && echo '✓ PASSED' || echo '✗ FAILED')"
echo "Systemd test:  $([ $SYSTEMD_RESULT -eq 0 ] && echo '✓ PASSED' || echo '✗ FAILED')"
echo ""

if [ $ALPINE_RESULT -eq 0 ] && [ $SYSTEMD_RESULT -eq 0 ]; then
    echo "✓ ALL INTEGRATION TESTS PASSED!"
    exit 0
else
    echo "✗ SOME INTEGRATION TESTS FAILED"
    exit 1
fi
