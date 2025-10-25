# Installation Guide

This guide covers installing and running the systemd monitor as a system service.

## Prerequisites

- Python 3.8 or higher
- systemd-based Linux distribution
- D-Bus system bus access
- Root or sudo privileges (for system service installation)

## Quick Install

### 1. Install Dependencies

#### Debian/Ubuntu
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-dbus python3-gi gir1.2-glib-2.0
```

#### RHEL/CentOS/Fedora
```bash
sudo dnf install -y python3 python3-pip python3-dbus python3-gobject
```

### 2. Install Python Package

```bash
# Clone the repository
git clone https://github.com/istorrs/systemd_monitor.git
cd systemd_monitor

# Install Python dependencies
sudo pip3 install -r requirements.txt

# Optional: Install development dependencies
sudo pip3 install -r requirements-dev.txt
```

### 3. Install as System Service

```bash
# Create installation directory
sudo mkdir -p /opt/systemd_monitor
sudo mkdir -p /etc/systemd_monitor
sudo mkdir -p /var/lib/service_monitor
sudo mkdir -p /var/log

# Copy application files
sudo cp -r systemd_monitor /opt/systemd_monitor/
sudo cp config.json.example /etc/systemd_monitor/config.json

# Edit configuration to monitor your services
sudo nano /etc/systemd_monitor/config.json

# Install systemd unit file
sudo cp systemd-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 4. Configure the Service

Edit `/etc/systemd_monitor/config.json` to specify which services to monitor:

```json
{
  "monitored_services": [
    "nginx.service",
    "postgresql.service",
    "redis.service"
  ],
  "log_file": "/var/log/systemd_monitor.log",
  "debug": false
}
```

### 5. Start the Service

```bash
# Enable service to start on boot
sudo systemctl enable systemd-monitor

# Start the service
sudo systemctl start systemd-monitor

# Check service status
sudo systemctl status systemd-monitor

# View logs
sudo journalctl -u systemd-monitor -f
```

## Manual Installation (Non-Service)

If you prefer to run the monitor manually without systemd:

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run with custom configuration
python3 -m systemd_monitor.systemd_monitor --config config.json

# Or specify services directly
python3 -m systemd_monitor.systemd_monitor --services nginx.service postgresql.service

# Enable debug logging
python3 -m systemd_monitor.systemd_monitor --debug
```

## Configuration Options

### Command-Line Arguments

- `--config FILE` - Path to JSON configuration file
- `--services SERVICE [...]` - List of services to monitor (overrides config file)
- `--log-file FILE` - Path to log file
- `--persistence-file FILE` - Path to state persistence file
- `--debug` - Enable debug logging
- `-h, --help` - Show help message
- `-v, --version` - Show version
- `-c, --clear` - Clear history log and persistence file

### Configuration File

Create a JSON file with the following structure:

```json
{
  "monitored_services": [
    "service1.service",
    "service2.service"
  ],
  "log_file": "/var/log/systemd_monitor.log",
  "poll_interval": 100,
  "stats_interval": 60,
  "max_retries": 3,
  "debug": false
}
```

**Note**: Command-line arguments override configuration file settings.

## Service Management

### Common Commands

```bash
# Start service
sudo systemctl start systemd-monitor

# Stop service
sudo systemctl stop systemd-monitor

# Restart service
sudo systemctl restart systemd-monitor

# Check status
sudo systemctl status systemd-monitor

# Enable on boot
sudo systemctl enable systemd-monitor

# Disable on boot
sudo systemctl disable systemd-monitor

# View logs (live)
sudo journalctl -u systemd-monitor -f

# View logs (last 100 lines)
sudo journalctl -u systemd-monitor -n 100

# View logs (since boot)
sudo journalctl -u systemd-monitor -b
```

### Monitoring Logs

The service logs to two places:

1. **Application Log**: Configured in `config.json` (default: `/var/log/systemd_monitor.log`)
   - Contains service state changes, starts, stops, crashes
   - Rotates at 1MB with 3 backups

2. **System Journal**: Via `journalctl`
   - Contains service startup/shutdown messages
   - Integrated with systemd logging

```bash
# View application log
sudo tail -f /var/log/systemd_monitor.log

# View system journal
sudo journalctl -u systemd-monitor -f
```

## Troubleshooting

### Service Won't Start

1. Check if D-Bus is available:
   ```bash
   systemctl status dbus
   ```

2. Verify Python dependencies:
   ```bash
   python3 -c "import jeepney"
   ```

3. Check configuration file syntax:
   ```bash
   python3 -m json.tool /etc/systemd_monitor/config.json
   ```

4. Check file permissions:
   ```bash
   ls -la /etc/systemd_monitor/config.json
   ls -la /var/lib/service_monitor
   ```

### Permission Errors

The service runs as root to access the system D-Bus. If running manually:

```bash
# Ensure your user is in the systemd-journal group
sudo usermod -a -G systemd-journal $USER

# Or run with sudo
sudo python3 -m systemd_monitor.systemd_monitor
```

### Services Not Being Monitored

1. Verify service names are correct:
   ```bash
   systemctl list-units --type=service | grep <service-name>
   ```

2. Check if services exist:
   ```bash
   systemctl status <service-name>
   ```

3. Enable debug logging:
   ```bash
   sudo systemctl stop systemd-monitor
   sudo python3 -m systemd_monitor.systemd_monitor --debug
   ```

### High CPU Usage

The monitor uses event-driven D-Bus callbacks, not polling, so CPU usage should be minimal. If experiencing high CPU:

1. Check number of monitored services (reduce if necessary)
2. Verify no infinite restart loops in monitored services
3. Check for D-Bus issues: `sudo journalctl -u dbus -f`

## Uninstallation

```bash
# Stop and disable service
sudo systemctl stop systemd-monitor
sudo systemctl disable systemd-monitor

# Remove systemd unit file
sudo rm /etc/systemd/system/systemd-monitor.service
sudo systemctl daemon-reload

# Remove application files
sudo rm -rf /opt/systemd_monitor
sudo rm -rf /etc/systemd_monitor

# Optional: Remove data and logs
sudo rm -rf /var/lib/service_monitor
sudo rm /var/log/systemd_monitor.log*
```

## Upgrading

```bash
# Stop service
sudo systemctl stop systemd-monitor

# Pull latest code
cd systemd_monitor
git pull

# Update installation
sudo cp -r systemd_monitor /opt/systemd_monitor/
sudo cp systemd-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start service
sudo systemctl start systemd-monitor
```

## Security Considerations

The systemd unit file includes security hardening:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to home directories
- `ProtectKernelTunables=true` - Kernel tunables are read-only
- `ProtectKernelModules=true` - Cannot load kernel modules
- `ProtectControlGroups=true` - Control groups are read-only

Write access is only granted to:
- `/var/lib/service_monitor` - State persistence
- `/var/log` - Log files

## Advanced Configuration

### Custom Installation Paths

If you want to install in different locations, edit the systemd unit file:

```ini
# In systemd-monitor.service
WorkingDirectory=/your/custom/path
ExecStart=/usr/bin/python3 -m systemd_monitor.systemd_monitor --config /your/config/path/config.json
```

Then update the `ReadWritePaths` if needed:

```ini
ReadWritePaths=/your/custom/data/path /your/custom/log/path
```

### Running as Non-Root User

**Warning**: The service requires access to the system D-Bus, which typically requires root privileges.

If you want to run as a specific user:

1. Create a dedicated user:
   ```bash
   sudo useradd -r -s /bin/false systemd-monitor
   ```

2. Grant D-Bus access by creating `/etc/dbus-1/system.d/systemd-monitor.conf`:
   ```xml
   <!DOCTYPE busconfig PUBLIC
    "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
    "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
   <busconfig>
     <policy user="systemd-monitor">
       <allow send_destination="org.freedesktop.systemd1"/>
       <allow receive_sender="org.freedesktop.systemd1"/>
     </policy>
   </busconfig>
   ```

3. Update service unit file:
   ```ini
   User=systemd-monitor
   Group=systemd-monitor
   ```

4. Fix file permissions:
   ```bash
   sudo chown -R systemd-monitor:systemd-monitor /var/lib/service_monitor
   ```

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/istorrs/systemd_monitor/issues
- Documentation: See README.md and CHANGELOG.md
