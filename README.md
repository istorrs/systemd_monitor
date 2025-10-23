# Systemd Monitor

`systemd_monitor.py` is a Python script designed to monitor the state of specified systemd services on a Linux system. It uses an **event-driven architecture** with D-Bus `PropertiesChanged` callbacks for real-time notification of service state changes. All monitored events are logged to a file with persistent counters tracking service starts, stops, and crashes across script runs.

## Features

*   **Event-Driven Architecture**: Uses D-Bus `PropertiesChanged` callbacks for immediate, efficient state change notifications
*   **Persistent State Tracking**: Counts of starts, stops, and crashes are persisted to JSON and survive script restarts
*   **Real-Time Logging**: Logs all service state changes with timestamps to rotating log files
*   **Crash Detection**: Identifies and logs service crashes with exit codes and signals
*   **Flexible Configuration**: Supports configuration via JSON files and command-line arguments
*   **Configurable Service List**: Monitor any set of systemd services via config file or CLI
*   **Clean Architecture**: Separated configuration module (`config.py`) for better code organization
*   **Comprehensive Testing**: **51 unit tests** with **70% code coverage** - all tests run without dbus!
*   **Code Quality**: 100% pylint compliant with comprehensive pre-commit hooks
*   **CI/CD Pipeline**: Full GitHub Actions workflow with test result visualization
*   **Graceful Shutdown**: Handles signals (SIGINT, SIGTERM) to save state and exit cleanly

## How it Works

The monitor uses an **event-driven architecture** for efficient, real-time service monitoring:

### Architecture Overview

1.  **Initialization**:
    *   Loads configuration from JSON file (if specified) or command-line arguments
    *   Loads persistent state from JSON file (`/var/lib/service_monitor/service_states.json`)
    *   Connects to system D-Bus
    *   Subscribes to D-Bus signals from systemd manager
    *   For each monitored service, subscribes to `PropertiesChanged` signals
    *   Polls initial service states to establish baseline

2.  **Event-Driven Monitoring**:
    *   Listens for D-Bus `PropertiesChanged` callbacks from systemd
    *   When a service state changes, immediately processes the event
    *   Detects state transitions: inactive→active (start), active→inactive (stop), active→failed (crash)
    *   Tracks crash details including exit codes and termination signals
    *   Updates persistent counters (starts, stops, crashes)
    *   No continuous polling - callbacks provide instant notification

3.  **State Persistence**:
    *   Maintains JSON file with service state and counters
    *   Saves state after each significant event (counter changes)
    *   Preserves counters across script restarts
    *   Handles cleanup of unmonitored services
    *   Creates persistence directory if it doesn't exist

4.  **Logging**:
    *   Rotating log files (1MB max, 3 backups)
    *   Structured log entries with timestamps
    *   Different log levels for state changes, crashes, errors
    *   Formatted output for easy parsing
    *   Configurable debug logging

### Key Advantages Over Polling

- **Lower CPU Usage**: No continuous polling loop consuming resources
- **Instant Detection**: State changes detected immediately via callbacks (no delay)
- **More Reliable**: Direct notification from systemd, no missed states between polls
- **Cleaner Code**: Event-driven pattern is easier to understand and maintain
- **Scalable**: Can monitor many services without performance degradation

## Configuration

The systemd monitor supports flexible configuration through JSON files and command-line arguments.

### Configuration Module (`config.py`)

The integrated `config.py` module provides comprehensive configuration management:

**Configuration Options:**
- `monitored_services`: List of services to monitor (required)
- `log_file`: Path to log file (default: `/tmp/service_monitor.log`)
- `debug`: Enable debug logging (default: `false`)
- `max_retries`: Maximum retry attempts for failed operations (default: 3)

**Reserved for Future Use:**
- `poll_interval`: Would set polling interval if we used polling (we don't)
- `stats_interval`: Interval for statistics generation (planned feature)

### Command-Line Options

Run with `-h` or `--help` to see all options:

```bash
python -m systemd_monitor.systemd_monitor --help
```

**Available Options:**
- `-h, --help`: Show help message and currently monitored services
- `-v, --version`: Show module version
- `-c, --clear`: Clear history log and persistence file
- `--config FILE`: Path to JSON configuration file
- `--services SERVICE [...]`: List of services to monitor (overrides config file)
- `-l FILE, --log-file FILE`: Path to log file (overrides config)
- `-p FILE, --persistence-file FILE`: Path to persistence file
- `--debug`: Enable debug logging

### Configuration Priority

Configuration is applied in this order (later overrides earlier):
1. Default values in code
2. JSON configuration file (if `--config` specified)
3. Command-line arguments

### Configuration File Example

Create a JSON config file (`/etc/systemd_monitor/config.json`):

```json
{
  "monitored_services": [
    "nginx.service",
    "postgresql.service",
    "redis.service"
  ],
  "log_file": "/var/log/systemd_monitor/services.log",
  "debug": false,
  "max_retries": 3
}
```

Use it:
```bash
python -m systemd_monitor.systemd_monitor --config /etc/systemd_monitor/config.json
```

### Default Monitored Services

If no configuration is provided, the script monitors these services by default:

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

*   Python 3.8+ (tested on 3.8, 3.9, 3.10, 3.11)
*   `python-dbus` (or `python3-dbus`)
*   `python-gi` (or `python3-gi`, `gir1.2-glib-2.0`)

Install on Debian-based systems:
```bash
sudo apt-get update
sudo apt-get install python3 python3-dbus python3-gi gir1.2-glib-2.0
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
pip install -r requirements-dev.txt
```

This includes:
- Testing: `pytest`, `pytest-cov`, `pytest-mock`
- Code Quality: `black`, `flake8`, `pylint`, `mypy`
- Security: `bandit`, `safety`
- Pre-commit hooks: `pre-commit`

## Usage

### Basic Usage

Run the monitor with default services:
```bash
python -m systemd_monitor.systemd_monitor
```

### Configuration File Usage

Monitor specific services using a config file:
```bash
python -m systemd_monitor.systemd_monitor --config /etc/systemd_monitor/config.json
```

### Command-Line Configuration

Monitor specific services directly from CLI:
```bash
python -m systemd_monitor.systemd_monitor \
  --services nginx.service postgresql.service redis.service \
  --log-file /var/log/my-services.log \
  --debug
```

### Other Examples

1. **Clear history and restart fresh**:
   ```bash
   python -m systemd_monitor.systemd_monitor --clear
   ```

2. **Custom persistence location**:
   ```bash
   python -m systemd_monitor.systemd_monitor \
     --persistence-file ~/.config/systemd_monitor/state.json
   ```

3. **Debug mode** (verbose logging):
   ```bash
   python -m systemd_monitor.systemd_monitor --debug
   ```

## Output

### Log File Example

```
2025-10-23 10:15:23 - [INFO] wirepas-gateway.service:  inactive      -> active        (SubState: running)
2025-10-23 10:15:23 - [INFO] wirepas-gateway.service:  Incrementing start counter -> 1
2025-10-23 11:20:45 - [ERROR] mosquitto.service: **CRASH** (ExitCode: 1, Signal: 9 (SIGKILL))
2025-10-23 11:20:45 - [ERROR] mosquitto.service: Incrementing crash counter -> 1
```

### Persistent State File

Located at `/var/lib/service_monitor/service_states.json`:

```json
{
  "wirepas-gateway.service": {
    "last_state": "active",
    "last_change_time": "2025-10-23 10:15:23",
    "starts": 5,
    "stops": 4,
    "crashes": 0,
    "logged_unloaded": false
  },
  "mosquitto.service": {
    "last_state": "failed",
    "last_change_time": "2025-10-23 11:20:45",
    "starts": 3,
    "stops": 2,
    "crashes": 1,
    "logged_unloaded": false
  }
}
```

## Development

### Running Tests

All 51 tests run without requiring dbus installed (uses mocked dependencies):

```bash
# Full test suite
pytest

# With coverage report
pytest --cov=systemd_monitor --cov-report=term-missing

# Specific test file
pytest tests/test_systemd_monitor.py -v

# Fast mode (no coverage)
pytest --no-cov
```

**Test Coverage:**
- Total: **70% coverage**
- `config.py`: 100% coverage (28 tests)
- `systemd_monitor.py`: 62% coverage (23 tests)
- All tests use mocked dbus dependencies - no actual systemd required!

### Code Quality

The project enforces strict code quality standards:

```bash
# Run pylint (must score 10/10)
pylint systemd_monitor/ tests/

# Format code with Black
black systemd_monitor/ tests/

# Check formatting
black --check systemd_monitor/ tests/

# Type checking
mypy systemd_monitor/

# Flake8 linting
flake8 systemd_monitor/ tests/ --max-complexity=10 --max-line-length=100

# Security scans
bandit -r systemd_monitor/ -ll -i
safety check
```

### Pre-commit Hooks

The project includes comprehensive pre-commit hooks that run automatically:

```bash
# Install hooks
pre-commit install
```

**The hooks enforce 5 quality gates:**
1. **Pylint**: Code must score 10.00/10
2. **Black**: Code must be formatted correctly
3. **Flake8**: No syntax errors, complexity under 10, lines under 100 chars
4. **Bandit**: No security vulnerabilities
5. **Pytest**: All 51 unit tests must pass

See `PRE_COMMIT_HOOK.md` for details.

### CI/CD Pipeline

The project has a comprehensive GitHub Actions CI/CD pipeline:

**Workflow Jobs:**
1. **Lint**: Pylint checks (10/10 required)
2. **Test**: Full test suite on Python 3.8, 3.9, 3.10, 3.11
   - JUnit XML test results published to GitHub UI
   - Coverage reports uploaded to Codecov
3. **Code Quality**: Black, Flake8, MyPy checks
4. **Build**: Package build and validation
5. **Security**: Bandit and Safety vulnerability scans

**CI/CD Features:**
- ✅ Multi-version testing (Python 3.8-3.11)
- ✅ Test result visualization in GitHub Actions UI
- ✅ Coverage tracking with Codecov
- ✅ Security scanning
- ✅ Automated quality enforcement

The CI/CD workflow uses system-installed dbus packages (`python3-dbus`, `python3-gi`) with `PYTHONPATH` configuration to avoid build issues, but the tests themselves use mocked dependencies.

## Troubleshooting

### Test Results

You should see: **"51 passed in X.XX seconds"**

All tests now run successfully without dbus installed thanks to comprehensive mocking!

### Permission Errors

The default persistence path `/var/lib/service_monitor/` requires elevated permissions.

**Solutions:**
1. Run with sudo (not recommended for development)
2. Use custom persistence path in user directory:
   ```bash
   python -m systemd_monitor.systemd_monitor \
     -p ~/.config/systemd_monitor/state.json
   ```

### D-Bus Connection Errors

If you see D-Bus connection errors:
1. Ensure systemd is running: `systemctl status`
2. Check D-Bus is accessible: `busctl status`
3. Verify permissions to access system D-Bus

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all quality checks pass (pre-commit hooks will help!)
5. Submit a pull request

**All contributions must:**
- Pass all 51 unit tests
- Achieve 10/10 pylint score
- Pass Black formatting
- Pass Flake8 checks
- Pass Bandit security scan
- Include documentation updates
- Maintain or improve code coverage

## Documentation

- **CHANGELOG.md**: Version history and migration guides
- **PRE_COMMIT_HOOK.md**: Pre-commit hook documentation
- **PR2_ANALYSIS.md**: Development roadmap and architecture analysis
- **COMPLETION_SUMMARY.md**: Project completion status

## Architecture

### Modules

**`systemd_monitor.py`** - Main monitoring logic
- Event-driven D-Bus monitoring
- State change detection
- Crash tracking
- Logging and persistence

**`config.py`** - Configuration management
- JSON file parsing
- Command-line argument handling
- Configuration validation
- Default value management

### Testing Strategy

**Unit Tests** (`tests/test_*.py`):
- Mock all external dependencies (dbus, GLib)
- Test business logic independently
- Fast execution (< 1 second)
- Run everywhere (no system dependencies)

**Integration Tests** (future):
- Would test actual systemd integration
- Require systemd and dbus
- Slower execution
- Environment-specific

## License

MIT License - see LICENSE file for details.

## Roadmap

**Completed:**
- ✅ Event-driven D-Bus architecture
- ✅ Config.py module integration
- ✅ GitHub Actions CI/CD pipeline
- ✅ Comprehensive type hints
- ✅ 51 unit tests with mocking
- ✅ Pre-commit hooks (5 quality gates)
- ✅ Test result visualization
- ✅ Security scanning

**In Progress:**
- 🔄 Improve test coverage to 80%+
- 🔄 Integration test suite

**Planned:**
- 📋 Prometheus metrics export
- 📋 Web dashboard for visualization
- 📋 Alerting capabilities
- 📋 Configuration hot-reload
- 📋 Systemd unit file for running as service

See [PR2_ANALYSIS.md](PR2_ANALYSIS.md) and [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md) for detailed status.
