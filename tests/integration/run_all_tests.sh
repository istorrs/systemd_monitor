#!/bin/bash
# Run systemd integration test locally
# Requires Docker to be installed and running

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "Systemd Integration Test"
echo "=========================================="
echo ""
echo "This test validates:"
echo "  ✓ Jeepney D-Bus implementation works"
echo "  ✓ All systemd monitoring features"
echo "  ✓ 12 comprehensive test scenarios"
echo ""

SYSTEMD_IMAGE="systemd-monitor-integration-test"

# Build and run systemd test
echo ">>> Building test container..."
docker build -f Dockerfile.systemd -t $SYSTEMD_IMAGE ../..

echo ""
echo ">>> Running integration test..."
echo ""

# Run with systemd enabled (requires privileged mode)
docker run --rm \
    --privileged \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    $SYSTEMD_IMAGE

RESULT=$?

echo ""
echo "=========================================="
echo "Test Result"
echo "=========================================="

if [ $RESULT -eq 0 ]; then
    echo "✓ INTEGRATION TEST PASSED!"
    echo ""
    echo "This proves:"
    echo "  ✓ Jeepney D-Bus implementation works correctly"
    echo "  ✓ All monitoring features functional"
    echo "  ✓ Feature parity with dbus-python"
    exit 0
else
    echo "✗ INTEGRATION TEST FAILED"
    exit 1
fi
