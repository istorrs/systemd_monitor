"""
Prometheus metrics exporter for systemd_monitor.

Provides metrics about systemd service states, transitions, and the monitor itself.
Metrics are exposed via HTTP endpoint for Prometheus scraping.
"""

import logging
from typing import Optional

try:
    from prometheus_client import start_http_server, Gauge, Counter, Info

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

LOGGER = logging.getLogger(__name__)

# State mapping for numeric gauge values
STATE_MAP = {
    "active": 1,
    "inactive": 0,
    "activating": 2,
    "deactivating": 3,
    "failed": -1,
    "unloaded": -2,
}


class PrometheusMetrics:  # pylint: disable=too-many-instance-attributes
    """
    Manages Prometheus metrics for systemd service monitoring.

    Provides gauges for current service states and counters for state transitions.
    Metrics track deltas only (since monitor startup), not historical persisted values.
    """

    def __init__(self):
        """Initialize Prometheus metrics (if available)."""
        self.enabled = False
        self.service_state: Optional[Gauge] = None
        self.service_starts: Optional[Counter] = None
        self.service_stops: Optional[Counter] = None
        self.service_crashes: Optional[Counter] = None
        self.service_restarts: Optional[Counter] = None
        self.service_last_change: Optional[Gauge] = None
        self.monitor_info: Optional[Info] = None

        if not PROMETHEUS_AVAILABLE:
            LOGGER.warning(
                "prometheus_client not installed. Metrics disabled. "
                "Install with: pip install prometheus-client"
            )
            return

        try:
            # Service state as numeric gauge
            self.service_state = Gauge(
                "systemd_service_state",
                "Service state: 1=active, 0=inactive, 2=activating, "
                "3=deactivating, -1=failed, -2=unloaded",
                ["service"],
            )

            # Counters for state transitions (delta only, not persisted)
            self.service_starts = Counter(
                "systemd_service_starts_total",
                "Total number of service starts since monitor started",
                ["service"],
            )

            self.service_stops = Counter(
                "systemd_service_stops_total",
                "Total number of service stops since monitor started",
                ["service"],
            )

            self.service_crashes = Counter(
                "systemd_service_crashes_total",
                "Total number of service crashes (failed state) since monitor started",
                ["service"],
            )

            self.service_restarts = Counter(
                "systemd_service_restarts_total",
                "Total number of service restart cycles since monitor started",
                ["service"],
            )

            # Last state change timestamp
            self.service_last_change = Gauge(
                "systemd_service_last_change_timestamp",
                "Unix timestamp of last state change",
                ["service"],
            )

            # Monitor metadata
            self.monitor_info = Info(
                "systemd_monitor", "Metadata about the systemd_monitor instance"
            )

            self.enabled = True
            LOGGER.info("Prometheus metrics initialized successfully")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.error("Failed to initialize Prometheus metrics: %s", exc)
            self.enabled = False

    def start_http_server(self, port: int) -> bool:
        """
        Start the Prometheus HTTP server.

        Args:
            port: Port number for the metrics endpoint

        Returns:
            True if server started successfully, False otherwise
        """
        if not self.enabled:
            LOGGER.warning("Cannot start Prometheus server: metrics not initialized")
            return False

        try:
            start_http_server(port)
            LOGGER.info(
                "Prometheus metrics available at http://localhost:%d/metrics", port
            )
            return True
        except OSError as exc:
            LOGGER.error(
                "Failed to start Prometheus HTTP server on port %d: %s", port, exc
            )
            return False

    def set_monitor_info(self, version: str, monitored_services: list) -> None:
        """
        Set monitor metadata information.

        Args:
            version: Version string of the monitor
            monitored_services: List of services being monitored
        """
        if not self.enabled or not self.monitor_info:
            return

        try:
            self.monitor_info.info(
                {
                    "version": version,
                    "monitored_services": ",".join(sorted(monitored_services)),
                    "service_count": str(len(monitored_services)),
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.error("Failed to set monitor info: %s", exc)

    def update_service_state(self, service: str, state: str, timestamp: float) -> None:
        """
        Update service state gauge and timestamp.

        Args:
            service: Service name (e.g., 'nginx.service')
            state: Service state ('active', 'inactive', 'failed', etc.)
            timestamp: Unix timestamp of the state change
        """
        if not self.enabled:
            return

        try:
            # Update state gauge
            if self.service_state:
                state_value = STATE_MAP.get(state, -99)
                self.service_state.labels(service=service).set(state_value)

            # Update timestamp
            if self.service_last_change:
                self.service_last_change.labels(service=service).set(timestamp)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.error("Failed to update service state for %s: %s", service, exc)

    def increment_starts(self, service: str) -> None:
        """
        Increment the starts counter for a service.

        Args:
            service: Service name
        """
        if self.enabled and self.service_starts:
            try:
                self.service_starts.labels(service=service).inc()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.error("Failed to increment starts for %s: %s", service, exc)

    def increment_stops(self, service: str) -> None:
        """
        Increment the stops counter for a service.

        Args:
            service: Service name
        """
        if self.enabled and self.service_stops:
            try:
                self.service_stops.labels(service=service).inc()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.error("Failed to increment stops for %s: %s", service, exc)

    def increment_crashes(self, service: str) -> None:
        """
        Increment the crashes counter for a service.

        Args:
            service: Service name
        """
        if self.enabled and self.service_crashes:
            try:
                self.service_crashes.labels(service=service).inc()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.error("Failed to increment crashes for %s: %s", service, exc)

    def increment_restarts(self, service: str) -> None:
        """
        Increment the restarts counter for a service.

        Args:
            service: Service name
        """
        if self.enabled and self.service_restarts:
            try:
                self.service_restarts.labels(service=service).inc()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.error("Failed to increment restarts for %s: %s", service, exc)


# Global singleton instance
_metrics_instance: Optional[PrometheusMetrics] = None


def get_metrics() -> PrometheusMetrics:
    """
    Get the global PrometheusMetrics singleton instance.

    Returns:
        PrometheusMetrics instance
    """
    global _metrics_instance  # pylint: disable=global-statement
    if _metrics_instance is None:
        _metrics_instance = PrometheusMetrics()
    return _metrics_instance
