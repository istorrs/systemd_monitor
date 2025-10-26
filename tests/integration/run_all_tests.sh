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
echo "  ✓ Installs without C compiler (pure Python)"
echo "  ✓ All systemd monitoring features work"
echo "  ✓ 12 test scenarios pass"
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
    echo "  ✓ Package installs without C compiler"
    echo "  ✓ Jeepney pure Python implementation works"
    echo "  ✓ All monitoring features functional"
    exit 0
else
    echo "✗ INTEGRATION TEST FAILED"
    exit 1
fi
