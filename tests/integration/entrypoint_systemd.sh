#!/bin/bash
# Entry point for systemd container integration test

set -e

echo "Starting systemd container integration test..."
echo ""

# Start systemd in background
/lib/systemd/systemd --system &
SYSTEMD_PID=$!

echo "Waiting for systemd to initialize..."
sleep 5

# Verify systemd is running
if ! systemctl --version > /dev/null 2>&1; then
    echo "ERROR: systemd failed to start"
    exit 1
fi

echo "systemd is running (PID: $SYSTEMD_PID)"
echo ""

# Run integration tests
python3 /app/tests/integration/test_systemd_integration.py
TEST_RESULT=$?

echo ""
echo "Integration test completed with exit code: $TEST_RESULT"

# Shutdown systemd gracefully
echo "Shutting down systemd..."
kill -TERM $SYSTEMD_PID 2>/dev/null || true
wait $SYSTEMD_PID 2>/dev/null || true

exit $TEST_RESULT
