"""
Service Monitor for systemd units.

This script monitors a predefined list of systemd services using D-Bus,
logging their state changes, starts, stops, and crashes to a file.
It uses pure Python Jeepney library for D-Bus communication (no C compiler required).
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
import threading
from typing import Dict, Any, Optional, List

# Use pure-Python Jeepney for D-Bus (no C compiler required)
from systemd_monitor import dbus_shim as dbus  # type: ignore

from systemd_monitor.config import Config
from systemd_monitor import __version__
from systemd_monitor.prometheus_metrics import get_metrics

# Configuration will be loaded from Config module
# These are module-level variables that will be set by initialize_from_config()
MONITORED_SERVICES = []  # pylint: disable=invalid-name
PERSISTENCE_DIR = "/var/lib/service_monitor"
PERSISTENCE_FILENAME = "service_states.json"
PERSISTENCE_FILE = os.path.join(PERSISTENCE_DIR, PERSISTENCE_FILENAME)

# Calculate max service name length for consistent padding
# Will be set after MONITORED_SERVICES is loaded
MAX_SERVICE_NAME_LEN = 30  # Default, will be recalculated
MAX_STATE_NAME_LEN = 12  # "deactivating" is 12 chars, "activating" 10, "inactive" 8

# D-Bus service and object path constants
SYSTEMD_DBUS_SERVICE = "org.freedesktop.systemd1"
SYSTEMD_DBUS_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
SYSTEMD_UNIT_INTERFACE = "org.freedesktop.systemd1.Unit"
SYSTEMD_SERVICE_INTERFACE = "org.freedesktop.systemd1.Service"
SYSTEMD_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"

# Global shutdown event for graceful termination
SHUTDOWN_EVENT = threading.Event()

# Initialize D-Bus connection
SYSTEM_BUS = dbus.SystemBus()
SYSTEMD_OBJECT = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, SYSTEMD_DBUS_PATH)
MANAGER_INTERFACE = dbus.Interface(SYSTEMD_OBJECT, SYSTEMD_MANAGER_INTERFACE)

# Dictionary to store service states (will be loaded from file)
# Includes 'logged_unloaded' flag for initial warning suppression
SERVICE_STATES = {}

# Mapping of signal numbers to their names
SIGNAL_NAMES = {
    num: name
    for name, num in signal.__dict__.items()
    if name.startswith("SIG") and not name.startswith("SIG_")
}

# --- Setup logging at module level with default log file ---
LOGGER = logging.getLogger("ServiceMonitor")
LOGGER.setLevel(logging.INFO)
# Using /tmp for default log is acceptable as it's overridable via --log-file
DEFAULT_LOG_FILE = "/tmp/service_monitor.log"  # nosec B108
file_handler = RotatingFileHandler(
    DEFAULT_LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=3
)
file_handler.setLevel(logging.INFO)
FORMATTER = logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
file_handler.setFormatter(FORMATTER)
LOGGER.addHandler(file_handler)
# --- End logging setup ---


def save_state() -> None:
    """
    Saves the current SERVICE_STATES dictionary to a JSON file for persistence.
    """
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)
    try:
        serializable_states = {}
        for service, data in SERVICE_STATES.items():
            serializable_states[service] = {
                "last_state": data["last_state"],
                "last_change_time": data["last_change_time"],
                "starts": data["starts"],
                "stops": data["stops"],
                "crashes": data["crashes"],
                "logged_unloaded": data.get(
                    "logged_unloaded", False
                ),  # Ensure this key exists
            }

        with open(PERSISTENCE_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable_states, f, indent=4)
        LOGGER.debug("Service states saved to %s", PERSISTENCE_FILE)
    except IOError as e:
        LOGGER.exception("Error saving service states to %s: %s", PERSISTENCE_FILE, e)
    except TypeError as e:
        LOGGER.exception("Error serializing service states (check data types): %s", e)


def load_state() -> None:
    """
    Loads service states from a JSON file.
    Initializes missing services or counters to default values.
    """
    global SERVICE_STATES  # pylint: disable=global-statement
    if not os.path.exists(PERSISTENCE_FILE):
        LOGGER.info(
            "Persistence file not found: %s. Initializing new states.", PERSISTENCE_FILE
        )
        # Initialize all services to default if no file exists
        SERVICE_STATES = {
            service: {
                "last_state": None,
                "last_change_time": None,
                "starts": 0,
                "stops": 0,
                "crashes": 0,
                "logged_unloaded": False,
            }
            for service in MONITORED_SERVICES
        }
        return

    try:
        with open(PERSISTENCE_FILE, "r", encoding="utf-8") as f:
            loaded_states = json.load(f)
        LOGGER.info("Service states loaded from %s", PERSISTENCE_FILE)

        # Merge loaded states with MONITORED_SERVICES, initializing new services
        for service in MONITORED_SERVICES:
            if service in loaded_states:
                SERVICE_STATES[service] = {
                    "last_state": loaded_states[service].get("last_state"),
                    "last_change_time": loaded_states[service].get("last_change_time"),
                    "starts": loaded_states[service].get("starts", 0),
                    "stops": loaded_states[service].get("stops", 0),
                    "crashes": loaded_states[service].get("crashes", 0),
                    "logged_unloaded": loaded_states[service].get(
                        "logged_unloaded", False
                    ),
                }
            else:
                # New service not in persistence file, initialize to default
                SERVICE_STATES[service] = {
                    "last_state": None,
                    "last_change_time": None,
                    "starts": 0,
                    "stops": 0,
                    "crashes": 0,
                    "logged_unloaded": False,
                }

        # Remove any services from SERVICE_STATES that are no longer in MONITORED_SERVICES
        services_to_remove = [s for s in SERVICE_STATES if s not in MONITORED_SERVICES]
        for service in services_to_remove:
            del SERVICE_STATES[service]
            LOGGER.info("Removed unmonitored service from state: %s", service)

    except (IOError, json.JSONDecodeError) as e:
        LOGGER.exception(
            "Error loading service states from %s: %s. Initializing with default states.",
            PERSISTENCE_FILE,
            e,
        )
        # Fallback to default if load fails
        SERVICE_STATES = {
            service: {
                "last_state": None,
                "last_change_time": None,
                "starts": 0,
                "stops": 0,
                "crashes": 0,
                "logged_unloaded": False,
            }
            for service in MONITORED_SERVICES
        }


def handle_properties_changed(  # pylint: disable=too-many-statements
    service_name: str, _interface: str, changed: Dict[str, Any], _invalidated: List[str]
) -> None:
    """
    Handle PropertiesChanged signal to detect service state changes and crashes,
    and update persistent counters.
    """
    current_active_state = str(
        changed.get("ActiveState", SERVICE_STATES[service_name]["last_state"])
    )
    current_sub_state = str(changed.get("SubState", "unknown"))
    current_exec_main_status = int(changed.get("ExecMainStatus", 0))
    current_exec_main_code = int(changed.get("ExecMainCode", 0))
    current_last_change_time = int(
        changed.get("StateChangeTimestamp", int(time.time() * 1000000))
    )

    last_state_info = SERVICE_STATES[service_name]
    last_active_state = last_state_info["last_state"]

    # Important: Do not process if ActiveState hasn't changed, unless it's the very first time.
    if current_active_state == last_active_state and last_active_state is not None:
        return

    # Prepare status meaning for crashes
    status_meaning = (
        SIGNAL_NAMES.get(current_exec_main_status, f"signal {current_exec_main_status}")
        if current_exec_main_code == 2
        else current_exec_main_status
    )

    log_message = ""
    counter_changed = False  # Flag to indicate if counters were modified

    # Define state categories for clearer logic.
    # 'deactivating' is a transient state that leads to a stop, so we consider it
    # as part of the "non-stopped" state for counting a stop *transition*.
    running_like_states = ["active", "activating", "reloading", "deactivating"]
    # 'unloaded' for initial state or if unit completely goes away
    stopped_like_states = ["inactive", "failed", "dead", "unloaded"]

    # --- Logic for state transitions and counter updates ---

    # 1. Detect a START
    # Transition from a 'stopped-like' state (or None) to a 'running-like' state.
    # Exclude 'deactivating' as a target for a START.
    if (last_active_state in stopped_like_states or last_active_state is None) and (
        current_active_state in ["activating", "active", "reloading"]
    ):
        last_state_info["starts"] += 1
        counter_changed = True
        log_message = (
            "Service %s: %s -> %s (START) - Starts: %d, Stops: %d, Crashes: %d",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            (last_active_state if last_active_state else "None").ljust(
                MAX_STATE_NAME_LEN
            ),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            last_state_info["starts"],
            last_state_info["stops"],
            last_state_info["crashes"],
        )
        LOGGER.info(*log_message)
        # Update Prometheus metrics
        get_metrics().increment_starts(service_name)

    # 2. Detect a STOP or CRASH
    # Transition from a 'running-like' state to a 'stopped-like' state.
    elif (last_active_state in running_like_states) and (
        current_active_state in stopped_like_states
    ):
        last_state_info["stops"] += 1
        counter_changed = True
        # Update Prometheus stop counter
        get_metrics().increment_stops(service_name)
        if current_active_state == "failed":
            last_state_info["crashes"] += 1
            log_message = (
                "Service %s: %s -> %s (**CRASH**)! SubState: %s, Status: %s, Code: %d. "
                "Crashes: %d, Starts: %d, Stops: %d",
                service_name.ljust(MAX_SERVICE_NAME_LEN),
                last_active_state.ljust(MAX_STATE_NAME_LEN),
                current_active_state.ljust(MAX_STATE_NAME_LEN),
                current_sub_state,
                status_meaning,
                current_exec_main_code,
                last_state_info["crashes"],
                last_state_info["starts"],
                last_state_info["stops"],
            )
            LOGGER.error(*log_message)
            # Update Prometheus crash counter
            get_metrics().increment_crashes(service_name)
        else:  # It's a clean stop (inactive, dead)
            log_message = (
                "Service %s: %s -> %s (STOP) - Starts: %d, Stops: %d, Crashes: %d",
                service_name.ljust(MAX_SERVICE_NAME_LEN),
                last_active_state.ljust(MAX_STATE_NAME_LEN),
                current_active_state.ljust(MAX_STATE_NAME_LEN),
                last_state_info["starts"],
                last_state_info["stops"],
                last_state_info["crashes"],
            )
            LOGGER.info(*log_message)

    # 3. Handle specific transitions for clarity, without affecting counters if already handled
    elif last_active_state == "active" and current_active_state == "deactivating":
        log_message = (
            "Service %s: %s -> %s (SubState: %s)",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            last_active_state.ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            current_sub_state,
        )
        LOGGER.info(*log_message)
    elif last_active_state == "active" and current_active_state == "activating":
        last_state_info["stops"] += 1
        last_state_info["starts"] += 1
        counter_changed = True
        log_message = (
            "Service %s: %s -> %s (RESTART_CYCLE) - Starts: %d, Stops: %d, Crashes: %d",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            last_active_state.ljust(MAX_STATE_NAME_LEN),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            last_state_info["starts"],
            last_state_info["stops"],
            last_state_info["crashes"],
        )
        LOGGER.info(*log_message)
        # Update Prometheus restart counter
        get_metrics().increment_restarts(service_name)
        get_metrics().increment_stops(service_name)
        get_metrics().increment_starts(service_name)
    else:
        log_message = (
            "Service %s: %s -> %s (SubState: %s)",
            service_name.ljust(MAX_SERVICE_NAME_LEN),
            (last_active_state if last_active_state else "None").ljust(
                MAX_STATE_NAME_LEN
            ),
            current_active_state.ljust(MAX_STATE_NAME_LEN),
            current_sub_state,
        )
        LOGGER.info(*log_message)

    # --- End Logic for state transitions and counter updates ---

    # Always update last_state after processing
    last_state_info["last_state"] = current_active_state
    last_state_info["last_change_time"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(current_last_change_time / 1000000)
    )
    # Reset logged_unloaded flag if service is now in an active state
    if current_active_state in ["active", "activating", "reloading"]:
        last_state_info["logged_unloaded"] = False

    # Always update Prometheus state gauge and timestamp (even if counters didn't change)
    get_metrics().update_service_state(
        service_name, current_active_state, current_last_change_time / 1000000
    )

    # Save state if counters were changed
    if counter_changed:
        save_state()


# pylint: disable=too-many-statements,too-many-branches
def setup_dbus_monitor() -> bool:  # noqa: C901
    """
    Set up D-Bus signal monitoring for service state changes.

    Loads persistent states, then initializes current states for all monitored services
    by polling once, and finally subscribes to D-Bus PropertiesChanged signals for each service.

    Returns:
        bool: True if D-Bus monitoring setup failed, False otherwise.
    """
    LOGGER.debug("Setting up D-Bus monitoring for %d services", len(MONITORED_SERVICES))

    # Load persistent states first
    load_state()
    LOGGER.debug("Loaded persistent state for %d services", len(SERVICE_STATES))

    try:
        # First, ensure systemd will emit signals to us
        LOGGER.debug("About to call MANAGER_INTERFACE.Subscribe()...")
        MANAGER_INTERFACE.Subscribe()
        LOGGER.info("Successfully subscribed to systemd D-Bus signals.")

        # Initial logging of service states
        LOGGER.debug(
            "Fetching initial service states for %d services...",
            len(MONITORED_SERVICES),
        )
        for service_name in MONITORED_SERVICES:
            LOGGER.debug("Fetching initial state for %s", service_name)
            current_props = _get_initial_service_properties(service_name)
            if current_props:
                if (
                    SERVICE_STATES[service_name]["last_state"]
                    != current_props["ActiveState"]
                    or SERVICE_STATES[service_name]["last_state"] is None
                ):
                    last_state = SERVICE_STATES[service_name]["last_state"]
                    last_state_str = last_state if last_state else "None"
                    log_message = (
                        "Initial state for %s: %s -> %s (SubState: %s)",
                        service_name.ljust(MAX_SERVICE_NAME_LEN),
                        last_state_str.ljust(MAX_STATE_NAME_LEN),
                        current_props["ActiveState"].ljust(MAX_STATE_NAME_LEN),
                        current_props["SubState"],
                    )
                    LOGGER.info(*log_message)
                else:
                    log_message = (
                        "Initial state for %s: %s (SubState: %s)",
                        service_name.ljust(MAX_SERVICE_NAME_LEN),
                        current_props["ActiveState"].ljust(MAX_STATE_NAME_LEN),
                        current_props["SubState"],
                    )
                    LOGGER.info(*log_message)

                SERVICE_STATES[service_name]["last_state"] = current_props[
                    "ActiveState"
                ]
                SERVICE_STATES[service_name]["last_change_time"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(current_props["StateChangeTimestamp"] / 1000000),
                )
                SERVICE_STATES[service_name]["logged_unloaded"] = False

            else:
                if not SERVICE_STATES[service_name].get("logged_unloaded", False):
                    LOGGER.warning(
                        "Service %s not loaded or accessible at startup. "
                        "Marking as 'unloaded'.",
                        service_name.ljust(MAX_SERVICE_NAME_LEN),
                    )
                    SERVICE_STATES[service_name]["logged_unloaded"] = True
                SERVICE_STATES[service_name]["last_state"] = "unloaded"

        # Initialize Prometheus gauges from loaded state
        metrics = get_metrics()
        if metrics.enabled:
            for service_name in MONITORED_SERVICES:
                state = SERVICE_STATES[service_name]["last_state"]
                # Use current time for initial timestamp
                # (since we don't have exact microsecond time)
                timestamp = time.time()
                metrics.update_service_state(service_name, state, timestamp)
                LOGGER.debug(
                    "Initialized Prometheus gauge for %s: state=%s",
                    service_name,
                    state,
                )

        LOGGER.debug(
            "Setting up signal subscriptions for %d services...",
            len(MONITORED_SERVICES),
        )
        for service_name in MONITORED_SERVICES:
            try:
                LOGGER.debug("Subscribing to PropertiesChanged for %s", service_name)
                unit_path = MANAGER_INTERFACE.GetUnit(service_name)
                LOGGER.debug("Got unit path for %s: %s", service_name, unit_path)

                # Check if GetUnit returned a valid path or an error message
                if not isinstance(unit_path, str) or not unit_path.startswith("/"):
                    LOGGER.warning(
                        "Service %s not loaded or accessible: %s",
                        service_name,
                        unit_path,
                    )
                    continue

                unit_obj = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, str(unit_path))
                LOGGER.debug("Got unit object for %s", service_name)
                unit_obj.connect_to_signal(
                    "PropertiesChanged",
                    lambda interface, changed, invalidated, s=service_name: (
                        handle_properties_changed(s, interface, changed, invalidated)
                    ),
                    dbus_interface=SYSTEMD_PROPERTIES_INTERFACE,
                )
                LOGGER.info(
                    "Subscribed to PropertiesChanged for %s",
                    service_name.ljust(MAX_SERVICE_NAME_LEN),
                )
            except dbus.exceptions.DBusException as exc:
                LOGGER.warning(
                    "Could not subscribe to %s: %s",
                    service_name.ljust(MAX_SERVICE_NAME_LEN),
                    exc,
                )

    except dbus.exceptions.DBusException as exc:
        LOGGER.exception("Failed to set up D-Bus monitoring: %s", exc)
        LOGGER.error("Exception type: %s", type(exc).__name__)
        LOGGER.error(
            "This may indicate:\n"
            "  - D-Bus service is not running (check: systemctl status dbus)\n"
            "  - Insufficient permissions (try running as root)\n"
            "  - systemd is not available on this system"
        )
        print(f"ERROR: D-Bus connection failed: {exc}", file=sys.stderr)
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad to catch any unexpected errors during setup
        LOGGER.exception("Unexpected error during D-Bus setup: %s", exc)
        LOGGER.error("Exception type: %s", type(exc).__name__)
        import traceback  # pylint: disable=import-outside-toplevel

        LOGGER.error("Traceback:\n%s", traceback.format_exc())
        print(f"ERROR: Unexpected error: {exc}", file=sys.stderr)
        return True

    LOGGER.info(
        "D-Bus monitoring setup completed successfully - ready to receive signals"
    )
    return False


def _get_initial_service_properties(service_name: str) -> Optional[Dict[str, Any]]:
    """
    Helper to fetch initial properties for a service.
    """
    try:
        unit_path = MANAGER_INTERFACE.GetUnit(service_name)

        # Check if GetUnit returned a valid path or an error message
        if not isinstance(unit_path, str) or not unit_path.startswith("/"):
            LOGGER.warning(
                "Service %s not loaded or accessible: %s", service_name, unit_path
            )
            return None

        unit_obj = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, str(unit_path))
        unit_props = dbus.Interface(unit_obj, SYSTEMD_PROPERTIES_INTERFACE)

        active_state = unit_props.Get(SYSTEMD_UNIT_INTERFACE, "ActiveState")
        sub_state = unit_props.Get(SYSTEMD_UNIT_INTERFACE, "SubState")
        exec_main_status = unit_props.Get(SYSTEMD_SERVICE_INTERFACE, "ExecMainStatus")
        exec_main_code = unit_props.Get(SYSTEMD_SERVICE_INTERFACE, "ExecMainCode")
        state_change_timestamp = unit_props.Get(
            SYSTEMD_UNIT_INTERFACE, "StateChangeTimestamp"
        )

        return {
            "ActiveState": str(active_state),
            "SubState": str(sub_state),
            "ExecMainStatus": int(exec_main_status),
            "ExecMainCode": int(exec_main_code),
            "StateChangeTimestamp": int(state_change_timestamp),
        }
    except dbus.exceptions.DBusException as exc:
        LOGGER.exception("Failed to set up D-Bus monitoring: %s", exc)
        LOGGER.error("Exception type: %s", type(exc).__name__)
        return None


def initialize_from_config(config: Config) -> None:
    """
    Initialize module-level variables from Config object.
    """
    global MONITORED_SERVICES, MAX_SERVICE_NAME_LEN  # pylint: disable=global-statement

    MONITORED_SERVICES = list(config.monitored_services)

    # Recalculate max service name length
    if MONITORED_SERVICES:
        MAX_SERVICE_NAME_LEN = max(len(s) for s in MONITORED_SERVICES)
    else:
        MAX_SERVICE_NAME_LEN = 30  # Default if no services

    LOGGER.info("Initialized with %d monitored services", len(MONITORED_SERVICES))


def signal_handler(_sig: int, _frame: Any) -> None:
    """
    Handle termination signals with cleanup. Saves state before exiting.
    """
    print("\nTerminating gracefully...")
    # Save state before quitting
    save_state()
    try:
        MANAGER_INTERFACE.Unsubscribe()  # Unsubscribe from global systemd signals
        LOGGER.info("Successfully unsubscribed from systemd D-Bus signals.")
    except dbus.exceptions.DBusException as exc:
        LOGGER.exception("Failed to unsubscribe from D-Bus: %s", exc)
    try:
        SYSTEM_BUS.close()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOGGER.exception("Failed to close D-Bus connection: %s", exc)

    # Ensure logs are flushed before exiting
    for handler in LOGGER.handlers:
        handler.flush()

    # Signal the main thread to exit
    SHUTDOWN_EVENT.set()
    sys.exit(0)


def _print_help(log_file_path: str) -> None:
    """Print help message with monitored services."""
    print("\nService Monitor for systemd units\n")
    print("Monitored services:")
    for svc in MONITORED_SERVICES:
        print(f"  - {svc}")
    print(f"\nMonitoring results are logged to: {log_file_path}")
    print(f"Persistence file is located at: {PERSISTENCE_FILE}")
    print("\nUsage:")
    print("  -h, --help                Show this help message and monitored services")
    print("  -v, --version             Show module version")
    print("  -c, --clear               Clear history log and persistence file")
    print("  --config FILE             Path to JSON configuration file")
    print("  --services SERVICE [...]  List of services to monitor")
    print("  -l, --log-file FILE       Path to the monitoring log file")
    print("  -p, --persistence-file FILE Path to the persistence file")
    print("  --debug                   Enable debug logging")


def _clear_files(log_file: Optional[str], persistence_file: Optional[str]) -> None:
    """Clear log file and persistence file if they exist."""
    if log_file and os.path.exists(log_file):
        os.remove(log_file)
        print(f"Removed log file: {log_file}")
    if persistence_file and os.path.exists(persistence_file):
        os.remove(persistence_file)
        print(f"Removed persistence file: {persistence_file}")


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Monitor systemd services.", add_help=False
    )
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="Show help message and monitored services",
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show module version"
    )
    parser.add_argument(
        "-c",
        "--clear",
        action="store_true",
        help="Clear history log and persistence file",
    )
    parser.add_argument("--config", type=str, help="Path to JSON configuration file")
    parser.add_argument(
        "--services",
        nargs="+",
        help="List of services to monitor (overrides config file)",
    )
    parser.add_argument(
        "-l", "--log-file", default=None, help="Path to the monitoring log file"
    )
    parser.add_argument(
        "-p", "--persistence-file", default=None, help="Path to the persistence file"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def _setup_logging(log_file_path: str, debug: bool) -> None:
    """Configure logging handlers and levels."""
    if log_file_path != DEFAULT_LOG_FILE:
        LOGGER.removeHandler(file_handler)
        new_file_handler = RotatingFileHandler(
            log_file_path, maxBytes=1 * 1024 * 1024, backupCount=3
        )
        new_file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        new_file_handler.setFormatter(FORMATTER)
        LOGGER.addHandler(new_file_handler)

    if debug:
        LOGGER.setLevel(logging.DEBUG)


def _handle_command_actions(
    args: argparse.Namespace, log_file_path: str
) -> bool:  # noqa: C901
    """
    Handle command-line actions (help, version, clear).

    Returns:
        bool: True if an action was performed and program should exit.
    """
    if args.help:
        _print_help(log_file_path)
        sys.exit(0)

    if args.version:
        print(f"systemd-monitor version: {__version__}")
        sys.exit(0)

    if args.clear:
        _clear_files(args.log_file, args.persistence_file)
        sys.exit(0)

    return False


def _initialize_prometheus(app_config: Config) -> None:
    """Initialize Prometheus metrics if enabled."""
    if not app_config.prometheus_enabled:
        LOGGER.info("Prometheus metrics disabled by configuration")
        return

    metrics = get_metrics()
    if not metrics.enabled:
        LOGGER.info("Prometheus client not available, metrics disabled")
        return

    if metrics.start_http_server(app_config.prometheus_port):
        LOGGER.info("Prometheus metrics enabled on port %d", app_config.prometheus_port)
        metrics.set_monitor_info(__version__, MONITORED_SERVICES)
    else:
        LOGGER.warning("Failed to start Prometheus HTTP server")


def _validate_services_configured() -> None:
    """Check that services are configured, exit with error if not."""
    if MONITORED_SERVICES:
        return

    error_msg = (
        "ERROR: No services configured for monitoring!\n"
        "Please specify services using:\n"
        "  --services SERVICE1,SERVICE2,...\n"
        "Or create a config file with 'monitored_services' list.\n"
        "Example: systemd-monitor --services sshd.service,cron.service"
    )
    print(error_msg, file=sys.stderr)
    LOGGER.error("No services configured for monitoring")
    for handler in LOGGER.handlers:
        handler.flush()
    sys.exit(1)


def _start_monitoring(log_file_path: str) -> None:
    """Start D-Bus monitoring or exit with error."""
    LOGGER.info("Starting D-Bus monitoring for %d services...", len(MONITORED_SERVICES))
    LOGGER.debug("Services: %s", ", ".join(MONITORED_SERVICES))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if setup_dbus_monitor():
        error_msg = (
            "ERROR: D-Bus monitoring setup failed!\n"
            f"Check {log_file_path} for details."
        )
        print(error_msg, file=sys.stderr)
        LOGGER.error("D-Bus monitoring setup failed. Exiting.")
        for handler in LOGGER.handlers:
            handler.flush()
        sys.exit(1)

    LOGGER.info("D-Bus monitoring active. Press Ctrl+C to stop.")
    print(
        f"Monitoring {len(MONITORED_SERVICES)} services. Press Ctrl+C to stop.",
        file=sys.stderr,
    )


def main() -> None:
    """Main entry point for the systemd monitor."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    # Initialize configuration
    config_kwargs = {}
    if args.debug:
        config_kwargs["debug"] = True
    if args.log_file:
        config_kwargs["log_file"] = args.log_file
    if args.services:
        config_kwargs["monitored_services"] = args.services

    app_config = Config(config_file=args.config, **config_kwargs)
    initialize_from_config(app_config)

    log_file_path = args.log_file if args.log_file else app_config.log_file
    _setup_logging(log_file_path, app_config.debug)

    _initialize_prometheus(app_config)

    if args.persistence_file:
        globals()["PERSISTENCE_FILE"] = args.persistence_file

    _handle_command_actions(args, log_file_path)
    _validate_services_configured()
    _start_monitoring(log_file_path)

    # Block main thread until shutdown event is set
    # The Jeepney event loop runs in a background thread
    try:
        SHUTDOWN_EVENT.wait()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
