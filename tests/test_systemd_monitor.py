"""
Unit tests for systemd_monitor module.

These are proper unit tests that mock dbus and GLib dependencies,
allowing tests to run in any environment without requiring actual
dbus/systemd installation.
"""

# pylint: disable=import-error,attribute-defined-outside-init
# pylint: disable=import-outside-toplevel,protected-access,too-few-public-methods
import sys
import json
import signal
from unittest.mock import patch, MagicMock, mock_open


# Create a proper DBusException class that can be caught
class MockDBusException(Exception):
    """Mock DBus exception for testing."""


# Mock dbus and GLib BEFORE importing systemd_monitor
# This allows tests to run without dbus-python installed
mock_dbus = MagicMock()


# Create a mock exceptions module with our real exception class
class MockDBusExceptionsModule:
    """Mock dbus.exceptions module."""

    DBusException = MockDBusException


mock_dbus_exceptions = MockDBusExceptionsModule()
mock_dbus.exceptions = mock_dbus_exceptions

sys.modules["dbus"] = mock_dbus
sys.modules["dbus.mainloop"] = MagicMock()
sys.modules["dbus.mainloop.glib"] = MagicMock()
sys.modules["dbus.exceptions"] = mock_dbus_exceptions
sys.modules["gi"] = MagicMock()
sys.modules["gi.repository"] = MagicMock()
sys.modules["gi.repository.GLib"] = MagicMock()

# Now we can safely import systemd_monitor
# pylint: disable=wrong-import-position
from systemd_monitor import systemd_monitor  # noqa: E402


class TestStateFunctions:
    """Test state management functions."""

    def test_save_state_creates_directory(self):
        """Test that save_state creates the persistence directory if it doesn't exist."""
        with patch("os.makedirs") as mock_makedirs, patch(
            "builtins.open", mock_open()
        ) as mock_file, patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ):
            systemd_monitor.save_state()
            mock_makedirs.assert_called_once_with(
                systemd_monitor.PERSISTENCE_DIR, exist_ok=True
            )
            mock_file.assert_called_once()

    def test_save_state_handles_io_error(self):
        """Test that save_state handles IOError gracefully."""
        with patch("os.makedirs"), patch(
            "builtins.open", side_effect=IOError("Test error")
        ), patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_logger:
            systemd_monitor.save_state()
            # Should log error but not raise
            assert mock_logger.called

    def test_load_state_creates_new_if_missing(self):
        """Test that load_state initializes new states if persistence file missing."""
        with patch("os.path.exists", return_value=False), patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service", "another.service"]
        ):
            systemd_monitor.load_state()
            # Should initialize SERVICE_STATES with default values
            assert "test.service" in systemd_monitor.SERVICE_STATES
            assert "another.service" in systemd_monitor.SERVICE_STATES
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 0

    def test_load_state_loads_existing_file(self):
        """Test that load_state properly loads from persistence file."""
        mock_data = {
            "test.service": {
                "last_state": "active",
                "last_change_time": "2025-01-01 00:00:00",
                "starts": 5,
                "stops": 3,
                "crashes": 1,
                "logged_unloaded": False,
            }
        }
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=json.dumps(mock_data))
        ), patch.object(systemd_monitor, "MONITORED_SERVICES", ["test.service"]):
            systemd_monitor.load_state()
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 5
            assert systemd_monitor.SERVICE_STATES["test.service"]["crashes"] == 1

    def test_load_state_handles_json_error(self):
        """Test that load_state handles JSON decode errors gracefully."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data="invalid json")
        ), patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ), patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_logger:
            systemd_monitor.load_state()
            # Should log error and initialize default states
            assert mock_logger.called
            assert "test.service" in systemd_monitor.SERVICE_STATES

    def test_load_state_removes_unmonitored_services(self):
        """Test that load_state removes services no longer in MONITORED_SERVICES."""
        mock_data = {
            "test.service": {
                "last_state": "active",
                "last_change_time": "2025-01-01 00:00:00",
                "starts": 5,
                "stops": 3,
                "crashes": 1,
                "logged_unloaded": False,
            },
            "old.service": {
                "last_state": "inactive",
                "last_change_time": "2025-01-01 00:00:00",
                "starts": 1,
                "stops": 1,
                "crashes": 0,
                "logged_unloaded": False,
            },
        }
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=json.dumps(mock_data))
        ), patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ):  # Only monitoring test.service
            systemd_monitor.load_state()
            assert "test.service" in systemd_monitor.SERVICE_STATES
            assert "old.service" not in systemd_monitor.SERVICE_STATES


class TestHandlePropertiesChanged:
    """Test the properties changed handler."""

    def test_start_detection(self):
        """Test detection of service start."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "inactive",
                    "last_change_time": None,
                    "starts": 0,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            changed = {
                "ActiveState": "active",
                "SubState": "running",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 1
            assert mock_log.called

    def test_stop_detection(self):
        """Test detection of service stop."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            changed = {
                "ActiveState": "inactive",
                "SubState": "dead",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            assert systemd_monitor.SERVICE_STATES["test.service"]["stops"] == 1
            assert mock_log.called

    def test_crash_detection(self):
        """Test detection of service crash."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_log:
            changed = {
                "ActiveState": "failed",
                "SubState": "failed",
                "ExecMainStatus": 1,
                "ExecMainCode": 1,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            assert systemd_monitor.SERVICE_STATES["test.service"]["crashes"] == 1
            assert systemd_monitor.SERVICE_STATES["test.service"]["stops"] == 1
            assert mock_log.called

    def test_restart_cycle_detection(self):
        """Test detection of service restart cycle."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            # Transition from active to activating indicates restart
            changed = {
                "ActiveState": "activating",
                "SubState": "auto-restart",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 2
            assert systemd_monitor.SERVICE_STATES["test.service"]["stops"] == 1
            assert mock_log.called

    def test_no_change_ignored(self):
        """Test that unchanged state is ignored."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "active",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state") as mock_save:
            # Same state as before
            changed = {
                "ActiveState": "active",
                "SubState": "running",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            # Counters should not change
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 1
            assert systemd_monitor.SERVICE_STATES["test.service"]["stops"] == 0
            # save_state should not be called (no counter change)
            assert not mock_save.called


class TestSetupDBusMonitor:
    """Test D-Bus monitor setup."""

    def test_setup_loads_state(self):
        """Test that setup_dbus_monitor loads state from persistence."""
        with patch.object(systemd_monitor, "load_state") as mock_load, patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ), patch.object(
            systemd_monitor, "_get_initial_service_properties", return_value=None
        ), patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {"test.service": {"last_state": None, "logged_unloaded": False}},
        ):
            mock_manager.Subscribe.return_value = None
            mock_manager.GetUnit.return_value = "/path/to/unit"
            systemd_monitor.setup_dbus_monitor()
            mock_load.assert_called_once()

    def test_setup_subscribes_to_dbus(self):
        """Test that setup_dbus_monitor subscribes to D-Bus signals."""
        with patch.object(systemd_monitor, "load_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ), patch.object(
            systemd_monitor, "_get_initial_service_properties", return_value=None
        ), patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {"test.service": {"last_state": None, "logged_unloaded": False}},
        ):
            mock_manager.Subscribe.return_value = None
            mock_manager.GetUnit.return_value = "/path/to/unit"
            result = systemd_monitor.setup_dbus_monitor()
            mock_manager.Subscribe.assert_called_once()
            assert result is False  # False means success

    def test_setup_handles_dbus_exception(self):
        """Test that setup_dbus_monitor handles D-Bus exceptions."""
        # Use the MockDBusException that's been set up in the module mock
        mock_exception = MockDBusException("DBus connection failed")

        with patch.object(systemd_monitor, "load_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor.LOGGER, "error") as mock_logger:
            mock_manager.Subscribe.side_effect = mock_exception
            result = systemd_monitor.setup_dbus_monitor()
            assert result is True  # True means failure
            assert mock_logger.called


class TestGetInitialServiceProperties:
    """Test getting initial service properties."""

    def test_get_properties_success(self):
        """Test successful property retrieval."""
        mock_unit_obj = MagicMock()
        mock_props = MagicMock()
        mock_props.Get.side_effect = [
            "active",
            "running",
            0,
            0,
            1704067200000000,
        ]

        with patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor, "SYSTEM_BUS") as mock_bus:
            mock_manager.GetUnit.return_value = "/path/to/unit"
            mock_bus.get_object.return_value = mock_unit_obj

            # Mock dbus.Interface to return our mock_props
            with patch("systemd_monitor.systemd_monitor.dbus") as mock_dbus_interface:
                mock_dbus_interface.Interface.return_value = mock_props

                result = systemd_monitor._get_initial_service_properties("test.service")
                assert result is not None
                assert result["ActiveState"] == "active"
                assert result["SubState"] == "running"

    def test_get_properties_handles_exception(self):
        """Test property retrieval handles exceptions."""
        # Use the MockDBusException
        mock_exception = MockDBusException("Failed to get unit")

        with patch.object(systemd_monitor, "MANAGER_INTERFACE") as mock_manager:
            mock_manager.GetUnit.side_effect = mock_exception
            result = systemd_monitor._get_initial_service_properties("test.service")
            assert result is None


class TestSignalHandler:
    """Test signal handler."""

    def test_signal_handler_saves_state(self):
        """Test that signal handler saves state before exiting."""
        mock_loop = MagicMock()

        with patch.object(systemd_monitor, "save_state") as mock_save, patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ), patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor, "LOGGER"
        ), patch(
            "sys.exit"
        ) as mock_exit:
            systemd_monitor.signal_handler(signal.SIGINT, None, mock_loop)
            mock_save.assert_called_once()
            mock_loop.quit.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_signal_handler_unsubscribes(self):
        """Test that signal handler unsubscribes from D-Bus."""
        mock_loop = MagicMock()

        with patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor, "LOGGER"
        ), patch(
            "sys.exit"
        ):
            systemd_monitor.signal_handler(signal.SIGINT, None, mock_loop)
            mock_manager.Unsubscribe.assert_called_once()

    def test_signal_handler_handles_unsub_error(self):
        """Test that signal handler handles unsubscribe errors."""
        mock_loop = MagicMock()
        # Use the MockDBusException
        mock_exception = MockDBusException("Failed to unsubscribe")

        with patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor.LOGGER, "warning"
        ) as mock_logger, patch(
            "sys.exit"
        ):
            mock_manager.Unsubscribe.side_effect = mock_exception
            systemd_monitor.signal_handler(signal.SIGINT, None, mock_loop)
            # Should log warning but still exit
            assert mock_logger.called


class TestConstants:
    """Test module constants and initialization."""

    def test_monitored_services_is_list(self):
        """Test that MONITORED_SERVICES is a list."""
        assert isinstance(systemd_monitor.MONITORED_SERVICES, list)

    def test_monitored_services_are_strings(self):
        """Test that monitored services are strings."""
        # Initialize with test data
        with patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service", "another.service"]
        ):
            for service in systemd_monitor.MONITORED_SERVICES:
                assert isinstance(service, str)
                assert service.endswith(".service")

    def test_signal_names_mapping(self):
        """Test that SIGNAL_NAMES contains expected signals."""
        assert "SIGINT" in systemd_monitor.SIGNAL_NAMES.values()
        assert "SIGTERM" in systemd_monitor.SIGNAL_NAMES.values()

    def test_persistence_file_path(self):
        """Test that persistence file path is properly constructed."""
        assert systemd_monitor.PERSISTENCE_FILE.endswith("service_states.json")
        assert systemd_monitor.PERSISTENCE_DIR in systemd_monitor.PERSISTENCE_FILE
