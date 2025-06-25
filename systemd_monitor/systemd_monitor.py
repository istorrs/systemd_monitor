import signal
import sys
import threading
import logging
from collections import defaultdict
import re
import os
import time
from typing import Optional, Any, Dict, List

# Try to import D-Bus dependencies with proper error handling
try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError as e:
    print(f"Error: Required D-Bus dependencies not available: {e}")
    print("Please install: python3-dbus python3-gi gir1.2-glib-2.0")
    print("On Ubuntu/Debian: sudo apt-get install python3-dbus python3-gi gir1.2-glib-2.0")
    print("On CentOS/RHEL: sudo yum install python3-dbus python3-gobject")
    DBUS_AVAILABLE = False

from .config import Config, parse_arguments

# Set up signal handler before imports to catch Ctrl+C early
def early_signal_handler(sig: int, frame: Any) -> None:
    """Handle SIGINT (Ctrl+C) during imports or runtime."""
    print("\nShutting down...")
    sys.exit(0)

# Register signal handler immediately
signal.signal(signal.SIGINT, early_signal_handler)

def unescape_unit_name(escaped_name: Optional[str]) -> Optional[str]:
    """Convert escaped systemd unit name back to its original form."""
    if not escaped_name:
        return None
    name = escaped_name
    # Replace only _2d and _2e with - and .
    name = re.sub(r'_2d', '-', name)
    name = re.sub(r'_2e', '.', name)
    # Remove any remaining underscores (systemd escaping)
    name = name.replace('_', '')
    if not name.endswith('.service') and not name.endswith('.mount'):
        name = name + '.service'
    return name

class DBusMonitor:
    """Monitor specific systemd service state changes via D-Bus signals and polling."""
    def __init__(self, config: Config):
        self.config = config
        self.log_file = config.log_file
        self.debug = config.debug
        self.monitored_services = config.monitored_services
        self._setup_logging()
        self.loop = None
        self.running = False
        self.bus = None
        self.manager = None
        self.registered_units = set()
        self.unit_states = {}  # Track last known ActiveState
        self.unit_last_job = {}  # Track last job type for failed states
        self.subscription_attempts = {}  # Track subscription attempts
        self.unit_path_to_name = {}  # Map unit_path to service_name

    def _setup_logging(self):
        """Configure logging for D-Bus events."""
        self.logger = logging.getLogger('SystemdMonitor')
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        self.logger.handlers = []
        file_handler = logging.FileHandler(self.log_file, mode='a')
        file_handler.setLevel(logging.DEBUG if self.debug else logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        file_handler.flush = lambda: file_handler.stream.flush()
        if self.debug:
            self.logger.debug("Logging initialized for SystemdMonitor")

    def _log_event(self, service: str, state: str, substate: str, job_type: Optional[str] = None, source: str = 'signal') -> None:
        """Log service state change events."""
        if not service or service == '-' or not re.match(r'^[a-zA-Z0-9@._-]+\.?(?:service|mount)?$', service):
            if self.debug:
                self.logger.debug(f"Ignoring invalid service name: {service}")
            return
        if service not in self.monitored_services:
            if self.debug:
                self.logger.debug(f"Ignoring non-monitored service: {service}")
            return
        message = f"Service: {service}, State: {state}, SubState: {substate}, Source: {source}"
        if job_type:
            message += f", Job: {job_type}"
        self.logger.info(message)
        print(message)
        # Force flush to disk for all handlers
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
        if self.debug:
            self.logger.debug(f"Logged event: {message}")

    def _list_registered_units(self) -> None:
        """List all units registered for monitoring."""
        if not self.registered_units:
            message = "No units registered for monitoring."
        else:
            message = "Registered units for monitoring:\n" + "\n".join(sorted(self.registered_units))
        self.logger.info(message)
        print(message)

    def _get_unit_name_from_path(self, unit_path: str) -> Optional[str]:
        """Query the unit name directly from D-Bus using the unit path."""
        if not self.bus:
            return None
        try:
            unit_obj = self.bus.get_object('org.freedesktop.systemd1', unit_path)
            props = dbus.Interface(unit_obj, 'org.freedesktop.DBus.Properties')
            unit_name = props.Get('org.freedesktop.systemd1.Unit', 'Id')
            return str(unit_name)
        except dbus.exceptions.DBusException as e:
            if self.debug:
                self.logger.debug(f"Failed to get unit name for path {unit_path}: {e}")
            return None

    def _unit_properties_changed(self, interface: str, changed: Dict[str, Any], invalidated: List[str], unit_path: str) -> None:
        """Handle PropertiesChanged signal for systemd units."""
        self.logger.info(f"PropertiesChanged for unit_path {unit_path}: {changed}, invalidated={invalidated}")
        service_name = self.unit_path_to_name.get(unit_path)
        raw_service_name = unit_path.split('/')[-1]
        if not service_name:
            service_name = self._get_unit_name_from_path(unit_path) or unescape_unit_name(raw_service_name)
        if self.debug:
            self.logger.debug(f"PropertiesChanged for unit_path {unit_path}: resolved to {service_name} (raw: {raw_service_name})")
        if not service_name or service_name not in self.monitored_services:
            if self.debug:
                self.logger.debug(f"Ignoring PropertiesChanged for non-monitored service: {service_name} (unit_path: {unit_path})")
            return
        if self.debug:
            self.logger.debug(f"PropertiesChanged for {service_name}: changed={changed}, invalidated={invalidated}")
        if 'ActiveState' in changed or 'SubState' in changed:
            active_state = changed.get('ActiveState', 'unknown')
            sub_state = changed.get('SubState', 'unknown')
            self.unit_states[service_name] = active_state
            self._log_event(service_name, active_state, sub_state, source='PropertiesChanged')
        elif 'Result' in changed and changed['Result'] == 'failed':
            self.unit_states[service_name] = 'failed'
            self._log_event(service_name, 'failed', 'condition', job_type='condition', source='PropertiesChanged')
        elif self.debug:
            self.logger.debug(f"Skipping non-state PropertiesChanged for {service_name}: {changed}")

    def _unit_new(self, unit_name: str, unit_path: str) -> None:
        """Handle UnitNew signal to monitor new units."""
        if self.debug:
            self.logger.debug(f"UnitNew: {unit_name}, Path: {unit_path}")
        if unit_name in self.monitored_services:
            attempt = self.subscription_attempts.get(unit_name, 0) + 1
            self.subscription_attempts[unit_name] = attempt
            try:
                if not self.bus:
                    return
                unit_obj = self.bus.get_object('org.freedesktop.systemd1', unit_path)
                unit_obj.connect_to_signal(
                    'PropertiesChanged',
                    lambda i, c, inv: self._unit_properties_changed(i, c, inv, unit_path),
                    dbus_interface='org.freedesktop.DBus.Properties'
                )
                self.registered_units.add(unit_name)
                self.unit_path_to_name[unit_path] = unit_name
                if self.debug:
                    self.logger.debug(f"Subscribed to new unit: {unit_name} (attempt {attempt}, unit_path: {unit_path})")
                self._poll_unit_state(unit_name, unit_path)
            except dbus.exceptions.DBusException as e:
                self.logger.error(f"Failed to subscribe to new unit {unit_name} (attempt {attempt}): {e}")
                if attempt < self.config.max_retries:  # Use config for retries
                    GLib.timeout_add(1000, lambda: self._unit_new(unit_name, unit_path))

    def _job_new(self, job_id: int, job_obj: Any, unit_name: str) -> None:
        """Handle JobNew signal to detect jobs (e.g., start, stop, restart)."""
        if self.debug:
            self.logger.debug(f"JobNew: {unit_name}, JobID: {job_id}")
        if unit_name in self.monitored_services:
            service_name = unit_name.replace('.service', '').replace('.mount', '')
            self._log_event(service_name, 'pending', 'job', job_type='unknown', source='JobNew')
            if self.debug:
                self.logger.debug(f"Logged JobNew for {service_name}")

    def _job_removed(self, job_id: int, job_obj: Any, unit_name: str, result: str) -> None:
        """Handle JobRemoved signal to detect job outcomes (e.g., failed, done)."""
        if self.debug:
            self.logger.debug(f"JobRemoved: {unit_name}, JobID: {job_id}, Result: {result}")
        if unit_name in self.monitored_services:
            service_name = unit_name.replace('.service', '').replace('.mount', '')
            if result == 'failed':
                self.unit_states[service_name] = 'failed'
                self._log_event(service_name, 'failed', 'job', job_type='failed', source='JobRemoved')
            elif result == 'done':
                if self.unit_last_job.get(service_name) == 'start':
                    self.unit_states[service_name] = 'active'
                    self._log_event(service_name, 'completed', 'job', job_type='start', source='JobRemoved')
                elif self.unit_last_job.get(service_name) == 'stop':
                    self.unit_states[service_name] = 'inactive'
                    self._log_event(service_name, 'completed', 'job', job_type='stop', source='JobRemoved')

    def _poll_unit_state(self, unit_name: str, unit_path: str, retry_count: int = 0) -> None:
        """Poll the state of a single unit with retry logic."""
        max_retries = self.config.max_retries
        if not self.bus:
            return
        try:
            unit_obj = self.bus.get_object('org.freedesktop.systemd1', unit_path)
            props = dbus.Interface(unit_obj, 'org.freedesktop.DBus.Properties')
            active_state = props.Get('org.freedesktop.systemd1.Unit', 'ActiveState')
            sub_state = props.Get('org.freedesktop.systemd1.Unit', 'SubState')
            service_name = unit_name.replace('.service', '').replace('.mount', '')
            last_state = self.unit_states.get(service_name)
            if last_state != active_state:
                self.unit_states[service_name] = active_state
                self._log_event(service_name, active_state, sub_state, source='Poll')
            if self.debug:
                self.logger.debug(f"Polled {service_name}: ActiveState={active_state}, SubState={sub_state}")
        except dbus.exceptions.DBusException as e:
            if retry_count < max_retries:
                if self.debug:
                    self.logger.debug(f"Retrying poll for {unit_name} (attempt {retry_count + 1}/{max_retries}): {e}")
                time.sleep(0.1)
                self._poll_unit_state(unit_name, unit_path, retry_count + 1)
            else:
                self.logger.error(f"Failed to poll unit {unit_name} after {max_retries} retries: {e}")

    def _poll_units(self) -> bool:
        """Periodically poll the state of registered units."""
        if self.debug:
            self.logger.debug("Polling registered units")
        if not self.manager:
            return False
        for unit_name in self.registered_units:
            try:
                unit_path = self.manager.GetUnit(unit_name)
                self._poll_unit_state(unit_name, unit_path)
            except dbus.exceptions.DBusException as e:
                self.logger.error(f"Failed to get unit path for {unit_name}: {e}")
        if self.running:
            return True
        return False

    def start(self) -> None:
        """Start monitoring specified systemd services via D-Bus."""
        if self.debug:
            self.logger.debug("Starting DBusMonitor")
        DBusGMainLoop(set_as_default=True)
        try:
            self.bus = dbus.SystemBus()
        except dbus.exceptions.DBusException as e:
            self.logger.error(f"Failed to connect to system bus: {e}")
            return

        try:
            systemd = self.bus.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
            self.manager = dbus.Interface(systemd, 'org.freedesktop.systemd1.Manager')
        except dbus.exceptions.DBusException as e:
            self.logger.error(f"Failed to connect to systemd D-Bus: {e}")
            return

        try:
            self.manager.Subscribe()
            self.bus.add_signal_receiver(
                self._unit_new,
                signal_name='UnitNew',
                dbus_interface='org.freedesktop.systemd1.Manager'
            )
            self.bus.add_signal_receiver(
                self._job_new,
                signal_name='JobNew',
                dbus_interface='org.freedesktop.systemd1.Manager'
            )
            self.bus.add_signal_receiver(
                self._job_removed,
                signal_name='JobRemoved',
                dbus_interface='org.freedesktop.systemd1.Manager'
            )
            if self.debug:
                self.logger.debug("Subscribed to systemd manager signals")
        except dbus.exceptions.DBusException as e:
            self.logger.error(f"Failed to subscribe to manager signals: {e}")
            return

        try:
            for unit in self.manager.ListUnits():
                unit_name = unit[0]
                if unit_name in self.monitored_services:
                    try:
                        unit_path = self.manager.GetUnit(unit_name)
                        unit_obj = self.bus.get_object('org.freedesktop.systemd1', unit_path)
                        unit_obj.connect_to_signal(
                            'PropertiesChanged',
                            lambda i, c, inv: self._unit_properties_changed(i, c, inv, unit_path),
                            dbus_interface='org.freedesktop.DBus.Properties'
                        )
                        self.registered_units.add(unit_name)
                        self.unit_path_to_name[unit_path] = unit_name
                        if self.debug:
                            self.logger.debug(f"Subscribed to unit: {unit_name} (unit_path: {unit_path})")
                        self._poll_unit_state(unit_name, unit_path)
                    except dbus.exceptions.DBusException as e:
                        self.logger.error(f"Failed to subscribe to unit {unit_name}: {e}")
                        if self.subscription_attempts.get(unit_name, 0) < self.config.max_retries:
                            GLib.timeout_add(1000, lambda: self._unit_new(unit_name, unit_path))
        except dbus.exceptions.DBusException as e:
            self.logger.error(f"Failed to list units: {e}")

        self._list_registered_units()

        GLib.timeout_add(self.config.poll_interval, self._poll_units)  # Use config for poll interval

        self.loop = GLib.MainLoop()
        self.running = True
        try:
            self.loop.run()
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
        finally:
            self.running = False

    def stop(self) -> None:
        """Stop the D-Bus monitoring loop."""
        if self.debug:
            self.logger.debug("Stopping DBusMonitor")
        if self.running and self.loop:
            self.loop.quit()
            self.running = False

class StatsAnalyzer:
    """Analyze logs and generate statistics for systemd service events."""
    def __init__(self, config: Config) -> None:
        self.config = config
        self.log_files = [config.log_file]
        self.logger = logging.getLogger('SystemdMonitor')
        self.debug = config.debug

    def _parse_logs(self, log_file: str) -> Dict[str, List[Dict[str, Any]]]:
        """Parse log file and extract service events."""
        events = defaultdict(list)
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    # Skip debug lines to prevent recursive logging
                    if 'DEBUG -' in line:
                        continue
                    match = re.match(
                        r'(\S+\s+\S+\s+\S+).*?Service:\s*([^,]+),\s*State:\s*([^,]+),\s*SubState:\s*([^,]+)(?:,\s*Source:\s*(\S+))?(?:,\s*Job:\s*(.+))?',
                        line
                    )
                    if match:
                        timestamp, service, state, substate, source, job_type = match.groups()
                        if not service or service == '-' or not re.match(r'^[a-zA-Z0-9@._-]+\.?(?:service|mount)?$', service):
                            if self.debug:
                                self.logger.debug(f"Skipping invalid service in logs: {service}")
                            continue
                        unescaped_service = unescape_unit_name(service.strip())
                        if unescaped_service not in self.config.monitored_services:
                            if self.debug:
                                self.logger.debug(f"Skipping non-monitored service in logs: {service} (unescaped: {unescaped_service})")
                            continue
                        events[unescaped_service].append({
                            'timestamp': timestamp,
                            'state': state.strip(),
                            'substate': substate.strip(),
                            'job_type': job_type.strip() if job_type else None,
                            'source': source.strip() if source else None
                        })
                    elif self.debug and not line.startswith('202'):
                        self.logger.debug(f"Line did not match regex (non-timestamped): {line.strip()}")
        except FileNotFoundError:
            print(f"Log file {log_file} not found.")
            self.logger.error(f"Log file {log_file} not found")
        except Exception as e:
            self.logger.error(f"Error parsing log file {log_file}: {e}")
        return events

    def generate_statistics(self) -> None:
        """Generate and print statistics from log files."""
        if self.debug:
            self.logger.debug("Generating statistics")
        for log_file in self.log_files:
            events = self._parse_logs(log_file)
            stats = defaultdict(lambda: {'crashes': 0, 'restarts': 0, 'starts': 0, 'stops': 0})
            last_state = {}

            for service, event_list in events.items():
                for event in event_list:
                    state = event['state']
                    substate = event['substate']
                    job_type = event['job_type']

                    # Only count valid state transitions
                    if state == 'unknown':
                        continue  # Skip unknown states unless failure-related
                    elif state == 'active':
                        stats[service]['starts'] += 1
                    elif state == 'inactive':
                        stats[service]['stops'] += 1
                    elif state == 'failed':
                        stats[service]['crashes'] += 1
                        stats[service]['restarts'] += 1
                    elif state == 'activating':
                        stats[service]['starts'] += 1
                    elif state == 'deactivating':
                        stats[service]['stops'] += 1
                    elif state == 'pending' and job_type in ['start', 'restart', 'unknown']:
                        stats[service]['starts'] += 1
                    elif state == 'pending' and job_type == 'stop':
                        stats[service]['stops'] += 1
                    elif state == 'completed' and job_type == 'start':
                        stats[service]['starts'] += 1
                    elif state == 'completed' and job_type == 'stop':
                        stats[service]['stops'] += 1

                    last_state[service] = state

            print(f"\nStatistics from {log_file}:")
            if not stats:
                print("No events found.")
                self.logger.info("No events found in statistics generation")
                continue
            headers = ["Service", "Crashes", "Restarts", "Starts", "Stops"]
            max_service_len = max(len(service) for service in stats.keys())
            print(f"{headers[0]:<{max_service_len}} {headers[1]:<10} {headers[2]:<10} {headers[3]:<10} {headers[4]:<10}")
            print("-" * (max_service_len + 40))
            for service, counts in sorted(stats.items()):
                print(f"{service:<{max_service_len}} {counts['crashes']:<10} {counts['restarts']:<10} {counts['starts']:<10} {counts['stops']:<10}")
            self.logger.info(f"Generated statistics for {log_file}")

class SystemdMonitor:
    """Orchestrate D-Bus monitoring with statistics."""
    def __init__(self, config: Config) -> None:
        self.config = config
        self.dbus_monitor = DBusMonitor(config)
        self.stats_analyzer = StatsAnalyzer(config)
        self.dbus_thread: Optional[threading.Thread] = None
        self.stats_thread: Optional[threading.Thread] = None
        self.running = False
        self.stats_running = False

    def start(self) -> None:
        """Start D-Bus monitoring and stats generation in separate threads."""
        self.running = True
        self.stats_running = True
        self.dbus_thread = threading.Thread(target=self.dbus_monitor.start)
        self.dbus_thread.start()
        self.stats_thread = threading.Thread(target=self._stats_loop)
        self.stats_thread.start()

    def _stats_loop(self) -> None:
        """Run periodic statistics generation."""
        logger = logging.getLogger('SystemdMonitor')
        if self.dbus_monitor.debug:
            logger.debug("Starting stats loop")
        while self.stats_running:
            try:
                self.stats_analyzer.generate_statistics()
                threading.Event().wait(self.config.stats_interval)  # Use config for stats interval
            except Exception as e:
                logger.error(f"Stats loop error: {e}")
                break
        if self.dbus_monitor.debug:
            logger.debug("Stats loop stopped")

    def stop(self) -> None:
        """Stop the monitor and stats threads."""
        logger = logging.getLogger('SystemdMonitor')
        if self.dbus_monitor.debug:
            logger.debug("Stopping SystemdMonitor")
        if self.running:
            self.stats_running = False
            self.dbus_monitor.stop()
            if self.dbus_thread:
                self.dbus_thread.join(timeout=2.0)
            if self.stats_thread:
                self.stats_thread.join(timeout=2.0)
            self.running = False

    def generate_stats(self) -> None:
        """Generate statistics from logs."""
        self.stats_analyzer.generate_statistics()

def signal_handler(sig: int, frame: Any) -> None:
    """Handle SIGINT (Ctrl+C) during runtime."""
    print("\nShutting down...")
    # Access monitor from the main function scope
    if 'monitor' in globals():
        monitor.stop()
        monitor.generate_stats()
    sys.exit(0)

def main() -> None:
    """Main entry point for the systemd monitor."""
    if not DBUS_AVAILABLE:
        print("Error: D-Bus dependencies are not available.")
        print("This tool requires systemd and D-Bus to be available on a Linux system.")
        sys.exit(1)
    
    config = parse_arguments()
    if config is None:  # Config file creation mode
        return
    
    log_file = config.log_file
    try:
        with open(log_file, 'a') as f:
            os.chmod(log_file, 0o666)
    except Exception as e:
        print(f"Failed to set permissions for {log_file}: {e}")
        sys.exit(1)

    global monitor  # Declare monitor as global
    monitor = SystemdMonitor(config)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        monitor.start()
        if monitor.dbus_thread:
            monitor.dbus_thread.join()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logging.getLogger('SystemdMonitor').error(f"SystemdMonitor error: {e}")
    finally:
        monitor.stop()

if __name__ == '__main__':
    main()