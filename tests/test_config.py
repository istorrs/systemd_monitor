"""
Unit tests for config module.
"""

# pylint: disable=import-error
import os
import json
import tempfile
from unittest.mock import patch
import pytest

from systemd_monitor import config


class TestConfigDefaults:
    """Test Config class default values."""

    def test_default_config_values(self):
        """Test that Config initializes with correct defaults."""
        cfg = config.Config()

        assert "wirepas-gateway.service" in cfg.monitored_services
        assert cfg.log_file == "systemd_monitor.log"
        assert cfg.poll_interval == 100
        assert cfg.stats_interval == 60
        assert cfg.max_retries == 3
        assert cfg.debug is False

    def test_default_services_list(self):
        """Test that default services list contains expected services."""
        cfg = config.Config()

        # Check some expected services
        expected_services = [
            "wirepas-gateway.service",
            "mosquitto.service",
            "devmgmt.service",
        ]
        for service in expected_services:
            assert service in cfg.monitored_services

    def test_monitored_services_returns_set(self):
        """Test that monitored_services property returns a set."""
        cfg = config.Config()
        assert isinstance(cfg.monitored_services, set)


class TestConfigFromKwargs:
    """Test Config initialization from keyword arguments."""

    def test_custom_log_file(self):
        """Test setting custom log file path."""
        cfg = config.Config(log_file="/custom/path/test.log")
        assert cfg.log_file == "/custom/path/test.log"

    def test_custom_debug_mode(self):
        """Test enabling debug mode."""
        cfg = config.Config(debug=True)
        assert cfg.debug is True

    def test_custom_poll_interval(self):
        """Test setting custom poll interval."""
        cfg = config.Config(poll_interval=200)
        assert cfg.poll_interval == 200

    def test_custom_stats_interval(self):
        """Test setting custom stats interval."""
        cfg = config.Config(stats_interval=120)
        assert cfg.stats_interval == 120

    def test_custom_max_retries(self):
        """Test setting custom max retries."""
        cfg = config.Config(max_retries=5)
        assert cfg.max_retries == 5

    def test_custom_monitored_services(self):
        """Test setting custom monitored services."""
        custom_services = ["nginx.service", "apache2.service"]
        cfg = config.Config(monitored_services=custom_services)
        assert cfg.monitored_services == set(custom_services)

    def test_multiple_kwargs(self):
        """Test setting multiple configuration values via kwargs."""
        cfg = config.Config(
            log_file="/tmp/test.log", debug=True, poll_interval=500, max_retries=10
        )
        assert cfg.log_file == "/tmp/test.log"
        assert cfg.debug is True
        assert cfg.poll_interval == 500
        assert cfg.max_retries == 10

    def test_unknown_kwargs_ignored(self):
        """Test that unknown kwargs are ignored."""
        cfg = config.Config(unknown_param="value")
        # Should not raise an error
        assert cfg.log_file == "systemd_monitor.log"  # Default value


class TestConfigFromFile:
    """Test Config initialization from configuration file."""

    def test_load_from_valid_file(self):
        """Test loading configuration from a valid JSON file."""
        config_data = {
            "monitored_services": ["test1.service", "test2.service"],
            "log_file": "/var/log/test.log",
            "debug": True,
            "poll_interval": 250,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            cfg = config.Config(config_file=config_file)
            assert cfg.monitored_services == {"test1.service", "test2.service"}
            assert cfg.log_file == "/var/log/test.log"
            assert cfg.debug is True
            assert cfg.poll_interval == 250
        finally:
            os.unlink(config_file)

    def test_load_from_nonexistent_file(self):
        """Test that nonexistent config file is handled gracefully."""
        cfg = config.Config(config_file="/nonexistent/file.json")
        # Should use defaults
        assert cfg.log_file == "systemd_monitor.log"

    def test_load_from_invalid_json(self):
        """Test that invalid JSON in config file raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content {")
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                config.Config(config_file=config_file)
            assert "Failed to load config file" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_kwargs_override_file_config(self):
        """Test that kwargs override values from config file."""
        config_data = {"log_file": "/file/path.log", "debug": False}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            cfg = config.Config(
                config_file=config_file, debug=True, log_file="/override/path.log"
            )
            # Kwargs should override file config
            assert cfg.debug is True
            assert cfg.log_file == "/override/path.log"
        finally:
            os.unlink(config_file)


class TestSaveConfig:
    """Test saving configuration to file."""

    def test_save_config_creates_file(self):
        """Test that save_config creates a new file."""
        cfg = config.Config(log_file="/test/log.log", debug=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            config_file = f.name

        try:
            cfg.save_config(config_file)
            assert os.path.exists(config_file)

            # Verify content
            with open(config_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            assert saved_data["log_file"] == "/test/log.log"
            assert saved_data["debug"] is True
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)

    def test_save_config_handles_io_error(self):
        """Test that save_config handles IOError."""
        cfg = config.Config()

        with pytest.raises(ValueError) as exc_info:
            cfg.save_config("/invalid/path/that/does/not/exist/config.json")
        assert "Failed to save config file" in str(exc_info.value)

    def test_save_and_load_roundtrip(self):
        """Test that saving and loading preserves configuration."""
        original_cfg = config.Config(
            log_file="/custom/path.log",
            debug=True,
            poll_interval=999,
            monitored_services=["service1.service", "service2.service"],
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            config_file = f.name

        try:
            original_cfg.save_config(config_file)
            loaded_cfg = config.Config(config_file=config_file)

            assert loaded_cfg.log_file == "/custom/path.log"
            assert loaded_cfg.debug is True
            assert loaded_cfg.poll_interval == 999
            assert loaded_cfg.monitored_services == {
                "service1.service",
                "service2.service",
            }
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)


class TestParseArguments:
    """Test command-line argument parsing."""

    def test_parse_debug_flag(self):
        """Test parsing --debug flag."""
        with patch("sys.argv", ["prog", "--debug"]):
            cfg = config.parse_arguments()
            assert cfg.debug is True

    def test_parse_log_file(self):
        """Test parsing --log-file argument."""
        with patch("sys.argv", ["prog", "--log-file", "/tmp/custom.log"]):
            cfg = config.parse_arguments()
            assert cfg.log_file == "/tmp/custom.log"

    def test_parse_config_file(self):
        """Test parsing --config argument."""
        config_data = {"debug": True}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with patch("sys.argv", ["prog", "--config", config_file]):
                cfg = config.parse_arguments()
                assert cfg.debug is True
        finally:
            os.unlink(config_file)

    def test_parse_services_list(self):
        """Test parsing --services argument."""
        with patch("sys.argv", ["prog", "--services", "svc1.service", "svc2.service"]):
            cfg = config.parse_arguments()
            assert cfg.monitored_services == {"svc1.service", "svc2.service"}

    def test_parse_poll_interval(self):
        """Test parsing --poll-interval argument."""
        with patch("sys.argv", ["prog", "--poll-interval", "500"]):
            cfg = config.parse_arguments()
            assert cfg.poll_interval == 500

    def test_parse_stats_interval(self):
        """Test parsing --stats-interval argument."""
        with patch("sys.argv", ["prog", "--stats-interval", "120"]):
            cfg = config.parse_arguments()
            assert cfg.stats_interval == 120

    def test_create_config_returns_none(self):
        """Test that --create-config returns None."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            config_file = f.name

        try:
            with patch("sys.argv", ["prog", "--create-config", config_file]):
                cfg = config.parse_arguments()
                assert cfg is None
                assert os.path.exists(config_file)
        finally:
            if os.path.exists(config_file):
                os.unlink(config_file)

    def test_parse_multiple_arguments(self):
        """Test parsing multiple arguments together."""
        with patch(
            "sys.argv",
            [
                "prog",
                "--debug",
                "--log-file",
                "/tmp/test.log",
                "--poll-interval",
                "300",
            ],
        ):
            cfg = config.parse_arguments()
            assert cfg.debug is True
            assert cfg.log_file == "/tmp/test.log"
            assert cfg.poll_interval == 300


class TestConfigProperties:
    """Test Config class properties."""

    def test_all_properties_accessible(self):
        """Test that all configuration properties are accessible."""
        cfg = config.Config()

        # Should not raise AttributeError
        _ = cfg.monitored_services
        _ = cfg.log_file
        _ = cfg.poll_interval
        _ = cfg.stats_interval
        _ = cfg.max_retries
        _ = cfg.debug

    def test_properties_return_correct_types(self):
        """Test that properties return expected types."""
        cfg = config.Config()

        assert isinstance(cfg.monitored_services, set)
        assert isinstance(cfg.log_file, str)
        assert isinstance(cfg.poll_interval, int)
        assert isinstance(cfg.stats_interval, int)
        assert isinstance(cfg.max_retries, int)
        assert isinstance(cfg.debug, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
