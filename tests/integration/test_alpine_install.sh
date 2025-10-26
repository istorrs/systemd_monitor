#!/bin/sh
# Integration test: Verify installation on Alpine Linux without C compiler
# This proves the pure Python approach works on minimal systems

set -e

echo "=========================================="
echo "Alpine Linux Integration Test"
echo "=========================================="
echo ""

# Verify we're on Alpine
echo "✓ Checking Alpine Linux version..."
cat /etc/alpine-release
echo ""

# Verify no build tools available (proving we don't need them)
echo "✓ Verifying no C compiler available..."
if command -v gcc >/dev/null 2>&1; then
    echo "❌ ERROR: gcc found! This test requires an environment without build tools"
    exit 1
fi
if command -v g++ >/dev/null 2>&1; then
    echo "❌ ERROR: g++ found! This test requires an environment without build tools"
    exit 1
fi
echo "  No C compiler found (expected) ✓"
echo ""

# Install the package
echo "✓ Installing systemd_monitor package..."
cd /app
pip install -e . --no-cache-dir
echo ""

# Verify Jeepney is installed (not dbus-python)
echo "✓ Verifying dependencies..."
pip list | grep jeepney || (echo "❌ ERROR: jeepney not installed" && exit 1)
if pip list | grep -i dbus-python >/dev/null 2>&1; then
    echo "❌ ERROR: dbus-python found! Should be using Jeepney only"
    exit 1
fi
echo "  jeepney installed ✓"
echo "  dbus-python NOT installed ✓"
echo ""

# Test imports
echo "✓ Testing Python imports..."
python3 -c "
import sys
import systemd_monitor
from systemd_monitor import dbus_shim
from systemd_monitor.config import Config
from systemd_monitor.prometheus_metrics import PrometheusMetrics

print('  systemd_monitor version:', systemd_monitor.__version__)
print('  dbus_shim module loaded ✓')
print('  Config module loaded ✓')
print('  PrometheusMetrics module loaded ✓')
"
echo ""

# Test dbus_shim functionality (without actual D-Bus)
echo "✓ Testing dbus_shim API compatibility..."
python3 -c "
from systemd_monitor import dbus_shim

# Test exception class exists
assert hasattr(dbus_shim, 'DBusException')
assert hasattr(dbus_shim.exceptions, 'DBusException')
print('  DBusException class available ✓')

# Test SystemBus function exists
assert hasattr(dbus_shim, 'SystemBus')
assert callable(dbus_shim.SystemBus)
print('  SystemBus() function available ✓')

# Test Interface class exists
assert hasattr(dbus_shim, 'Interface')
print('  Interface class available ✓')

# NOTE: We don't actually call SystemBus() here because:
# 1. No D-Bus daemon running in Alpine container
# 2. We're just testing the API is available
# 3. Actual functionality is tested in systemd integration tests

print('')
print('  All dbus_shim APIs available ✓')
"
echo ""

# Test configuration module
echo "✓ Testing configuration module..."
python3 -c "
from systemd_monitor.config import Config

# Test default config creation
config = Config()
print('  Default config created ✓')
print('  Default services:', len(list(config.monitored_services)))
print('  Prometheus enabled:', config.prometheus_enabled)
print('  Prometheus port:', config.prometheus_port)
"
echo ""

# Test Prometheus metrics (optional dependency)
echo "✓ Testing Prometheus metrics module..."
python3 -c "
from systemd_monitor.prometheus_metrics import get_metrics, PROMETHEUS_AVAILABLE

if PROMETHEUS_AVAILABLE:
    print('  prometheus-client installed ✓')
    metrics = get_metrics()
    print('  PrometheusMetrics singleton created ✓')
    print('  Metrics enabled:', metrics.enabled)
else:
    print('  prometheus-client not installed (optional dependency)')
    print('  Metrics gracefully disabled ✓')
"
echo ""

# Test command-line interface
echo "✓ Testing CLI availability..."
python3 -m systemd_monitor.systemd_monitor --version
python3 -m systemd_monitor.systemd_monitor --help | head -5
echo ""

echo "=========================================="
echo "✓ All Alpine Linux tests PASSED!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Package installed without C compiler ✓"
echo "  - Pure Python dependencies only ✓"
echo "  - All modules import successfully ✓"
echo "  - dbus_shim API compatible ✓"
echo "  - Configuration module works ✓"
echo "  - CLI available ✓"
echo ""
echo "This proves systemd_monitor can be deployed on"
echo "Alpine Linux and other minimal environments!"
