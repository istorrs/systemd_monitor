"""Unit tests for Prometheus metrics module."""

import sys
from unittest.mock import Mock, patch, MagicMock


# Mock prometheus_client before importing prometheus_metrics
mock_prometheus = Mock()
mock_gauge = Mock()
mock_counter = Mock()
mock_info = Mock()

# Create mock classes
mock_gauge_class = Mock(return_value=mock_gauge)
mock_counter_class = Mock(return_value=mock_counter)
mock_info_class = Mock(return_value=mock_info)
mock_start_http_server = Mock()

mock_prometheus.Gauge = mock_gauge_class
mock_prometheus.Counter = mock_counter_class
mock_prometheus.Info = mock_info_class
mock_prometheus.start_http_server = mock_start_http_server

sys.modules["prometheus_client"] = mock_prometheus

# Now import the module under test
# pylint: disable=wrong-import-position
from systemd_monitor.prometheus_metrics import (  # noqa: E402
    PrometheusMetrics,
    get_metrics,
    STATE_MAP,
)


class TestPrometheusMetrics:
    """Test PrometheusMetrics class."""

    def setup_method(self):
        """Reset mocks before each test."""
        mock_gauge.reset_mock()
        mock_counter.reset_mock()
        mock_info.reset_mock()
        mock_gauge_class.reset_mock()
        mock_counter_class.reset_mock()
        mock_info_class.reset_mock()
        mock_start_http_server.reset_mock()

    def test_initialization_success(self):
        """Test successful Prometheus metrics initialization."""
        metrics = PrometheusMetrics()

        assert metrics.enabled is True
        assert mock_gauge_class.call_count == 2  # service_state, service_last_change
        assert mock_counter_class.call_count == 4  # starts, stops, crashes, restarts
        assert mock_info_class.call_count == 1  # monitor_info

    def test_state_map_values(self):
        """Test STATE_MAP has expected values."""
        assert STATE_MAP["active"] == 1
        assert STATE_MAP["inactive"] == 0
        assert STATE_MAP["activating"] == 2
        assert STATE_MAP["deactivating"] == 3
        assert STATE_MAP["failed"] == -1
        assert STATE_MAP["unloaded"] == -2

    def test_start_http_server_success(self):
        """Test starting HTTP server successfully."""
        metrics = PrometheusMetrics()
        result = metrics.start_http_server(9100)

        assert result is True
        mock_start_http_server.assert_called_once_with(9100)

    def test_start_http_server_os_error(self):
        """Test handling OSError when starting HTTP server."""
        mock_start_http_server.side_effect = OSError("Port in use")
        metrics = PrometheusMetrics()
        result = metrics.start_http_server(9100)

        assert result is False
        mock_start_http_server.assert_called_once_with(9100)

    def test_start_http_server_when_disabled(self):
        """Test starting HTTP server when metrics disabled."""
        metrics = PrometheusMetrics()
        metrics.enabled = False
        result = metrics.start_http_server(9100)

        assert result is False
        mock_start_http_server.assert_not_called()

    def test_set_monitor_info(self):
        """Test setting monitor info metadata."""
        metrics = PrometheusMetrics()
        mock_info_instance = MagicMock()
        metrics.monitor_info = mock_info_instance

        metrics.set_monitor_info("1.0.0", ["service1.service", "service2.service"])

        mock_info_instance.info.assert_called_once()
        call_args = mock_info_instance.info.call_args[0][0]
        assert call_args["version"] == "1.0.0"
        assert call_args["monitored_services"] == "service1.service,service2.service"
        assert call_args["service_count"] == "2"

    def test_set_monitor_info_when_disabled(self):
        """Test setting monitor info when metrics disabled."""
        metrics = PrometheusMetrics()
        metrics.enabled = False
        mock_info_instance = MagicMock()
        metrics.monitor_info = mock_info_instance

        metrics.set_monitor_info("1.0.0", ["service1.service"])

        mock_info_instance.info.assert_not_called()

    def test_update_service_state(self):
        """Test updating service state gauge."""
        metrics = PrometheusMetrics()
        mock_gauge_instance = MagicMock()
        mock_labels = MagicMock()
        mock_gauge_instance.labels.return_value = mock_labels
        metrics.service_state = mock_gauge_instance

        mock_timestamp_gauge = MagicMock()
        mock_timestamp_labels = MagicMock()
        mock_timestamp_gauge.labels.return_value = mock_timestamp_labels
        metrics.service_last_change = mock_timestamp_gauge

        metrics.update_service_state("test.service", "active", 1234567890.0)

        mock_gauge_instance.labels.assert_called_once_with(service="test.service")
        mock_labels.set.assert_called_once_with(1)  # active = 1

        mock_timestamp_gauge.labels.assert_called_once_with(service="test.service")
        mock_timestamp_labels.set.assert_called_once_with(1234567890.0)

    def test_update_service_state_unknown(self):
        """Test updating service state with unknown state."""
        metrics = PrometheusMetrics()
        mock_gauge_instance = MagicMock()
        mock_labels = MagicMock()
        mock_gauge_instance.labels.return_value = mock_labels
        metrics.service_state = mock_gauge_instance
        metrics.service_last_change = MagicMock()

        metrics.update_service_state("test.service", "unknown_state", 1234567890.0)

        # Unknown state should map to -99
        mock_labels.set.assert_called_once_with(-99)

    def test_update_service_state_when_disabled(self):
        """Test updating service state when metrics disabled."""
        metrics = PrometheusMetrics()
        metrics.enabled = False
        mock_gauge_instance = MagicMock()
        metrics.service_state = mock_gauge_instance

        metrics.update_service_state("test.service", "active", 1234567890.0)

        mock_gauge_instance.labels.assert_not_called()

    def test_increment_starts(self):
        """Test incrementing starts counter."""
        metrics = PrometheusMetrics()
        mock_counter_instance = MagicMock()
        mock_labels = MagicMock()
        mock_counter_instance.labels.return_value = mock_labels
        metrics.service_starts = mock_counter_instance

        metrics.increment_starts("test.service")

        mock_counter_instance.labels.assert_called_once_with(service="test.service")
        mock_labels.inc.assert_called_once()

    def test_increment_stops(self):
        """Test incrementing stops counter."""
        metrics = PrometheusMetrics()
        mock_counter_instance = MagicMock()
        mock_labels = MagicMock()
        mock_counter_instance.labels.return_value = mock_labels
        metrics.service_stops = mock_counter_instance

        metrics.increment_stops("test.service")

        mock_counter_instance.labels.assert_called_once_with(service="test.service")
        mock_labels.inc.assert_called_once()

    def test_increment_crashes(self):
        """Test incrementing crashes counter."""
        metrics = PrometheusMetrics()
        mock_counter_instance = MagicMock()
        mock_labels = MagicMock()
        mock_counter_instance.labels.return_value = mock_labels
        metrics.service_crashes = mock_counter_instance

        metrics.increment_crashes("test.service")

        mock_counter_instance.labels.assert_called_once_with(service="test.service")
        mock_labels.inc.assert_called_once()

    def test_increment_restarts(self):
        """Test incrementing restarts counter."""
        metrics = PrometheusMetrics()
        mock_counter_instance = MagicMock()
        mock_labels = MagicMock()
        mock_counter_instance.labels.return_value = mock_labels
        metrics.service_restarts = mock_counter_instance

        metrics.increment_restarts("test.service")

        mock_counter_instance.labels.assert_called_once_with(service="test.service")
        mock_labels.inc.assert_called_once()

    def test_increment_when_disabled(self):
        """Test incrementing counters when metrics disabled."""
        metrics = PrometheusMetrics()
        metrics.enabled = False
        mock_counter_instance = MagicMock()
        metrics.service_starts = mock_counter_instance

        metrics.increment_starts("test.service")

        mock_counter_instance.labels.assert_not_called()

    def test_get_metrics_singleton(self):
        """Test get_metrics returns singleton instance."""
        # Clear any existing instance
        # pylint: disable=import-outside-toplevel
        import systemd_monitor.prometheus_metrics as prom_module

        prom_module._metrics_instance = None  # pylint: disable=protected-access

        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2


class TestPrometheusMetricsUnavailable:
    """Test PrometheusMetrics when prometheus_client is unavailable."""

    def test_initialization_without_prometheus_client(self):
        """Test initialization when prometheus_client not available."""
        # Create a new instance with PROMETHEUS_AVAILABLE = False
        with patch("systemd_monitor.prometheus_metrics.PROMETHEUS_AVAILABLE", False):
            metrics = PrometheusMetrics()

            assert metrics.enabled is False
            assert metrics.service_state is None
            assert metrics.service_starts is None

    def test_operations_when_unavailable(self):
        """Test operations don't crash when prometheus_client unavailable."""
        with patch("systemd_monitor.prometheus_metrics.PROMETHEUS_AVAILABLE", False):
            metrics = PrometheusMetrics()

            # These should not crash
            result = metrics.start_http_server(9100)
            assert result is False

            metrics.update_service_state("test.service", "active", 1234567890.0)
            metrics.increment_starts("test.service")
            metrics.increment_stops("test.service")
            metrics.increment_crashes("test.service")
            metrics.increment_restarts("test.service")
            metrics.set_monitor_info("1.0.0", ["test.service"])


class TestPrometheusMetricsExceptions:
    """Test exception handling in PrometheusMetrics."""

    def test_initialization_exception(self):
        """Test handling exceptions during initialization."""
        with patch(
            "systemd_monitor.prometheus_metrics.Gauge",
            side_effect=Exception("Init error"),
        ):
            metrics = PrometheusMetrics()
            assert metrics.enabled is False

    def test_update_service_state_exception(self):
        """Test handling exceptions in update_service_state."""
        metrics = PrometheusMetrics()
        mock_gauge_instance = MagicMock()
        mock_gauge_instance.labels.side_effect = Exception("Update error")
        metrics.service_state = mock_gauge_instance

        # Should not crash
        metrics.update_service_state("test.service", "active", 1234567890.0)

    def test_increment_exception(self):
        """Test handling exceptions in increment methods."""
        metrics = PrometheusMetrics()
        mock_counter_instance = MagicMock()
        mock_counter_instance.labels.side_effect = Exception("Increment error")
        metrics.service_starts = mock_counter_instance

        # Should not crash
        metrics.increment_starts("test.service")

    def test_set_monitor_info_exception(self):
        """Test handling exceptions in set_monitor_info."""
        metrics = PrometheusMetrics()
        mock_info_instance = MagicMock()
        mock_info_instance.info.side_effect = Exception("Info error")
        metrics.monitor_info = mock_info_instance

        # Should not crash
        metrics.set_monitor_info("1.0.0", ["test.service"])
