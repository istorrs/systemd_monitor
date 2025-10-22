"""Configuration management for systemd monitor."""
import os
import json
import argparse
from typing import Set, Dict, Any, Optional


class Config:
    """Configuration management for systemd monitor."""

    DEFAULT_CONFIG = {
        'monitored_services': [
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
            'wps_button_monitor.service',
            'mosquitto.service'
        ],
        'log_file': 'systemd_monitor.log',
        'poll_interval': 100,  # milliseconds
        'stats_interval': 60,  # seconds
        'max_retries': 3,
        'debug': False
    }

    def __init__(self, config_file: Optional[str] = None, **kwargs):
        """Initialize configuration from file and/or command line arguments."""
        self.config = self.DEFAULT_CONFIG.copy()

        # Load from config file if provided
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)

        # Override with command line arguments
        self._update_from_kwargs(kwargs)

    def _load_from_file(self, config_file: str):
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except (json.JSONDecodeError, IOError) as e:
            raise ValueError(f"Failed to load config file {config_file}: {e}") from e

    def _update_from_kwargs(self, kwargs: Dict[str, Any]):
        """Update configuration from keyword arguments."""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value

    @property
    def monitored_services(self) -> Set[str]:
        """Get set of monitored services."""
        return set(self.config['monitored_services'])

    @property
    def log_file(self) -> str:
        """Get log file path."""
        return self.config['log_file']

    @property
    def poll_interval(self) -> int:
        """Get polling interval in milliseconds."""
        return self.config['poll_interval']

    @property
    def stats_interval(self) -> int:
        """Get statistics generation interval in seconds."""
        return self.config['stats_interval']

    @property
    def max_retries(self) -> int:
        """Get maximum retry attempts."""
        return self.config['max_retries']

    @property
    def debug(self) -> bool:
        """Get debug mode setting."""
        return self.config['debug']

    def save_config(self, config_file: str):
        """Save current configuration to file."""
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
        except IOError as e:
            raise ValueError(f"Failed to save config file {config_file}: {e}") from e


def parse_arguments() -> Optional[Config]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Systemd Service Monitor')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--log-file', type=str, help='Log file path')
    parser.add_argument('--services', nargs='+',
                        help='List of services to monitor')
    parser.add_argument('--poll-interval', type=int,
                        help='Polling interval in milliseconds')
    parser.add_argument('--stats-interval', type=int,
                        help='Statistics generation interval in seconds')
    parser.add_argument('--create-config', type=str,
                        help='Create a default configuration file')

    args = parser.parse_args()

    # Handle config file creation
    if args.create_config:
        config = Config()
        config.save_config(args.create_config)
        print(f"Created default configuration file: {args.create_config}")
        return None

    # Build kwargs from arguments
    kwargs = {}
    if args.debug:
        kwargs['debug'] = True
    if args.log_file:
        kwargs['log_file'] = args.log_file
    if args.services:
        kwargs['monitored_services'] = args.services
    if args.poll_interval:
        kwargs['poll_interval'] = args.poll_interval
    if args.stats_interval:
        kwargs['stats_interval'] = args.stats_interval

    return Config(args.config, **kwargs)
