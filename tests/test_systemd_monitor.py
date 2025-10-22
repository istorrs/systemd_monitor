"""
Unit tests for systemd_monitor module.
"""
# pylint: disable=import-error,attribute-defined-outside-init
# pylint: disable=import-outside-toplevel,protected-access
import os
import json
import signal
from unittest.mock import patch, MagicMock, mock_open
import pytest

# Check if dbus is available
try:
    import dbus as _dbus_check  # pylint: disable=unused-import
    DBUS_AVAILABLE = True
    # Only import if dbus is available
    from systemd_monitor import systemd_monitor  # pylint: disable=wrong-import-position
except (ImportError, ModuleNotFoundError):
    DBUS_AVAILABLE = False
    # Create a dummy module object to prevent NameError in test definitions
    systemd_monitor = None  # pylint: disable=invalid-name

# Skip all tests if dbus is not available
pytestmark = pytest.mark.skipif(
    not DBUS_AVAILABLE,
    reason="dbus-python not available in this environment"
)


class TestStateFunctions:
    """Test state management functions."""

    def test_save_state_creates_directory(self):
        """Test that save_state creates the persistence directory if it doesn't exist."""
        with patch('os.makedirs') as mock_makedirs, \
             patch('builtins.open', mock_open()) as mock_file, \
             patch.object(systemd_monitor, 'SERVICE_STATES',
                         {'test.service': {'last_state': 'active',
                                          'last_change_time': '2025-01-01 00:00:00',
                                          'starts': 1, 'stops': 0, 'crashes': 0,
                                          'logged_unloaded': False}}):
            systemd_monitor.save_state()
            mock_makedirs.assert_called_once_with(
                systemd_monitor.PERSISTENCE_DIR, exist_ok=True
            )
            mock_file.assert_called_once()

    def test_save_state_handles_io_error(self):
        """Test that save_state handles IOError gracefully."""
        with patch('os.makedirs'), \
             patch('builtins.open', side_effect=IOError("Disk full")), \
             patch.object(systemd_monitor.LOGGER, 'error') as mock_error, \
             patch.object(systemd_monitor, 'SERVICE_STATES',
                         {'test.service': {'last_state': 'active',
                                          'last_change_time': '2025-01-01 00:00:00',
                                          'starts': 1, 'stops': 0, 'crashes': 0,
                                          'logged_unloaded': False}}):
            systemd_monitor.save_state()
            mock_error.assert_called()
            assert "Error saving service states" in str(mock_error.call_args)

    def test_load_state_creates_new_if_missing(self):
        """Test that load_state initializes new states if file doesn't exist."""
        with patch('os.path.exists', return_value=False), \
             patch.object(systemd_monitor.LOGGER, 'info') as mock_info:
            systemd_monitor.load_state()
            mock_info.assert_called()
            assert "Persistence file not found" in str(mock_info.call_args)
            # Check that SERVICE_STATES is initialized for all monitored services
            for service in systemd_monitor.MONITORED_SERVICES:
                assert service in systemd_monitor.SERVICE_STATES
                assert systemd_monitor.SERVICE_STATES[service]['starts'] == 0

    def test_load_state_loads_existing_file(self):
        """Test that load_state correctly loads data from existing file."""
        test_data = {
            'wirepas-gateway.service': {
                'last_state': 'active',
                'last_change_time': '2025-01-01 00:00:00',
                'starts': 5,
                'stops': 3,
                'crashes': 1,
                'logged_unloaded': False
            }
        }
        mock_file_content = json.dumps(test_data)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=mock_file_content)), \
             patch.object(systemd_monitor.LOGGER, 'info'):
            systemd_monitor.load_state()
            service = 'wirepas-gateway.service'
            assert systemd_monitor.SERVICE_STATES[service]['starts'] == 5
            assert systemd_monitor.SERVICE_STATES[service]['stops'] == 3
            assert systemd_monitor.SERVICE_STATES[service]['crashes'] == 1

    def test_load_state_handles_json_error(self):
        """Test that load_state handles JSON decode errors."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="invalid json")), \
             patch.object(systemd_monitor.LOGGER, 'error') as mock_error:
            systemd_monitor.load_state()
            mock_error.assert_called()
            assert "Error loading service states" in str(mock_error.call_args)

    def test_load_state_removes_unmonitored_services(self):
        """Test that load_state removes services no longer monitored."""
        test_data = {
            'wirepas-gateway.service': {
                'last_state': 'active',
                'last_change_time': '2025-01-01 00:00:00',
                'starts': 5,
                'stops': 3,
                'crashes': 1,
                'logged_unloaded': False
            },
            'removed.service': {
                'last_state': 'inactive',
                'last_change_time': '2025-01-01 00:00:00',
                'starts': 0,
                'stops': 0,
                'crashes': 0,
                'logged_unloaded': False
            }
        }
        mock_file_content = json.dumps(test_data)

        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=mock_file_content)), \
             patch.object(systemd_monitor.LOGGER, 'info') as mock_info:
            systemd_monitor.load_state()
            assert 'removed.service' not in systemd_monitor.SERVICE_STATES
            # Check that info was logged about removal
            calls = [str(c) for c in mock_info.call_args_list]
            assert any('Removed unmonitored service' in c for c in calls)


class TestHandlePropertiesChanged:
    """Test the PropertiesChanged signal handler."""

    def setup_method(self):
        """Set up test fixtures."""
        # Initialize SERVICE_STATES for a test service
        self.service_name = 'test.service'
        systemd_monitor.SERVICE_STATES[self.service_name] = {
            'last_state': 'inactive',
            'last_change_time': None,
            'starts': 0,
            'stops': 0,
            'crashes': 0,
            'logged_unloaded': False
        }

    def test_start_detection(self):
        """Test that a service start is correctly detected and counted."""
        changed = {
            'ActiveState': 'active',
            'SubState': 'running',
            'ExecMainStatus': 0,
            'ExecMainCode': 0,
            'StateChangeTimestamp': 1640000000000000
        }

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.LOGGER, 'info'):
            systemd_monitor.handle_properties_changed(
                self.service_name, None, changed, None
            )

            assert systemd_monitor.SERVICE_STATES[self.service_name]['starts'] == 1
            assert systemd_monitor.SERVICE_STATES[self.service_name]['stops'] == 0
            assert systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] == 'active'
            mock_save.assert_called_once()

    def test_stop_detection(self):
        """Test that a service stop is correctly detected and counted."""
        # Set initial state to active
        systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] = 'active'

        changed = {
            'ActiveState': 'inactive',
            'SubState': 'dead',
            'ExecMainStatus': 0,
            'ExecMainCode': 0,
            'StateChangeTimestamp': 1640000000000000
        }

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.LOGGER, 'info'):
            systemd_monitor.handle_properties_changed(
                self.service_name, None, changed, None
            )

            assert systemd_monitor.SERVICE_STATES[self.service_name]['stops'] == 1
            assert systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] == 'inactive'
            mock_save.assert_called_once()

    def test_crash_detection(self):
        """Test that a service crash is correctly detected and counted."""
        # Set initial state to active
        systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] = 'active'

        changed = {
            'ActiveState': 'failed',
            'SubState': 'failed',
            'ExecMainStatus': 9,  # SIGKILL
            'ExecMainCode': 2,    # Signal code
            'StateChangeTimestamp': 1640000000000000
        }

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.LOGGER, 'error') as mock_error:
            systemd_monitor.handle_properties_changed(
                self.service_name, None, changed, None
            )

            assert systemd_monitor.SERVICE_STATES[self.service_name]['crashes'] == 1
            assert systemd_monitor.SERVICE_STATES[self.service_name]['stops'] == 1
            assert systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] == 'failed'
            mock_save.assert_called_once()
            mock_error.assert_called()
            assert '**CRASH**' in str(mock_error.call_args)

    def test_restart_cycle_detection(self):
        """Test detection of active -> activating (restart) transition."""
        # Set initial state to active
        systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] = 'active'

        changed = {
            'ActiveState': 'activating',
            'SubState': 'auto-restart',
            'ExecMainStatus': 0,
            'ExecMainCode': 0,
            'StateChangeTimestamp': 1640000000000000
        }

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.LOGGER, 'info'):
            systemd_monitor.handle_properties_changed(
                self.service_name, None, changed, None
            )

            # Restart cycle counts both a stop and a start
            assert systemd_monitor.SERVICE_STATES[self.service_name]['starts'] == 1
            assert systemd_monitor.SERVICE_STATES[self.service_name]['stops'] == 1
            mock_save.assert_called_once()

    def test_no_change_ignored(self):
        """Test that duplicate state changes are ignored."""
        # Set initial state to active
        systemd_monitor.SERVICE_STATES[self.service_name]['last_state'] = 'active'

        changed = {
            'ActiveState': 'active',
            'SubState': 'running',
            'ExecMainStatus': 0,
            'ExecMainCode': 0,
            'StateChangeTimestamp': 1640000000000000
        }

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.LOGGER, 'info'):
            systemd_monitor.handle_properties_changed(
                self.service_name, None, changed, None
            )

            # No counters should change
            assert systemd_monitor.SERVICE_STATES[self.service_name]['starts'] == 0
            assert systemd_monitor.SERVICE_STATES[self.service_name]['stops'] == 0
            # save_state should not be called since no counters changed
            mock_save.assert_not_called()


class TestSetupDBusMonitor:
    """Test D-Bus monitoring setup."""

    def test_setup_loads_state(self):
        """Test that setup_dbus_monitor loads persistent state."""
        with patch('systemd_monitor.systemd_monitor.load_state') as mock_load, \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Subscribe'), \
             patch('systemd_monitor.systemd_monitor._get_initial_service_properties',
                   return_value=None):
            result = systemd_monitor.setup_dbus_monitor()
            mock_load.assert_called_once()
            assert result is False  # False means no error

    def test_setup_subscribes_to_dbus(self):
        """Test that setup_dbus_monitor subscribes to D-Bus signals."""
        with patch('systemd_monitor.systemd_monitor.load_state'), \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Subscribe') as mock_sub, \
             patch('systemd_monitor.systemd_monitor._get_initial_service_properties',
                   return_value=None):
            systemd_monitor.setup_dbus_monitor()
            mock_sub.assert_called_once()

    def test_setup_handles_dbus_exception(self):
        """Test that setup_dbus_monitor handles D-Bus exceptions."""
        import dbus as dbus_module  # Import locally to avoid name conflict
        with patch('systemd_monitor.systemd_monitor.load_state'), \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Subscribe',
                         side_effect=dbus_module.exceptions.DBusException("Connection failed")), \
             patch.object(systemd_monitor.LOGGER, 'error') as mock_error:
            result = systemd_monitor.setup_dbus_monitor()
            assert result is True  # True means error occurred
            mock_error.assert_called()


class TestGetInitialServiceProperties:
    """Test initial service properties retrieval."""

    def test_get_properties_success(self):
        """Test successful property retrieval."""
        mock_unit_obj = MagicMock()
        mock_props_interface = MagicMock()

        # Set up return values for property gets
        mock_props_interface.Get.side_effect = [
            'active',  # ActiveState
            'running',  # SubState
            0,  # ExecMainStatus
            0,  # ExecMainCode
            1640000000000000  # StateChangeTimestamp
        ]

        with patch.object(systemd_monitor.MANAGER_INTERFACE, 'GetUnit',
                         return_value='/org/freedesktop/systemd1/unit/test'), \
             patch.object(systemd_monitor.SYSTEM_BUS, 'get_object',
                         return_value=mock_unit_obj), \
             patch('dbus.Interface', return_value=mock_props_interface):
            result = systemd_monitor._get_initial_service_properties('test.service')

            assert result is not None
            assert result['ActiveState'] == 'active'
            assert result['SubState'] == 'running'
            assert result['ExecMainStatus'] == 0
            assert result['ExecMainCode'] == 0
            assert result['StateChangeTimestamp'] == 1640000000000000

    def test_get_properties_handles_exception(self):
        """Test that _get_initial_service_properties handles exceptions."""
        import dbus as dbus_module  # Import locally to avoid name conflict
        with patch.object(systemd_monitor.MANAGER_INTERFACE, 'GetUnit',
                         side_effect=dbus_module.exceptions.DBusException("Unit not found")):
            result = systemd_monitor._get_initial_service_properties('test.service')
            assert result is None


class TestSignalHandler:
    """Test signal handler function."""

    def test_signal_handler_saves_state(self):
        """Test that signal handler saves state before exiting."""
        mock_loop = MagicMock()

        with patch('systemd_monitor.systemd_monitor.save_state') as mock_save, \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Unsubscribe'), \
             patch.object(systemd_monitor.SYSTEM_BUS, 'close'), \
             patch('sys.exit'):
            systemd_monitor.signal_handler(signal.SIGTERM, None, mock_loop)
            mock_save.assert_called_once()
            mock_loop.quit.assert_called_once()

    def test_signal_handler_unsubscribes(self):
        """Test that signal handler unsubscribes from D-Bus."""
        mock_loop = MagicMock()

        with patch('systemd_monitor.systemd_monitor.save_state'), \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Unsubscribe') as mock_unsub, \
             patch.object(systemd_monitor.SYSTEM_BUS, 'close'), \
             patch('sys.exit'):
            systemd_monitor.signal_handler(signal.SIGTERM, None, mock_loop)
            mock_unsub.assert_called_once()

    def test_signal_handler_handles_unsub_error(self):
        """Test that signal handler handles unsubscribe errors gracefully."""
        import dbus as dbus_module  # Import locally to avoid name conflict
        mock_loop = MagicMock()

        with patch('systemd_monitor.systemd_monitor.save_state'), \
             patch.object(systemd_monitor.MANAGER_INTERFACE, 'Unsubscribe',
                         side_effect=dbus_module.exceptions.DBusException("Error")), \
             patch.object(systemd_monitor.SYSTEM_BUS, 'close'), \
             patch.object(systemd_monitor.LOGGER, 'warning') as mock_warn, \
             patch('sys.exit'):
            systemd_monitor.signal_handler(signal.SIGTERM, None, mock_loop)
            mock_warn.assert_called()


class TestConstants:
    """Test module constants."""

    def test_monitored_services_is_list(self):
        """Test that MONITORED_SERVICES is a non-empty list."""
        assert isinstance(systemd_monitor.MONITORED_SERVICES, list)
        assert len(systemd_monitor.MONITORED_SERVICES) > 0

    def test_monitored_services_are_strings(self):
        """Test that all monitored services are strings ending with .service."""
        for service in systemd_monitor.MONITORED_SERVICES:
            assert isinstance(service, str)
            assert service.endswith('.service')

    def test_signal_names_mapping(self):
        """Test that SIGNAL_NAMES contains expected signals."""
        assert isinstance(systemd_monitor.SIGNAL_NAMES, dict)
        # Common signals should be present
        assert signal.SIGTERM in systemd_monitor.SIGNAL_NAMES
        assert signal.SIGINT in systemd_monitor.SIGNAL_NAMES
        # Should not include SIG_ prefixed names
        for name in systemd_monitor.SIGNAL_NAMES.values():
            assert not name.startswith('SIG_')

    def test_persistence_file_path(self):
        """Test that PERSISTENCE_FILE has correct path."""
        assert systemd_monitor.PERSISTENCE_FILE == os.path.join(
            systemd_monitor.PERSISTENCE_DIR,
            systemd_monitor.PERSISTENCE_FILENAME
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
