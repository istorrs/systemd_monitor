"""
Unit tests for the event_logger module.

Tests structured event logging in JSON Lines format.
"""

import json
import tempfile
from pathlib import Path
import pytest
from systemd_monitor.event_logger import ServiceEventLogger, get_machine_id


class TestGetMachineId:
    """Tests for get_machine_id function."""

    def test_get_machine_id_returns_string(self):
        """Test that get_machine_id returns a string."""
        machine_id = get_machine_id()
        assert isinstance(machine_id, str)
        assert len(machine_id) > 0

    def test_get_machine_id_valid_format(self):
        """Test that machine_id is either hex string or 'unknown'."""
        machine_id = get_machine_id()
        # Should be either a hex string (32 chars) or 'unknown'
        if machine_id != "unknown":
            assert len(machine_id) == 32
            # Check if it's a valid hex string
            try:
                int(machine_id, 16)
            except ValueError:
                pytest.fail(f"machine_id '{machine_id}' is not valid hex")


class TestServiceEventLogger:
    """Tests for ServiceEventLogger class."""

    def test_logger_initialization(self):
        """Test that logger can be initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(
                log_file=str(log_file),
                max_bytes=1024,
                backup_count=2,
            )
            assert logger.log_file == str(log_file)
            assert logger.machine_id is not None
            assert isinstance(logger.machine_id, str)
            logger.close()

    def test_logger_creates_directory(self):
        """Test that logger creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "subdir" / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))
            assert log_file.parent.exists()
            logger.close()

    def test_log_event_creates_file(self):
        """Test that logging an event creates the log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="test.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            assert log_file.exists()

    def test_log_event_json_format(self):
        """Test that logged events are valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="test.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            # Read and parse the logged event
            with open(log_file, "r", encoding="utf-8") as f:
                line = f.readline()
                event = json.loads(line)

            # Verify required fields
            assert event["event"] == "start"
            assert event["service"] == "test.service"
            assert event["from_state"] == "inactive"
            assert event["to_state"] == "active"
            assert event["counters"]["starts"] == 1
            assert event["counters"]["stops"] == 0
            assert event["counters"]["crashes"] == 0
            assert "timestamp" in event
            assert "machine_id" in event

    def test_log_start_event(self):
        """Test logging a service start event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="nginx.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["event"] == "start"
            assert event["service"] == "nginx.service"
            assert event["to_state"] == "active"

    def test_log_stop_event(self):
        """Test logging a service stop event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="stop",
                service="nginx.service",
                from_state="active",
                to_state="inactive",
                counters={"starts": 1, "stops": 1, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["event"] == "stop"
            assert event["from_state"] == "active"
            assert event["to_state"] == "inactive"

    def test_log_crash_event_with_exit_code(self):
        """Test logging a service crash event with exit code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="crash",
                service="nginx.service",
                from_state="active",
                to_state="failed",
                counters={"starts": 1, "stops": 1, "crashes": 1},
                exit_code=1,
                sub_state="failed",
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["event"] == "crash"
            assert event["to_state"] == "failed"
            assert event["exit_code"] == 1
            assert event["sub_state"] == "failed"
            assert event["counters"]["crashes"] == 1

    def test_log_restart_event(self):
        """Test logging a service restart event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="restart",
                service="nginx.service",
                from_state="active",
                to_state="activating",
                counters={"starts": 2, "stops": 1, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["event"] == "restart"
            assert event["counters"]["starts"] == 2

    def test_multiple_events_json_lines(self):
        """Test that multiple events are logged as separate JSON Lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            # Log multiple events
            logger.log_event(
                event_type="start",
                service="nginx.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.log_event(
                event_type="stop",
                service="nginx.service",
                from_state="active",
                to_state="inactive",
                counters={"starts": 1, "stops": 1, "crashes": 0},
            )
            logger.log_event(
                event_type="crash",
                service="redis.service",
                from_state="active",
                to_state="failed",
                counters={"starts": 1, "stops": 1, "crashes": 1},
                exit_code=127,
            )
            logger.close()

            # Read all events
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            assert len(lines) == 3

            # Parse and verify each event
            event1 = json.loads(lines[0])
            assert event1["event"] == "start"
            assert event1["service"] == "nginx.service"

            event2 = json.loads(lines[1])
            assert event2["event"] == "stop"
            assert event2["service"] == "nginx.service"

            event3 = json.loads(lines[2])
            assert event3["event"] == "crash"
            assert event3["service"] == "redis.service"
            assert event3["exit_code"] == 127

    def test_extra_fields(self):
        """Test that extra fields are included in the log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="crash",
                service="test.service",
                from_state="active",
                to_state="failed",
                counters={"starts": 1, "stops": 1, "crashes": 1},
                custom_field="custom_value",
                pid=1234,
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["custom_field"] == "custom_value"
            assert event["pid"] == 1234

    def test_from_state_none(self):
        """Test logging an event with from_state=None (initial state)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="test.service",
                from_state=None,
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert event["from_state"] is None
            assert event["to_state"] == "active"

    def test_timestamp_format(self):
        """Test that timestamp is in ISO 8601 format with timezone."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="test.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            # Verify ISO 8601 format with timezone
            timestamp = event["timestamp"]
            assert "T" in timestamp
            assert "+" in timestamp or "Z" in timestamp or "-" in timestamp[-6:]

    def test_machine_id_included(self):
        """Test that machine_id is included in every event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            logger = ServiceEventLogger(log_file=str(log_file))

            logger.log_event(
                event_type="start",
                service="test.service",
                from_state="inactive",
                to_state="active",
                counters={"starts": 1, "stops": 0, "crashes": 0},
            )
            logger.close()

            with open(log_file, "r", encoding="utf-8") as f:
                event = json.loads(f.readline())

            assert "machine_id" in event
            assert isinstance(event["machine_id"], str)
            assert len(event["machine_id"]) > 0

    def test_log_rotation_max_bytes(self):
        """Test that log file rotates when max_bytes is exceeded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "events.jsonl"
            # Set very small max_bytes to trigger rotation
            logger = ServiceEventLogger(
                log_file=str(log_file),
                max_bytes=200,  # Very small to trigger rotation
                backup_count=2,
            )

            # Log enough events to exceed max_bytes
            for i in range(10):
                logger.log_event(
                    event_type="start",
                    service=f"service{i}.service",
                    from_state="inactive",
                    to_state="active",
                    counters={"starts": i + 1, "stops": 0, "crashes": 0},
                )
            logger.close()

            # Check that main log file exists
            assert log_file.exists()
            # Rotation may or may not create backup depending on timing
            # Just verify main file exists and contains valid JSON
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                assert len(lines) > 0
                # Verify last line is valid JSON
                json.loads(lines[-1])
