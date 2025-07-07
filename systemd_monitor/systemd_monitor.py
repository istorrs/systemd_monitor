"""
Service Monitor for systemd units.

This script monitors a predefined list of systemd services using D-Bus,
logging their state changes, starts, stops, and crashes to a file.
It uses GLib.MainLoop for event handling and argparse for command-line
argument parsing.
Counters for starts, stops, and crashes are persisted across script runs
using a JSON file.
"""

import time
import logging
from logging.handlers import RotatingFileHandler
import argparse
import signal
import sys
import json
import os
from functools import partial # Used for signal_handler binding

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

__git_tag__ = "manual_version"

# Set up DBusGMainLoop globally before any D-Bus interaction
DBusGMainLoop(set_as_default=True)

# List of services to monitor
MONITORED_SERVICES = [
    'wirepas-gateway.service',
    'wirepas-sink-ttys1.service',
    'wirepas-sink-ttys2.service',
    'edger.connecteddev.service',
    'edger.endries.service',
    'devmgmt.service',
    'hwcheck.service',
    'provisioning.service',
    'Node-Configuration.service',
    'setup_cell_connect.service',
    'mosquitto.service',
    'wps_button_monitor.service',
]

# Path for persistence file
PERSISTENCE_DIR = '/var/lib/service_monitor'
PERSISTENCE_FILENAME = 'service_states.json'
PERSISTENCE_FILE = os.path.join(PERSISTENCE_DIR, PERSISTENCE_FILENAME)

# Calculate max service name length for consistent padding
MAX_SERVICE_NAME_LEN = max(len(s) for s in MONITORED_SERVICES)
MAX_STATE_NAME_LEN = 12 # "deactivating" is 12 chars, "activating" 10, "inactive" 8

# D-Bus service and object path constants
SYSTEMD_DBUS_SERVICE = 'org.freedesktop.systemd1'
SYSTEMD_DBUS_PATH = '/org/freedesktop/systemd1'
SYSTEMD_MANAGER_INTERFACE = 'org.freedesktop.systemd1.Manager'
SYSTEMD_UNIT_INTERFACE = 'org.freedesktop.systemd1.Unit'
SYSTEMD_SERVICE_INTERFACE = 'org.freedesktop.systemd1.Service'
SYSTEMD_PROPERTIES_INTERFACE = 'org.freedesktop.DBus.Properties'

# Initialize D-Bus connection
SYSTEM_BUS = dbus.SystemBus()
SYSTEMD_OBJECT = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, SYSTEMD_DBUS_PATH)
MANAGER_INTERFACE = dbus.Interface(SYSTEMD_OBJECT, SYSTEMD_MANAGER_INTERFACE)

# Dictionary to store service states (will be loaded from file)
# Includes 'logged_unloaded' flag for initial warning suppression
SERVICE_STATES = {}

# Mapping of signal numbers to their names
SIGNAL_NAMES = {num: name for name, num in signal.__dict__.items()
                if name.startswith('SIG') and not name.startswith('SIG_')}

# --- Setup logging at module level with default log file ---
LOGGER = logging.getLogger('ServiceMonitor')
LOGGER.setLevel(logging.INFO)
DEFAULT_LOG_FILE = '/tmp/service_monitor.log'
FILE_HANDLER = RotatingFileHandler(DEFAULT_LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=3)
FILE_HANDLER.setLevel(logging.INFO)
FORMATTER = logging.Formatter('%(asctime)s - [%(levelname)s] %(message)s')
FILE_HANDLER.setFormatter(FORMATTER)
LOGGER.addHandler(FILE_HANDLER)
# --- End logging setup ---

def save_state():
    """
    Saves the current SERVICE_STATES dictionary to a JSON file for persistence.
    """
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)
    try:
        serializable_states = {}
        for service, data in SERVICE_STATES.items():
            serializable_states[service] = {
                'last_state': data['last_state'],
                'last_change_time': data['last_change_time'],
                'starts': data['starts'],
                'stops': data['stops'],
                'crashes': data['crashes'],
                'logged_unloaded': data.get('logged_unloaded', False) # Ensure this key exists
            }

        with open(PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(serializable_states, f, indent=4)
        LOGGER.debug("Service states saved to %s", PERSISTENCE_FILE)
    except IOError as e:
        LOGGER.error("Error saving service states to %s: %s", PERSISTENCE_FILE, e)
    except TypeError as e:
        LOGGER.error("Error serializing service states (check data types): %s", e)


def load_state():
    """
    Loads service states from a JSON file.
    Initializes missing services or counters to default values.
    """
    global SERVICE_STATES  # pylint: disable=global-statement
    if not os.path.exists(PERSISTENCE_FILE):
        LOGGER.info("Persistence file not found: %s. Initializing new states.", PERSISTENCE_FILE)
        # Initialize all services to default if no file exists
        SERVICE_STATES = {service: {'last_state': None, 'last_change_time': None, 'starts': 0,
                                    'stops': 0, 'crashes': 0, 'logged_unloaded': False}
                          for service in MONITORED_SERVICES}
        return

    try:
        with open(PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
            loaded_states = json.load(f)
        LOGGER.info("Service states loaded from %s", PERSISTENCE_FILE)

        # Merge loaded states with MONITORED_SERVICES, initializing new services
        for service in MONITORED_SERVICES:
            if service in loaded_states:
                SERVICE_STATES[service] = {
                    'last_state': loaded_states[service].get('last_state'),
                    'last_change_time': loaded_states[service].get('last_change_time'),
                    'starts': loaded_states[service].get('starts', 0),
                    'stops': loaded_states[service].get('stops', 0),
                    'crashes': loaded_states[service].get('crashes', 0),
                    'logged_unloaded': loaded_states[service].get('logged_unloaded', False)
                }
            else:
                # New service not in persistence file, initialize to default
                SERVICE_STATES[service] = {'last_state': None, 'last_change_time': None, 'starts': 0,
                                            'stops': 0, 'crashes': 0, 'logged_unloaded': False}

        # Remove any services from SERVICE_STATES that are no longer in MONITORED_SERVICES
        services_to_remove = [s for s in SERVICE_STATES if s not in MONITORED_SERVICES]
        for service in services_to_remove:
            del SERVICE_STATES[service]
            LOGGER.info("Removed unmonitored service from state: %s", service)

    except (IOError, json.JSONDecodeError) as e:
        LOGGER.error("Error loading service states from %s: %s. Initializing with default states.",
                     PERSISTENCE_FILE, e)
        # Fallback to default if load fails
        SERVICE_STATES = {service: {'last_state': None, 'last_change_time': None, 'starts': 0,
                                    'stops': 0, 'crashes': 0, 'logged_unloaded': False}
                          for service in MONITORED_SERVICES}


def handle_properties_changed(service_name, _interface, changed, _invalidated):
    """
    Handle PropertiesChanged signal to detect service state changes and crashes,
    and update persistent counters.
    """
    current_active_state = str(changed.get('ActiveState', SERVICE_STATES[service_name]['last_state']))
    current_sub_state = str(changed.get('SubState', 'unknown'))
    current_exec_main_status = int(changed.get('ExecMainStatus', 0))
    current_exec_main_code = int(changed.get('ExecMainCode', 0))
    current_last_change_time = int(changed.get('StateChangeTimestamp', int(time.time() * 1000000)))

    last_state_info = SERVICE_STATES[service_name]
    last_active_state = last_state_info['last_state']

    # Important: Do not process if ActiveState hasn't changed, unless it's the very first time.
    if current_active_state == last_active_state and last_active_state is not None:
        return

    # Prepare status meaning for crashes
    status_meaning = SIGNAL_NAMES.get(current_exec_main_status,
                                      f"signal {current_exec_main_status}") \
                                      if current_exec_main_code == 2 else \
                                      current_exec_main_status

    log_message = ""
    counter_changed = False # Flag to indicate if counters were modified

    # Define state categories for clearer logic.
    # 'deactivating' is a transient state that leads to a stop, so we consider it
    # as part of the "non-stopped" state for the purpose of counting a stop *transition*.
    running_like_states = ['active', 'activating', 'reloading', 'deactivating']
    stopped_like_states = ['inactive', 'failed', 'dead', 'unloaded'] # 'unloaded' for initial state or if unit completely goes away

    # --- Logic for state transitions and counter updates ---

    # 1. Detect a START
    # Transition from a 'stopped-like' state (or None) to a 'running-like' state.
    # Exclude 'deactivating' as a target for a START.
    if (last_active_state in stopped_like_states or last_active_state is None) and \
       (current_active_state in ['activating', 'active', 'reloading']):
        last_state_info['starts'] += 1
        counter_changed = True
        log_message = (
            "Service %s: %s -> %s (START) - Starts: %d, Stops: %d, Crashes: %d",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            (last_active_state if last_active_state else 'None').ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            last_state_info['starts'],
            last_state_info['stops'],
            last_state_info['crashes']
        )
        LOGGER.info(*log_message)

    # 2. Detect a STOP or CRASH
    # Transition from a 'running-like' state to a 'stopped-like' state.
    elif (last_active_state in running_like_states) and \
         (current_active_state in stopped_like_states):
        last_state_info['stops'] += 1
        counter_changed = True
        if current_active_state == 'failed':
            last_state_info['crashes'] += 1
            log_message = (
                "Service %s: %s -> %s (**CRASH**)! SubState: %s, Status: %s, Code: %d. "
                "Crashes: %d, Starts: %d, Stops: %d",
                service_name.ljust(MAX_SERVICE_NAME_LEN),
                last_active_state.ljust(MAX_STATE_NAME_LEN),
                current_active_state.ljust(MAX_STATE_NAME_LEN),
                current_sub_state,
                status_meaning,
                current_exec_main_code,
                last_state_info['crashes'],
                last_state_info['starts'],
                last_state_info['stops']
            )
            LOGGER.error(*log_message)
        else: # It's a clean stop (inactive, dead)
            log_message = (
                "Service %s: %s -> %s (STOP) - Starts: %d, Stops: %d, Crashes: %d",
                service_name.ljust(MAX_SERVICE_NAME_LEN),
                last_active_state.ljust(MAX_STATE_NAME_LEN),
                current_active_state.ljust(MAX_STATE_NAME_LEN),
                last_state_info['starts'],
                last_state_info['stops'],
                last_state_info['crashes']
            )
            LOGGER.info(*log_message)

    # 3. Handle specific transitions for clarity, without affecting counters if already handled
    elif last_active_state == 'active' and current_active_state == 'deactivating':
        log_message = (
            "Service %s: %s -> %s (SubState: %s)",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            last_active_state.ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            current_sub_state
        )
        LOGGER.info(*log_message)
    elif last_active_state == 'active' and current_active_state == 'activating':
        last_state_info['stops'] += 1
        last_state_info['starts'] += 1
        counter_changed = True
        log_message = (
            "Service %s: %s -> %s (RESTART_CYCLE) - Starts: %d, Stops: %d, Crashes: %d",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            last_active_state.ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            last_state_info['starts'],
            last_state_info['stops'],
            last_state_info['crashes']
        )
        LOGGER.info(*log_message)
    else:
        log_message = (
            "Service %s: %s -> %s (SubState: %s)",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            (last_active_state if last_active_state else 'None').ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            current_sub_state
        )
        LOGGER.info(*log_message)

    # --- End Logic for state transitions and counter updates ---

    # Always update last_state after processing
    last_state_info['last_state'] = current_active_state
    last_state_info['last_change_time'] = time.strftime(
        '%Y-%m-%d %H:%M:%S',
        time.localtime(current_last_change_time / 1000000)
    )
    # Reset logged_unloaded flag if service is now in an active state
    if current_active_state in ['active', 'activating', 'reloading']:
        last_state_info['logged_unloaded'] = False

    # Save state if counters were changed
    if counter_changed:
        save_state()


def setup_dbus_monitor():
    """
    Set up D-Bus signal monitoring for service state changes.

    Loads persistent states, then initializes current states for all monitored services
    by polling once, and finally subscribes to D-Bus PropertiesChanged signals for each service.

    Returns:
        bool: True if D-Bus monitoring setup failed, False otherwise.
    """
    # Load persistent states first
    load_state()

    try:
        # First, ensure systemd will emit signals to us
        MANAGER_INTERFACE.Subscribe()
        LOGGER.info("Successfully subscribed to systemd D-Bus signals.")

        # Initial logging of service states
        for service_name in MONITORED_SERVICES:
            current_props = _get_initial_service_properties(service_name)
            if current_props:
                if SERVICE_STATES[service_name]['last_state'] != current_props['ActiveState'] or \
                   SERVICE_STATES[service_name]['last_state'] is None:
                    log_message = (
                        "Initial state for %s: %s -> %s (SubState: %s)",
                        service_name.ljust(MAX_SERVICE_NAME_LEN),
                        (SERVICE_STATES[service_name]['last_state'] if SERVICE_STATES[service_name]['last_state'] else 'None').ljust(MAX_STATE_NAME_LEN),
                        current_props['ActiveState'].ljust(MAX_STATE_NAME_LEN),
                        current_props['SubState']
                    )
                    LOGGER.info(*log_message)
                else:
                    log_message = (
                        "Initial state for %s: %s (SubState: %s)",
                        service_name.ljust(MAX_SERVICE_NAME_LEN),
                        current_props['ActiveState'].ljust(MAX_STATE_NAME_LEN),
                        current_props['SubState']
                    )
                    LOGGER.info(*log_message)

                SERVICE_STATES[service_name]['last_state'] = current_props['ActiveState']
                SERVICE_STATES[service_name]['last_change_time'] = \
                    time.strftime('%Y-%m-%d %H:%M:%S',
                                  time.localtime(current_props['StateChangeTimestamp'] / 1000000))
                SERVICE_STATES[service_name]['logged_unloaded'] = False

            else:
                if not SERVICE_STATES[service_name].get('logged_unloaded', False):
                    LOGGER.warning(
                        "Service %s not loaded or accessible at startup. "
                        "Marking as 'unloaded'.",
                        service_name.ljust(MAX_SERVICE_NAME_LEN)
                    )
                    SERVICE_STATES[service_name]['logged_unloaded'] = True
                SERVICE_STATES[service_name]['last_state'] = 'unloaded'

        for service_name in MONITORED_SERVICES:
            try:
                unit_path = MANAGER_INTERFACE.GetUnit(service_name)
                unit_obj = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, str(unit_path))
                unit_obj.connect_to_signal(
                    'PropertiesChanged',
                    lambda interface, changed, invalidated, s=service_name:
                        handle_properties_changed(s, interface, changed, invalidated),
                    dbus_interface=SYSTEMD_PROPERTIES_INTERFACE
                )
                LOGGER.info("Subscribed to PropertiesChanged for %s", service_name.ljust(MAX_SERVICE_NAME_LEN))
            except dbus.exceptions.DBusException as exc:
                LOGGER.warning(
                    "Could not subscribe to %s: %s",
                    service_name.ljust(MAX_SERVICE_NAME_LEN),
                    exc
                )

    except dbus.exceptions.DBusException as exc:
        LOGGER.error(
            "Failed to set up D-Bus monitoring: %s",
            exc
        )
        return True
    return False

def _get_initial_service_properties(service_name):
    """
    Helper to fetch initial properties for a service.
    """
    try:
        unit_path = MANAGER_INTERFACE.GetUnit(service_name)
        unit_obj = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, str(unit_path))
        unit_props = dbus.Interface(unit_obj, SYSTEMD_PROPERTIES_INTERFACE)

        active_state = unit_props.Get(SYSTEMD_UNIT_INTERFACE, 'ActiveState')
        sub_state = unit_props.Get(SYSTEMD_UNIT_INTERFACE, 'SubState')
        exec_main_status = unit_props.Get(SYSTEMD_SERVICE_INTERFACE, 'ExecMainStatus')
        exec_main_code = unit_props.Get(SYSTEMD_SERVICE_INTERFACE, 'ExecMainCode')
        state_change_timestamp = unit_props.Get(SYSTEMD_UNIT_INTERFACE, 'StateChangeTimestamp')

        return {
            'ActiveState': str(active_state),
            'SubState': str(sub_state),
            'ExecMainStatus': int(exec_main_status),
            'ExecMainCode': int(exec_main_code),
            'StateChangeTimestamp': int(state_change_timestamp)
        }
    except dbus.exceptions.DBusException:
        return None


def signal_handler(_sig, _frame, main_loop):
    """
    Handle termination signals with cleanup. Saves state before exiting.
    """
    print("\nTerminating gracefully...")
    # Save state before quitting
    save_state()
    try:
        MANAGER_INTERFACE.Unsubscribe() # Unsubscribe from global systemd signals
        LOGGER.info("Successfully unsubscribed from systemd D-Bus signals.")
    except dbus.exceptions.DBusException as exc:
        LOGGER.warning("Failed to unsubscribe from D-Bus: %s", exc)
    try:
        SYSTEM_BUS.close()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOGGER.error("Failed to close D-Bus connection: %s", exc)

    # Ensure logs are flushed before exiting
    for handler in LOGGER.handlers:
        handler.flush()

    main_loop.quit()
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Monitor systemd services.',
        add_help=False
    )
    parser.add_argument('-h', '--help', action='store_true', help='Show help message and monitored services')
    parser.add_argument('-v', '--version', action='store_true', help='Show module version')
    parser.add_argument('-c', '--clear', action='store_true', help='Clear history log and persistence file')
    parser.add_argument('-l', '--log-file', default=DEFAULT_LOG_FILE, help='Path to the monitoring log file')
    parser.add_argument('-p', '--persistence-file', default=os.path.join(PERSISTENCE_DIR, PERSISTENCE_FILENAME), help='Path to the persistence file')
    ARGS = parser.parse_args()

    # If log file path is different from default, update handler
    if ARGS.log_file != DEFAULT_LOG_FILE:
        LOGGER.removeHandler(FILE_HANDLER)
        FILE_HANDLER = RotatingFileHandler(ARGS.log_file, maxBytes=1 * 1024 * 1024, backupCount=3)
        FILE_HANDLER.setLevel(logging.INFO)
        FILE_HANDLER.setFormatter(FORMATTER)
        LOGGER.addHandler(FILE_HANDLER)

    # Update global persistence file path
    globals()['PERSISTENCE_FILE'] = ARGS.persistence_file

    if ARGS.help:
        print("\nService Monitor for systemd units\n")
        print("Monitored services:")
        for svc in MONITORED_SERVICES:
            print(f"  - {svc}")
        print(f"\nMonitoring results are logged to: {ARGS.log_file}")
        print(f"Persistence file is located at: {ARGS.persistence_file}")
        print("\nUsage:")
        print("  -h, --help     Show this help message and monitored services")
        print("  -v, --version  Show module version")
        print("  -c, --clear    Clear history log and persistence file")
        print("  -l, --log-file     Path to the monitoring log file")
        print("  -p, --persistence-file Path to the persistence file")
        sys.exit(0)

    if ARGS.version:
        print(f"systemd.monitor version: {__git_tag__}")
        sys.exit(0)

    if ARGS.clear:
        # Remove log file and persistence file if they exist
        if os.path.exists(ARGS.log_file):
            os.remove(ARGS.log_file)
            print(f"Removed log file: {ARGS.log_file}")
        if os.path.exists(ARGS.persistence_file):
            os.remove(ARGS.persistence_file)
            print(f"Removed persistence file: {ARGS.persistence_file}")
        sys.exit(0)

    MAIN_LOOP = GLib.MainLoop()

    # Set up signal handlers with reference to the GLib loop
    # Using partial from functools for consistent signal handler binding
    signal.signal(signal.SIGINT, partial(signal_handler, main_loop=MAIN_LOOP))
    signal.signal(signal.SIGTERM, partial(signal_handler, main_loop=MAIN_LOOP))

    if setup_dbus_monitor():
        LOGGER.error("D-Bus monitoring setup failed. Exiting.")
        sys.exit(1)

    try:
        MAIN_LOOP.run()
    except KeyboardInterrupt:
        # KeyboardInterrupt will be caught by the signal handler, but
        # this provides a fallback for direct execution without signal trapping
        signal_handler(signal.SIGINT, None, MAIN_LOOP)
