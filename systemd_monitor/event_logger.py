"""
Structured event logging for service state changes.

Logs service events in JSON Lines format for analysis and alerting.
Each event includes a machine ID for multi-host centralized logging.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path


def get_machine_id() -> str:
    """
    Get the machine ID from /etc/machine-id.

    Returns:
        Machine ID as a string, or 'unknown' if not available.
    """
    try:
        machine_id_path = Path("/etc/machine-id")
        if machine_id_path.exists():
            return machine_id_path.read_text(encoding="utf-8").strip()
    except (OSError, IOError):
        pass

    # Fallback to /var/lib/dbus/machine-id
    try:
        dbus_machine_id_path = Path("/var/lib/dbus/machine-id")
        if dbus_machine_id_path.exists():
            return dbus_machine_id_path.read_text(encoding="utf-8").strip()
    except (OSError, IOError):
        pass

    return "unknown"


class ServiceEventLogger:
    """Logs service state changes as JSON Lines."""

    def __init__(
        self,
        log_file: str,
        max_bytes: int = 10_485_760,
        backup_count: int = 5,
    ):
        """
        Initialize the event logger.

        Args:
            log_file: Path to the JSON Lines log file.
            max_bytes: Maximum size of log file before rotation (default: 10 MB).
            backup_count: Number of backup files to keep (default: 5).
        """
        self.log_file = log_file
        self.machine_id = get_machine_id()

        # Create parent directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up rotating file handler
        self.handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )

        # Create a logger for events (separate from main logger)
        self.logger = logging.getLogger("systemd_monitor.events")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)
        self.logger.propagate = False  # Don't propagate to root logger

    def log_event(  # pylint: disable=too-many-arguments
        self,
        event_type: str,
        service: str,
        from_state: Optional[str],
        to_state: str,
        counters: Dict[str, int],
        **extra_fields: Any,
    ) -> None:
        """
        Log a service state change event.

        Args:
            event_type: Type of event ("start", "stop", "crash", "restart").
            service: Name of the systemd service.
            from_state: Previous state (can be None for initial state).
            to_state: Current state after the event.
            counters: Dictionary with starts, stops, crashes counts.
            **extra_fields: Additional fields to include in the log entry.
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "machine_id": self.machine_id,
            "event": event_type,
            "service": service,
            "from_state": from_state,
            "to_state": to_state,
            "counters": counters,
        }

        # Add any extra fields
        if extra_fields:
            event.update(extra_fields)

        # Log as JSON (handler writes to file)
        self.logger.info(json.dumps(event, sort_keys=True))

    def close(self) -> None:
        """Close the event logger and flush handlers."""
        self.handler.close()
        self.logger.removeHandler(self.handler)
