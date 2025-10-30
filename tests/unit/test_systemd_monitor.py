"""
Unit tests for systemd_monitor module.

These are proper unit tests that mock D-Bus dependencies,
allowing tests to run in any environment without requiring actual
dbus/systemd installation.
"""

# pylint: disable=import-error,attribute-defined-outside-init
# pylint: disable=import-outside-toplevel,protected-access,too-few-public-methods
# pylint: disable=too-many-lines,invalid-name,duplicate-code
# Test files can be long for comprehensive coverage
import sys
import os
import json
import signal
from unittest.mock import patch, MagicMock, mock_open

import pytest


# Import the real DBusException from dbus_shim
# (which test_dbus_shim has already imported)
# This ensures exception class identity works correctly across the test suite
# pylint: disable=wrong-import-position
from systemd_monitor.dbus_shim import DBusException  # noqa: E402


# Create a mock exceptions module with the REAL exception class
class MockDBusExceptionsModule:
    """Mock dbus.exceptions module."""

    DBusException = DBusException


# Mock dbus_shim BEFORE importing systemd_monitor
# This allows tests to run without real D-Bus connection
# Create a real module-like object instead of MagicMock for proper attribute access
class MockDBusShimModule:
    """Mock dbus_shim module."""

    SystemBus = MagicMock
    ProxyObject = MagicMock
    Interface = MagicMock
    DBusException = DBusException
    get_system_bus = MagicMock
    exceptions = MockDBusExceptionsModule()


mock_dbus_shim = MockDBusShimModule()
sys.modules["systemd_monitor.dbus_shim"] = mock_dbus_shim

# Now we can safely import systemd_monitor
# pylint: disable=wrong-import-position
from systemd_monitor import systemd_monitor  # noqa: E402


class TestStateFunctions:
    """Test state management functions."""

    def test_save_state_creates_directory(self):
        """
        Test that save_state creates the persistence directory if it
        doesn't exist.
        """
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

    def test_save_state_handles_type_error(self):
        """Test that save_state handles TypeError when serializing invalid data."""
        # Create mock that raises TypeError when json.dump is called
        with patch("os.makedirs"), patch("builtins.open", mock_open()), patch(
            "json.dump", side_effect=TypeError("Object not serializable")
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
            # Check that the error message mentions serialization
            error_call_args = str(mock_logger.call_args)
            assert "serializing" in error_call_args.lower()

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

    def test_load_state_initializes_new_service(self):
        """Test that load_state initializes new services not in persistence file."""
        # Persistence file has test.service but not new.service
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
        ), patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service", "new.service"]
        ):
            systemd_monitor.load_state()
            # test.service should have loaded data
            assert systemd_monitor.SERVICE_STATES["test.service"]["starts"] == 5
            # new.service should be initialized with defaults
            assert "new.service" in systemd_monitor.SERVICE_STATES
            assert systemd_monitor.SERVICE_STATES["new.service"]["starts"] == 0
            assert systemd_monitor.SERVICE_STATES["new.service"]["last_state"] is None


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

    def test_active_to_deactivating_transition(self):
        """Test transition from active to deactivating."""
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
        ), patch.object(systemd_monitor, "save_state") as mock_save, patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            changed = {
                "ActiveState": "deactivating",
                "SubState": "stop",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            # State updated but no counter change (deactivating is transient)
            assert (
                systemd_monitor.SERVICE_STATES["test.service"]["last_state"]
                == "deactivating"
            )
            assert not mock_save.called  # No counter changed
            assert mock_log.called

    def test_other_state_transition(self):
        """Test other state transitions (else branch)."""
        with patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {
                "test.service": {
                    "last_state": "activating",
                    "last_change_time": "2025-01-01 00:00:00",
                    "starts": 1,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }
            },
        ), patch.object(systemd_monitor, "save_state") as mock_save, patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            # Transition from activating to reloading (unusual, not a defined pattern)
            changed = {
                "ActiveState": "reloading",
                "SubState": "reload",
                "ExecMainStatus": 0,
                "ExecMainCode": 0,
                "StateChangeTimestamp": 1704067200000000,
            }
            systemd_monitor.handle_properties_changed(
                "test.service", "org.freedesktop.systemd1.Unit", changed, []
            )
            # State updated but no counter change (activating -> reloading is else case)
            assert (
                systemd_monitor.SERVICE_STATES["test.service"]["last_state"]
                == "reloading"
            )
            assert not mock_save.called  # No counter changed
            assert mock_log.called


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
        # Use the real DBusException class to ensure isinstance() works correctly
        mock_exception = DBusException("DBus connection failed")

        with patch.object(systemd_monitor, "load_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor.LOGGER, "error") as mock_logger:
            mock_manager.Subscribe.side_effect = mock_exception
            result = systemd_monitor.setup_dbus_monitor()
            assert result is True  # True means failure
            assert mock_logger.called

    def test_setup_logs_initial_state_change(self):
        """Test that setup logs when initial state differs from persisted state."""
        mock_props = {
            "ActiveState": "active",
            "SubState": "running",
            "ExecMainStatus": 0,
            "ExecMainCode": 0,
            "StateChangeTimestamp": 1704067200000000,
        }

        with patch.object(systemd_monitor, "load_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ), patch.object(
            systemd_monitor, "_get_initial_service_properties", return_value=mock_props
        ), patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {"test.service": {"last_state": "inactive", "logged_unloaded": False}},
        ), patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            mock_manager.Subscribe.return_value = None
            mock_manager.GetUnit.return_value = "/path/to/unit"
            systemd_monitor.setup_dbus_monitor()
            # Should log state change from inactive to active
            assert mock_log.called
            # Verify state was updated
            assert (
                systemd_monitor.SERVICE_STATES["test.service"]["last_state"] == "active"
            )

    def test_setup_logs_initial_state_no_change(self):
        """Test that setup logs correctly when initial state matches persisted state."""
        mock_props = {
            "ActiveState": "active",
            "SubState": "running",
            "ExecMainStatus": 0,
            "ExecMainCode": 0,
            "StateChangeTimestamp": 1704067200000000,
        }

        with patch.object(systemd_monitor, "load_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service"]
        ), patch.object(
            systemd_monitor, "_get_initial_service_properties", return_value=mock_props
        ), patch.object(
            systemd_monitor,
            "SERVICE_STATES",
            {"test.service": {"last_state": "active", "logged_unloaded": False}},
        ), patch.object(
            systemd_monitor.LOGGER, "info"
        ) as mock_log:
            mock_manager.Subscribe.return_value = None
            mock_manager.GetUnit.return_value = "/path/to/unit"
            systemd_monitor.setup_dbus_monitor()
            # Should still log initial state
            assert mock_log.called

    def test_setup_handles_service_subscribe_exception(self):
        """Test that setup handles exception when subscribing to individual service."""
        # Use the real DBusException class to ensure isinstance() works correctly
        mock_exception = DBusException("Service not found")

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
        ), patch.object(
            systemd_monitor.LOGGER, "warning"
        ) as mock_warn:
            mock_manager.Subscribe.return_value = None
            mock_manager.GetUnit.side_effect = mock_exception
            result = systemd_monitor.setup_dbus_monitor()
            # Should log warning but not fail completely
            assert mock_warn.called
            assert result is False  # Setup succeeded overall


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
        # Use the real DBusException class to ensure isinstance() works correctly
        mock_exception = DBusException("Failed to get unit")

        with patch.object(systemd_monitor, "MANAGER_INTERFACE") as mock_manager:
            mock_manager.GetUnit.side_effect = mock_exception
            result = systemd_monitor._get_initial_service_properties("test.service")
            assert result is None


class TestSignalHandler:
    """Test signal handler."""

    def test_signal_handler_saves_state(self):
        """Test that signal handler saves state before exiting."""
        with patch.object(systemd_monitor, "save_state") as mock_save, patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ), patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor, "LOGGER"
        ), patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ) as mock_event, patch(
            "sys.exit"
        ) as mock_exit:
            systemd_monitor.signal_handler(signal.SIGINT, None)
            mock_save.assert_called_once()
            mock_event.set.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_signal_handler_unsubscribes(self):
        """Test that signal handler unsubscribes from D-Bus."""
        with patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor, "LOGGER"
        ), patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ), patch(
            "sys.exit"
        ):
            systemd_monitor.signal_handler(signal.SIGINT, None)
            mock_manager.Unsubscribe.assert_called_once()

    def test_signal_handler_handles_unsub_error(self):
        """Test that signal handler handles unsubscribe errors."""
        # Use the real DBusException class to ensure isinstance() works correctly
        mock_exception = DBusException("Failed to unsubscribe")

        with patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ) as mock_manager, patch.object(systemd_monitor, "SYSTEM_BUS"), patch.object(
            systemd_monitor.LOGGER, "exception"
        ) as mock_logger, patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ), patch(
            "sys.exit"
        ):
            mock_manager.Unsubscribe.side_effect = mock_exception
            systemd_monitor.signal_handler(signal.SIGINT, None)
            # Should log exception but still exit
            assert mock_logger.called

    def test_signal_handler_handles_bus_close_error(self):
        """Test that signal handler handles SYSTEM_BUS close errors."""
        with patch.object(systemd_monitor, "save_state"), patch.object(
            systemd_monitor, "MANAGER_INTERFACE"
        ), patch.object(systemd_monitor, "SYSTEM_BUS") as mock_bus, patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_logger, patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ), patch(
            "sys.exit"
        ):
            mock_bus.close.side_effect = Exception("Failed to close bus")
            systemd_monitor.signal_handler(signal.SIGINT, None)
            # Should log error but still exit gracefully
            assert mock_logger.called


class TestInitializeFromConfig:
    """Test initialize_from_config function."""

    def test_initialize_with_services(self):
        """Test initialization with list of services."""
        mock_config = MagicMock()
        mock_config.monitored_services = ["test.service", "another.service"]

        with patch.object(systemd_monitor.LOGGER, "info") as mock_log:
            systemd_monitor.initialize_from_config(mock_config)
            assert systemd_monitor.MONITORED_SERVICES == [
                "test.service",
                "another.service",
            ]
            assert systemd_monitor.MAX_SERVICE_NAME_LEN == len("another.service")
            assert mock_log.called

    def test_initialize_with_empty_services(self):
        """Test initialization with empty service list."""
        mock_config = MagicMock()
        mock_config.monitored_services = []

        with patch.object(systemd_monitor.LOGGER, "info") as mock_log:
            systemd_monitor.initialize_from_config(mock_config)
            assert not systemd_monitor.MONITORED_SERVICES
            assert systemd_monitor.MAX_SERVICE_NAME_LEN == 30  # Default value
            assert mock_log.called


class TestCLIHelpers:
    """Test CLI helper functions."""

    def test_print_help(self, capsys):
        """Test _print_help function."""
        with patch.object(
            systemd_monitor, "MONITORED_SERVICES", ["test.service", "another.service"]
        ):
            systemd_monitor._print_help("/tmp/test.log")
            captured = capsys.readouterr()
            assert "Service Monitor" in captured.out
            assert "test.service" in captured.out
            assert "/tmp/test.log" in captured.out

    def test_clear_files_both_exist(self):
        """Test _clear_files when both files exist."""
        with patch("os.path.exists", return_value=True), patch(
            "os.remove"
        ) as mock_remove, patch("builtins.print") as mock_print:
            systemd_monitor._clear_files("/tmp/test.log", "/tmp/state.json")
            assert mock_remove.call_count == 2
            assert mock_print.call_count == 2

    def test_clear_files_none_exist(self):
        """Test _clear_files when files don't exist."""
        with patch("os.path.exists", return_value=False), patch(
            "os.remove"
        ) as mock_remove:
            systemd_monitor._clear_files("/tmp/test.log", "/tmp/state.json")
            # Should not try to remove non-existent files
            assert not mock_remove.called

    def test_clear_files_with_none(self):
        """Test _clear_files with None values."""
        with patch("os.path.exists", return_value=True), patch(
            "os.remove"
        ) as mock_remove:
            systemd_monitor._clear_files(None, None)
            # Should not try to remove None paths
            assert not mock_remove.called

    def test_create_argument_parser(self):
        """Test _create_argument_parser function."""
        parser = systemd_monitor._create_argument_parser()
        assert parser is not None
        # Parse test arguments
        args = parser.parse_args(["--debug", "--services", "test.service"])
        assert args.debug is True
        assert args.services == ["test.service"]

    def test_setup_logging_default_file(self):
        """Test _setup_logging with default log file."""
        with patch.object(systemd_monitor, "LOGGER"):
            # Should not change handler when using default file
            systemd_monitor._setup_logging(systemd_monitor.DEFAULT_LOG_FILE, False)
            # Just verify it doesn't crash

    def test_setup_logging_custom_file(self):
        """Test _setup_logging with custom log file."""
        with patch.object(systemd_monitor, "LOGGER") as mock_logger, patch.object(
            systemd_monitor, "file_handler"
        ), patch("systemd_monitor.systemd_monitor.RotatingFileHandler") as mock_handler:
            mock_handler.return_value = MagicMock()
            systemd_monitor._setup_logging("/custom/log.log", True)
            # Should have called removeHandler and addHandler
            assert mock_logger.removeHandler.called
            assert mock_logger.addHandler.called
            assert mock_logger.setLevel.called

    def test_handle_command_actions_help(self):
        """Test _handle_command_actions with help flag."""
        args = MagicMock()
        args.help = True
        args.version = False
        args.clear = False

        with patch.object(systemd_monitor, "_print_help") as mock_help, patch(
            "sys.exit"
        ) as mock_exit:
            systemd_monitor._handle_command_actions(args, "/tmp/test.log")
            mock_help.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_handle_command_actions_version(self):
        """Test _handle_command_actions with version flag."""
        args = MagicMock()
        args.help = False
        args.version = True
        args.clear = False

        with patch("builtins.print") as mock_print, patch("sys.exit") as mock_exit:
            systemd_monitor._handle_command_actions(args, "/tmp/test.log")
            mock_print.assert_called_once()
            # Verify version string is displayed
            call_args = mock_print.call_args[0][0]
            assert "systemd-monitor version:" in call_args
            assert systemd_monitor.__version__ in call_args
            mock_exit.assert_called_once_with(0)

    def test_handle_command_actions_clear(self):
        """Test _handle_command_actions with clear flag."""
        args = MagicMock()
        args.help = False
        args.version = False
        args.clear = True
        args.log_file = "/tmp/test.log"
        args.persistence_file = "/tmp/state.json"

        with patch.object(systemd_monitor, "_clear_files") as mock_clear, patch(
            "sys.exit"
        ) as mock_exit:
            systemd_monitor._handle_command_actions(args, "/tmp/test.log")
            mock_clear.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_handle_command_actions_no_action(self):
        """Test _handle_command_actions with no action flags."""
        args = MagicMock()
        args.help = False
        args.version = False
        args.clear = False

        result = systemd_monitor._handle_command_actions(args, "/tmp/test.log")
        assert result is False  # No action performed


class TestMainFunction:
    """Test main function."""

    def test_main_with_debug_flag(self):
        """Test main function configuration with debug flag."""
        test_args = ["prog", "--debug", "--services", "test.service"]

        with patch("sys.argv", test_args), patch.object(
            systemd_monitor, "initialize_from_config"
        ) as mock_init, patch.object(
            systemd_monitor, "_setup_logging"
        ) as mock_setup_log, patch.object(
            systemd_monitor, "_handle_command_actions", return_value=False
        ), patch.object(
            systemd_monitor, "setup_dbus_monitor", return_value=False
        ), patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ) as mock_event, patch(
            "signal.signal"
        ):
            # Mock wait() to raise KeyboardInterrupt to exit cleanly
            mock_event.wait.side_effect = KeyboardInterrupt()

            with patch.object(systemd_monitor, "signal_handler"), patch("sys.exit"):
                try:
                    systemd_monitor.main()
                except KeyboardInterrupt:
                    pass  # Expected

                # Verify initialization was called
                assert mock_init.called
                # Verify setup_logging was called
                assert mock_setup_log.called

    def test_main_exits_on_empty_services(self):
        """Test that main exits when no services are configured."""
        test_args = ["prog", "--debug"]  # No --services argument

        with patch("sys.argv", test_args), patch.object(
            systemd_monitor, "initialize_from_config"
        ), patch.object(systemd_monitor, "_setup_logging"), patch.object(
            systemd_monitor, "_handle_command_actions", return_value=False
        ), patch.object(
            systemd_monitor, "MONITORED_SERVICES", []
        ), patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_logger, patch(
            "builtins.print"
        ) as mock_print, patch(
            "sys.exit"
        ) as mock_exit:
            # Make sys.exit raise SystemExit to actually stop execution
            mock_exit.side_effect = SystemExit(1)

            with pytest.raises(SystemExit):
                systemd_monitor.main()

            # Verify error was logged and printed
            assert mock_logger.called
            assert mock_print.called
            # Check that helpful error message was printed
            print_call_args = str(mock_print.call_args)
            assert "No services configured" in print_call_args
            mock_exit.assert_called_once_with(1)

    def test_main_exits_on_dbus_setup_failure(self):
        """Test that main exits when D-Bus setup fails."""
        test_args = ["prog", "--services", "test.service"]

        with patch("sys.argv", test_args), patch.object(
            systemd_monitor, "initialize_from_config"
        ), patch.object(systemd_monitor, "_setup_logging"), patch.object(
            systemd_monitor, "_handle_command_actions", return_value=False
        ), patch.object(
            systemd_monitor, "setup_dbus_monitor", return_value=True
        ), patch.object(
            systemd_monitor.LOGGER, "error"
        ) as mock_logger, patch.object(
            systemd_monitor, "signal_handler"
        ), patch(
            "sys.exit"
        ) as mock_exit:
            # Make sys.exit raise SystemExit to actually stop execution
            mock_exit.side_effect = SystemExit(1)

            with pytest.raises(SystemExit):
                systemd_monitor.main()

            # Should log error and exit with code 1
            assert mock_logger.called
            mock_exit.assert_called_once_with(1)

    def test_main_with_custom_files(self):
        """Test main function with custom log and persistence files."""
        test_args = [
            "prog",
            "--services",
            "test.service",
            "--log-file",
            "/tmp/custom.log",
            "--persistence-file",
            "/tmp/custom_state.json",
        ]

        with patch("sys.argv", test_args), patch.object(
            systemd_monitor, "initialize_from_config"
        ), patch.object(
            systemd_monitor, "_setup_logging"
        ) as mock_setup_log, patch.object(
            systemd_monitor, "_handle_command_actions", return_value=False
        ), patch.object(
            systemd_monitor, "setup_dbus_monitor", return_value=False
        ), patch.object(
            systemd_monitor, "SHUTDOWN_EVENT"
        ) as mock_event, patch(
            "signal.signal"
        ):
            # Mock wait() to raise KeyboardInterrupt to exit cleanly
            mock_event.wait.side_effect = KeyboardInterrupt()

            with patch.object(systemd_monitor, "signal_handler"), patch("sys.exit"):
                try:
                    systemd_monitor.main()
                except KeyboardInterrupt:
                    pass

                # Verify setup_logging was called with custom log file
                assert mock_setup_log.called
                # Check that PERSISTENCE_FILE was updated
                assert systemd_monitor.PERSISTENCE_FILE == "/tmp/custom_state.json"


class TestVersion:
    """Test version information."""

    def test_version_attribute_exists(self):
        """Test that __version__ attribute exists."""
        assert hasattr(systemd_monitor, "__version__")
        assert isinstance(systemd_monitor.__version__, str)

    def test_version_format(self):
        """Test that version follows semantic versioning format."""
        version = systemd_monitor.__version__
        # Should be either X.Y.Z or X.Y.Z-dev or similar
        assert len(version) > 0
        # Should contain at least one dot for version parts
        assert "." in version or "-dev" in version


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
        # Note: PERSISTENCE_FILE can be modified by main(), so check if
        # it contains .json
        assert systemd_monitor.PERSISTENCE_FILE.endswith(".json")
        # Verify default value has the expected structure
        default_file = os.path.join(
            systemd_monitor.PERSISTENCE_DIR, systemd_monitor.PERSISTENCE_FILENAME
        )
        assert default_file.endswith("service_states.json")
