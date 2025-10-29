"""
Smoke tests for basic functionality.

These tests verify configuration structure, basic setup, and error handling
without requiring D-Bus or systemd.
"""

# pylint: disable=import-outside-toplevel,import-error


class TestConfigurationModule:
    """Test configuration module structure."""

    def test_config_module_imports(self):
        """Test that config module can be imported."""
        from systemd_monitor import config

        assert config is not None

    def test_config_has_dataclass(self):
        """Test that Config dataclass exists."""
        from systemd_monitor import config

        assert hasattr(config, "Config")
        # Config is the main configuration dataclass
        config_class = config.Config  # pylint: disable=invalid-name
        assert config_class is not None

    def test_config_parse_arguments_exists(self):
        """Test that parse_arguments function exists."""
        from systemd_monitor import config

        assert hasattr(config, "parse_arguments")
        assert callable(config.parse_arguments)


class TestExceptionClasses:
    """Test custom exception classes."""

    def test_dbus_exception_can_be_raised(self):
        """Test that DBusException can be instantiated and raised."""
        from systemd_monitor.dbus_shim import DBusException

        exc = DBusException("Test error")
        assert str(exc) == "Test error"
        assert isinstance(exc, Exception)

        # Test it can be raised and caught
        try:
            raise DBusException("Test message")
        except DBusException as e:
            assert str(e) == "Test message"

    def test_dbus_exception_identity(self):
        """Test that DBusException class identity works."""
        from systemd_monitor.dbus_shim import DBusException, exceptions

        # Verify class identity (important for exception handling)
        assert exceptions.DBusException is DBusException
        exc = DBusException("test")
        assert isinstance(exc, exceptions.DBusException)


class TestPrometheusMetrics:
    """Test Prometheus metrics module."""

    def test_prometheus_module_imports(self):
        """Test that prometheus_metrics module can be imported."""
        from systemd_monitor import prometheus_metrics

        assert prometheus_metrics is not None

    def test_prometheus_metrics_class_exists(self):
        """Test that PrometheusMetrics class exists."""
        from systemd_monitor.prometheus_metrics import PrometheusMetrics

        assert PrometheusMetrics is not None
        # Check it's a class
        assert isinstance(PrometheusMetrics, type)


class TestLoggingSetup:
    """Test logging configuration."""

    def test_log_levels_valid(self):
        """Test that log level configuration works."""
        import logging

        # Test that standard log levels work
        for level_name in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            level = logging.getLevelName(level_name)
            assert isinstance(level, int)

    def test_logging_module_available(self):
        """Test that logging module is available."""
        import logging

        assert logging is not None
        assert hasattr(logging, "getLogger")
