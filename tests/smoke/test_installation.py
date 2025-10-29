"""
Smoke tests for package installation and imports.

These tests verify that the systemd_monitor package can be installed
and all modules can be imported successfully.
"""

# pylint: disable=import-outside-toplevel,import-error

import sys


class TestImports:
    """Test that all modules can be imported successfully."""

    def test_import_main_module(self):
        """Test that systemd_monitor module can be imported."""
        import systemd_monitor

        assert systemd_monitor is not None
        assert hasattr(systemd_monitor, "__version__")

    def test_import_config(self):
        """Test that config module can be imported."""
        from systemd_monitor import config

        assert config is not None
        assert hasattr(config, "parse_arguments")

    def test_import_dbus_shim(self):
        """Test that dbus_shim module can be imported."""
        from systemd_monitor import dbus_shim

        assert dbus_shim is not None
        assert hasattr(dbus_shim, "DBusException")

    def test_import_prometheus_metrics(self):
        """Test that prometheus_metrics module can be imported."""
        from systemd_monitor import prometheus_metrics

        assert prometheus_metrics is not None
        assert hasattr(prometheus_metrics, "PrometheusMetrics")

    def test_systemd_monitor_module_exists(self):
        """Test that systemd_monitor.systemd_monitor module file exists."""
        from pathlib import Path

        # Find the module file without importing it (avoids D-Bus connection)
        import systemd_monitor

        module_path = Path(systemd_monitor.__file__).parent / "systemd_monitor.py"
        assert module_path.exists(), f"Module file not found: {module_path}"
        assert module_path.is_file()

        # Check file has content
        assert module_path.stat().st_size > 0


class TestPackageStructure:
    """Test package structure and metadata."""

    def test_version_format(self):
        """Test that version follows semantic versioning."""
        import systemd_monitor

        version = systemd_monitor.__version__
        assert isinstance(version, str)
        # Should be like "0.4.0" or "0.4.0-dev"
        parts = version.split("-")[0].split(".")
        assert len(parts) >= 2, f"Invalid version format: {version}"
        # Check that major and minor are numbers
        assert parts[0].isdigit(), f"Invalid major version: {parts[0]}"
        assert parts[1].isdigit(), f"Invalid minor version: {parts[1]}"

    def test_package_has_docstring(self):
        """Test that main package has docstring."""
        import systemd_monitor

        assert systemd_monitor.__doc__ is not None
        assert len(systemd_monitor.__doc__) > 0

    def test_all_modules_have_docstrings(self):
        """Test that main modules have docstrings."""
        from systemd_monitor import config, dbus_shim, prometheus_metrics

        # Note: Can't import systemd_monitor.systemd_monitor without D-Bus
        for module in [config, dbus_shim, prometheus_metrics]:
            assert module.__doc__ is not None, f"{module.__name__} missing docstring"
            assert len(module.__doc__) > 0, f"{module.__name__} has empty docstring"


class TestDependencies:
    """Test that required dependencies are available."""

    def test_jeepney_available(self):
        """Test that jeepney is available (pure Python D-Bus)."""
        try:
            import jeepney

            assert jeepney is not None
        except ImportError:
            # If jeepney not installed, dbus_shim should handle gracefully
            from systemd_monitor import dbus_shim

            assert not dbus_shim.JEEPNEY_AVAILABLE

    def test_prometheus_client_available(self):
        """Test that prometheus_client is available."""
        import prometheus_client

        assert prometheus_client is not None

    def test_no_dbus_python_required(self):
        """Test that dbus-python is NOT required (we use Jeepney)."""
        # This test verifies we're truly pure Python
        # dbus-python should not be in sys.modules
        assert (
            "dbus" not in sys.modules or sys.modules["dbus"].__name__ == "unittest.mock"
        )
