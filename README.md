# Systemd Monitor

`systemd_monitor.py` is a Python script designed to monitor the state of specified systemd services on a Linux system. It uses an **event-driven architecture** with D-Bus `PropertiesChanged` callbacks for real-time notification of service state changes. All monitored events are logged to a file with persistent counters tracking service starts, stops, and crashes across script runs.

## Features

*   **Event-Driven Architecture**: Uses D-Bus `PropertiesChanged` callbacks for immediate, efficient state change notifications
*   **Persistent State Tracking**: Counts of starts, stops, and crashes are persisted to JSON and survive script restarts
*   **Real-Time Logging**: Logs all service state changes with timestamps to rotating log files
*   **Crash Detection**: Identifies and logs service crashes with exit codes and signals
*   **Flexible Configuration**: Supports configuration via JSON files and command-line arguments
*   **Configurable Service List**: Monitor any set of systemd services
*   **Clean Architecture**: Separated configuration module for better code organization
*   **Comprehensive Testing**: 53 unit tests ensuring reliability (28 config tests, 25 monitor tests)
*   **Code Quality**: 100% pylint compliant with pre-commit hooks enforcing standards
*   **Graceful Shutdown**: Handles signals (SIGINT, SIGTERM) to save state and exit cleanly

## How it Works

The monitor uses an **event-driven architecture** for efficient, real-time service monitoring:

### Architecture Overview

1.  **Initialization**:
    *   Loads persistent state from JSON file (`/var/lib/service_monitor/service_states.json`)
    *   Connects to system D-Bus
    *   Subscribes to D-Bus signals from systemd manager
    *   For each monitored service, subscribes to `PropertiesChanged` signals

2.  **Event-Driven Monitoring**:
    *   Listens for D-Bus `PropertiesChanged` callbacks from systemd
    *   When a service state changes, immediately processes the event
    *   Detects state transitions: inactive→active (start), active→inactive (stop), active→failed (crash)
    *   Tracks crash details including exit codes and termination signals
    *   Updates persistent counters (starts, stops, crashes)

3.  **State Persistence**:
    *   Maintains JSON file with service state and counters
    *   Saves state after each significant event
    *   Preserves counters across script restarts
    *   Handles cleanup of unmonitored services

4.  **Logging**:
    *   Rotating log files (1MB max, 3 backups)
    *   Structured log entries with timestamps
    *   Different log levels for state changes, crashes, errors
    *   Formatted output for easy parsing

### Key Advantages Over Polling

- **Lower CPU Usage**: No continuous polling loop
- **Instant Detection**: State changes detected immediately via callbacks
- **More Reliable**: Direct notification from systemd, no missed states
- **Cleaner Code**: Event-driven pattern is easier to understand and maintain

## Configuration

The systemd monitor supports flexible configuration through JSON files and command-line arguments.

### Configuration Options (config.py module)

The `config.py` module provides:

- `monitored_services`: List of services to monitor
- `log_file`: Path to log file (default: `systemd_monitor.log`)
- `poll_interval`: Polling interval in milliseconds (default: 100) - *Reserved for future use*
- `stats_interval`: Statistics generation interval in seconds (default: 60) - *Reserved for future use*
- `max_retries`: Maximum retry attempts for failed operations (default: 3)
- `debug`: Enable debug logging (default: false)

> **Note**: The `config.py` module exists and provides full configuration management, but integration with the main monitoring code is pending.

### Default Monitored Services

The script is configured to monitor the following services by default:

```
wirepas-gateway.service
wirepas-sink-ttys1.service
wirepas-sink-ttys2.service
edger.connecteddev.service
edger.endries.service
devmgmt.service
hwcheck.service
provisioning.service
Node-Configuration.service
setup_cell_connect.service
mosquitto.service
wps_button_monitor.service
```

## Prerequisites

*   Python 3.7+
*   `python-dbus` (or `python3-dbus`)
*   `python-gi` (or `python3-gi`, `gir1.2-glib-2.0`)

Install on Debian-based systems:
```bash
sudo apt-get update
sudo apt-get install python3 python3-dbus python3-gi
```

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/istorrs/systemd_monitor.git
cd systemd_monitor
```

2. Install the package:
```bash
pip install -e .
```

### Development Installation

For development, install with additional tools:
```bash
pip install -e ".[dev]"
```

## Usage

### Basic Usage

Run the monitor:
```bash
python -m systemd_monitor.systemd_monitor
```

### Command Line Options

- `-h, --help`: Show help message and monitored services
- `-v, --version`: Show module version
- `-c, --clear`: Clear history log and persistence file
- `-l FILE, --log-file FILE`: Path to log file (default: `/tmp/service_monitor.log`)
- `-p FILE, --persistence-file FILE`: Path to persistence file (default: `/var/lib/service_monitor/service_states.json`)

### Examples

1. **Custom log file**:
   ```bash
   python -m systemd_monitor.systemd_monitor --log-file /var/log/my-services.log
   ```

2. **Clear history**:
   ```bash
   python -m systemd_monitor.systemd_monitor --clear
   ```

## Output

### Log File Example

```
2025-07-07 10:15:23 - [INFO] wirepas-gateway.service:  inactive      -> active        (SubState: running)
2025-07-07 10:15:23 - [INFO] wirepas-gateway.service:  Incrementing start counter -> 1
2025-07-07 11:20:45 - [ERROR] mosquitto.service: **CRASH** (ExitCode: 1, Signal: 9 (SIGKILL))
```

### Persistent State File

Located at `/var/lib/service_monitor/service_states.json`:

```json
{
  "wirepas-gateway.service": {
    "last_state": "active",
    "last_change_time": "2025-07-07 10:15:23",
    "starts": 5,
    "stops": 4,
    "crashes": 0,
    "logged_unloaded": false
  }
}
```

## Development

### Running Tests

```bash
# Full test suite
pytest

# With coverage
pytest --cov=systemd_monitor --cov-report=term-missing

# Without coverage (faster)
pytest --no-cov
```

> **Note**: 23 of 25 systemd_monitor tests require dbus and will skip gracefully if unavailable.

### Code Quality

```bash
# Run pylint (must score 10/10)
pylint systemd_monitor/ tests/

# Format code
black systemd_monitor/ tests/

# Type checking
mypy systemd_monitor/
```

### Pre-commit Hooks

Install hooks for automatic quality checks:

```bash
pre-commit install
```

The hooks enforce:
- ✅ Pylint compliance (10/10 score required)
- ✅ All unit tests must pass

See `PRE_COMMIT_HOOK.md` for details.

## Troubleshooting

### Skipped Tests

If you see "28 passed, 23 skipped" - this is normal. The 23 systemd_monitor tests skip without dbus bindings.

### Permission Errors

Run with sudo or use custom persistence path:
```bash
python -m systemd_monitor.systemd_monitor -p ~/.config/systemd_monitor/state.json
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure tests pass and code is pylint compliant
5. Submit a pull request

All contributions must:
- Pass unit tests
- Achieve 10/10 pylint score
- Include documentation updates

## Documentation

- **CHANGELOG.md**: Version history and migration guides
- **PRE_COMMIT_HOOK.md**: Pre-commit hook documentation
- **PR2_ANALYSIS.md**: Development roadmap and architecture analysis

## License

MIT License - see LICENSE file for details.

## Roadmap

- [ ] Integrate config.py module
- [ ] GitHub Actions CI/CD
- [ ] Type hints throughout
- [ ] Prometheus metrics export
- [ ] Web dashboard

See [PR2_ANALYSIS.md](PR2_ANALYSIS.md) for detailed plan.
