import pytest
import logging
import types
from unittest.mock import patch, MagicMock, mock_open, call
from systemd_monitor.systemd_monitor import (
    unescape_unit_name, DBusMonitor, StatsAnalyzer, SystemdMonitor
)
from systemd_monitor.config import Config

def test_unescape_unit_name():
    assert unescape_unit_name('wirepas_2d_gateway_2e_service') == 'wirepas-gateway.service'
    assert unescape_unit_name('edger_2e_connecteddev_2e_service') == 'edger.connecteddev.service'
    assert unescape_unit_name('foo') == 'foo.service'
    assert unescape_unit_name('') is None
    assert unescape_unit_name(None) is None

def test_dbusmonitor_log_event_filters(monkeypatch):
    config = Config()
    monitor = DBusMonitor(config)
    monitor.logger = MagicMock()
    # Should ignore invalid service
    monitor._log_event('-', 'active', 'running')
    monitor.logger.info.assert_not_called()
    # Should ignore non-monitored service
    monitor._log_event('notmonitored.service', 'active', 'running')
    monitor.logger.info.assert_not_called()
    # Should log valid monitored service
    monitor._log_event('wirepas-gateway.service', 'active', 'running')
    monitor.logger.info.assert_called()

def test_statsanalyzer_parse_logs(monkeypatch):
    log_content = "2025-05-19 12:00:00 - INFO - Service: wirepas-gateway.service, State: active, SubState: running, Source: signal\n"
    m = mock_open(read_data=log_content)
    with patch('builtins.open', m):
        config = Config()
        analyzer = StatsAnalyzer(config)
        events = analyzer._parse_logs('dummy.log')
        assert 'wirepas-gateway.service' in events
        assert events['wirepas-gateway.service'][0]['state'] == 'active'

def test_statsanalyzer_generate_statistics_prints(monkeypatch, capsys):
    log_content = "2025-05-19 12:00:00 - INFO - Service: wirepas-gateway.service, State: failed, SubState: failed, Source: signal\n"
    m = mock_open(read_data=log_content)
    with patch('builtins.open', m):
        config = Config()
        analyzer = StatsAnalyzer(config)
        analyzer.generate_statistics()
        out = capsys.readouterr().out
        assert "wirepas-gateway.service" in out
        assert "Crashes" in out

def test_systemdmonitor_threads(monkeypatch):
    # Patch DBusMonitor and StatsAnalyzer to avoid real threads
    with patch.object(DBusMonitor, 'start'), \
         patch.object(DBusMonitor, 'stop'), \
         patch.object(StatsAnalyzer, 'generate_statistics'):
        config = Config()
        monitor = SystemdMonitor(config)
        monitor.start()
        assert monitor.running
        monitor.stop()
        assert not monitor.running

def test_signal_handler(monkeypatch):
    # Patch sys.modules to inject a mock monitor into the module namespace
    import sys
    from systemd_monitor import systemd_monitor as sm
    fake_monitor = MagicMock()
    monkeypatch.setattr(sm, 'monitor', fake_monitor, raising=False)
    with patch('sys.exit') as exit_mock:
        sm.signal_handler(2, None)
        fake_monitor.stop.assert_called()
        fake_monitor.generate_stats.assert_called()
        exit_mock.assert_called()

def test_dbusmonitor_setup_logging(tmp_path):
    log_file = tmp_path / "test.log"
    config = Config(log_file=str(log_file), debug=True)
    monitor = DBusMonitor(config)
    assert monitor.logger.name == 'SystemdMonitor'
    assert monitor.logger.level == logging.DEBUG
    # Should create a file handler
    assert any(isinstance(h, logging.FileHandler) for h in monitor.logger.handlers)

def test_statsanalyzer_handles_missing_file():
    config = Config()
    analyzer = StatsAnalyzer(config)
    # Should not raise
    analyzer.generate_statistics()

def test_statsanalyzer_handles_invalid_line(capsys, tmp_path):
    log_file = tmp_path / "bad.log"
    log_file.write_text("not a log line\n")
    config = Config()
    analyzer = StatsAnalyzer(config)
    analyzer.generate_statistics()
    out = capsys.readouterr().out
    assert "Statistics from" in out

def test_config_defaults():
    """Test that Config provides correct defaults."""
    config = Config()
    assert 'wirepas-gateway.service' in config.monitored_services
    assert config.log_file == 'systemd_monitor.log'
    assert config.poll_interval == 100
    assert config.stats_interval == 60
    assert config.max_retries == 3
    assert config.debug is False

def test_config_custom_services():
    """Test that Config can be customized with different services."""
    custom_services = ['nginx.service', 'apache2.service']
    config = Config(monitored_services=custom_services)
    assert config.monitored_services == set(custom_services)

def test_config_file_loading(tmp_path):
    """Test loading configuration from file."""
    config_file = tmp_path / "test_config.json"
    config_data = {
        "monitored_services": ["test.service"],
        "log_file": "test.log",
        "debug": True
    }
    import json
    with open(config_file, 'w') as f:
        json.dump(config_data, f)
    
    config = Config(str(config_file))
    assert config.monitored_services == {"test.service"}
    assert config.log_file == "test.log"
    assert config.debug is True
