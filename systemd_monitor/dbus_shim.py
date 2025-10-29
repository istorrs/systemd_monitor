"""
D-Bus compatibility shim using Jeepney.

This module provides a compatibility layer that mimics the dbus-python API
using Jeepney, a pure-Python D-Bus implementation. This allows the systemd
monitor to run on systems without C compilers where dbus-python cannot be
installed.

The API is designed to be a drop-in replacement for the subset of dbus-python used by
systemd_monitor.py, including:
- SystemBus()
- get_object()
- Interface()
- connect_to_signal()
- PropertiesChanged signals
- Exception classes

Performance: ~5-10x slower than dbus-python but sufficient for systemd monitoring.
"""

import logging
import threading
from queue import Queue, Empty
from typing import Callable, Optional, Dict, Any

try:
    from jeepney import DBusAddress, new_method_call, MatchRule, HeaderFields
    from jeepney.bus_messages import message_bus

    JEEPNEY_AVAILABLE = True
except ImportError:
    JEEPNEY_AVAILABLE = False

LOGGER = logging.getLogger(__name__)

# Constants for systemd D-Bus interface
SYSTEMD_DBUS_SERVICE = "org.freedesktop.systemd1"
SYSTEMD_DBUS_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
SYSTEMD_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


class DBusException(Exception):
    """D-Bus exception compatible with dbus-python."""


class _DBusExceptionsModule:  # pylint: disable=too-few-public-methods
    """Mock dbus.exceptions module for compatibility."""

    DBusException = DBusException


class _SystemBus:  # pylint: disable=too-many-instance-attributes
    """
    D-Bus system bus connection using Jeepney.

    Provides a compatibility layer matching dbus.SystemBus() API.
    Uses DBusRouter with built-in receiver thread for signal handling.
    """

    def __init__(self):
        """Initialize system bus connection with DBusRouter."""
        if not JEEPNEY_AVAILABLE:
            raise ImportError(
                "Jeepney not installed. Install with: pip install jeepney"
            )

        # Open D-Bus router (connection + receiver thread)
        # Note: We can't use context manager since we need long-lived connection
        # pylint: disable=import-outside-toplevel
        from jeepney.io.threading import open_dbus_connection, DBusRouter

        self.conn = open_dbus_connection(bus="SYSTEM")
        self.router = DBusRouter(self.conn)

        # Subscriptions: service_name -> callback
        self.subscriptions: Dict[str, Callable] = {}
        self.subscriptions_lock = threading.Lock()

        # Signal queue for PropertiesChanged signals
        self.signal_queue: Queue = Queue()

        # Subscribe to all PropertiesChanged signals from systemd units
        self._setup_signal_filter()

        # Dispatcher thread to process signals
        self._running = True
        self._thread = threading.Thread(target=self._signal_dispatcher, daemon=True)
        self._thread.start()

        LOGGER.info("Jeepney D-Bus shim initialized with DBusRouter")

    def get_object(self, bus_name: str, object_path: str) -> "ProxyObject":
        """
        Get a proxy object for a D-Bus object.

        Args:
            bus_name: D-Bus service name (e.g., 'org.freedesktop.systemd1')
            object_path: Object path (e.g., '/org/freedesktop/systemd1')

        Returns:
            ProxyObject that can be used to interact with the D-Bus object
        """
        return ProxyObject(self.router, bus_name, object_path, self)

    def close(self):
        """Clean shutdown of router and connection."""
        self._running = False
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if hasattr(self, "router"):
            try:
                self.router.close()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.debug("Error closing D-Bus router: %s", exc)
        if hasattr(self, "conn"):
            try:
                self.conn.close()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.debug("Error closing D-Bus connection: %s", exc)
        LOGGER.info("Jeepney D-Bus shim shut down")

    def _setup_signal_filter(self):
        """Set up filter for PropertiesChanged signals from systemd units."""
        # Create match rule for PropertiesChanged signals
        rule = MatchRule(
            type="signal",
            interface=SYSTEMD_PROPERTIES_INTERFACE,
            member="PropertiesChanged",
            path_namespace="/org/freedesktop/systemd1/unit",
        )

        # Subscribe to signals on D-Bus using message_bus
        # pylint: disable=import-outside-toplevel
        from jeepney.io.threading import Proxy

        bus_proxy = Proxy(message_bus, self.router)
        bus_proxy.AddMatch(rule)
        LOGGER.debug("Subscribed to PropertiesChanged signals via message_bus.AddMatch")

        # Create filter that routes matching messages to our queue
        self._filter_handle = self.router.filter(rule, queue=self.signal_queue)

    def _escape_unit(self, name: str) -> str:
        """Escape systemd unit name for D-Bus path."""
        # Systemd unit name escaping rules (order matters!)
        result = name
        for char, escaped in [("_", "_5f"), (".", "_2e"), ("-", "_2d"), ("/", "_2f")]:
            result = result.replace(char, escaped)
        return result

    def _unescape_unit(self, escaped: str) -> str:
        """Unescape systemd unit name from D-Bus path."""
        result = escaped
        # Unescape in reverse order to handle overlapping patterns
        for escaped_str, char in [
            ("_2f", "/"),
            ("_2d", "-"),
            ("_2e", "."),
            ("_5f", "_"),
        ]:
            result = result.replace(escaped_str, char)
        return result

    def _process_properties_changed(self, msg, path: str):
        """Process PropertiesChanged signal."""
        # Extract unit name from path
        if "/unit/" not in path:
            LOGGER.debug(
                "Ignoring PropertiesChanged: path doesn't contain /unit/: %s", path
            )
            return

        unit_name_escaped = path.split("/")[-1]
        service_name = self._unescape_unit(unit_name_escaped)

        LOGGER.debug(
            "Processing PropertiesChanged for %s (escaped: %s)",
            service_name,
            unit_name_escaped,
        )

        # Thread-safe callback lookup
        with self.subscriptions_lock:
            callback = self.subscriptions.get(service_name)
            registered_services = list(self.subscriptions.keys())

        if not callback:
            LOGGER.warning(
                "No callback found for %s. Registered services: %s",
                service_name,
                registered_services,
            )
            return

        # Extract signal body
        changed_interface = msg.body[0] if len(msg.body) > 0 else ""
        changed = msg.body[1] if len(msg.body) > 1 else {}
        invalidated = msg.body[2] if len(msg.body) > 2 else []

        LOGGER.debug(
            "Calling callback for %s: interface=%s, changed=%s",
            service_name,
            changed_interface,
            list(changed.keys()) if changed else [],
        )

        # Call callback
        try:
            callback(changed_interface, changed, invalidated)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.error(
                "Error in callback for %s: %s", service_name, exc, exc_info=True
            )

    def _signal_dispatcher(self):
        """Background thread: reads signals from queue and dispatches to callbacks."""
        LOGGER.info("Signal dispatcher thread started")
        message_count = 0
        while self._running:
            try:
                # Wait for signal with timeout to allow clean shutdown
                msg = self.signal_queue.get(timeout=0.1)
                message_count += 1

                # Extract signal information from Jeepney message header
                # Jeepney stores header fields in msg.header.fields dict
                path = msg.header.fields.get(HeaderFields.path, "")
                interface = msg.header.fields.get(HeaderFields.interface, "")
                member = msg.header.fields.get(HeaderFields.member, "")

                LOGGER.debug(
                    "Signal dispatcher received message #%d: "
                    "path=%s, interface=%s, member=%s",
                    message_count,
                    path,
                    interface,
                    member,
                )

                # Handle PropertiesChanged signals
                if (
                    member == "PropertiesChanged"
                    and interface == SYSTEMD_PROPERTIES_INTERFACE
                ):
                    self._process_properties_changed(msg, path)
                else:
                    LOGGER.debug("Ignoring signal: %s.%s", interface, member)

            except Empty:
                # Timeout - continue loop to check _running flag
                continue
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if self._running:  # Only log if not shutting down
                    LOGGER.error("Signal dispatcher error: %s", exc, exc_info=True)
        LOGGER.info(
            "Signal dispatcher thread exiting (received %d messages)", message_count
        )


class ProxyObject:  # pylint: disable=too-few-public-methods
    """
    Proxy object for D-Bus objects.

    Provides connect_to_signal() method matching dbus-python API.
    """

    def __init__(
        self, router, bus_name: str, object_path: str, bus_instance: "_SystemBus"
    ):
        """Initialize proxy object.

        Args:
            router: DBusRouter instance for D-Bus communication
            bus_name: D-Bus service name
            object_path: D-Bus object path
            bus_instance: Reference to parent _SystemBus instance
        """
        self.router = router
        self.bus_name = bus_name
        self.object_path = object_path
        self.bus_instance = bus_instance
        self.bus = bus_instance

    def connect_to_signal(
        self,
        signal_name: str,
        handler_function: Callable,
        dbus_interface: Optional[str] = None,  # pylint: disable=unused-argument
    ):
        """
        Subscribe to D-Bus signal.

        Args:
            signal_name: Name of signal (e.g., 'PropertiesChanged')
            handler_function: Callback function to call when signal received
            dbus_interface: D-Bus interface name (optional)
        """
        if signal_name != "PropertiesChanged":
            LOGGER.warning("Unsupported signal: %s", signal_name)
            return

        unit_name = self._extract_unit_name()
        if not unit_name:
            LOGGER.error("Cannot extract unit name from path: %s", self.object_path)
            return

        # Register callback (thread-safe)
        # The global signal filter in _setup_signal_filter already subscribes to all
        # PropertiesChanged signals, so we just need to register the callback
        with self.bus.subscriptions_lock:
            self.bus.subscriptions[unit_name] = handler_function

        LOGGER.debug("Registered callback for PropertiesChanged on %s", unit_name)

    def _extract_unit_name(self) -> Optional[str]:
        """Extract unit name from D-Bus object path."""
        if not self.object_path.startswith("/org/freedesktop/systemd1/unit/"):
            return None
        escaped = self.object_path.split("/")[-1]
        return self.bus._unescape_unit(escaped)  # pylint: disable=protected-access


class Interface:
    """
    D-Bus interface wrapper.

    Provides method call interface matching dbus.Interface API.
    """

    def __init__(self, proxy_obj: ProxyObject, interface_name: str):
        """Initialize interface wrapper."""
        self.proxy_obj = proxy_obj
        self.interface_name = interface_name

    def __getattr__(self, method_name: str) -> Callable:
        """
        Dynamic method call wrapper.

        Returns a callable that makes D-Bus method calls.
        """

        def method_call(*args):
            """Make D-Bus method call."""
            try:
                # Determine signature based on arguments
                if not args:
                    signature = ""
                elif len(args) == 1 and isinstance(args[0], str):
                    signature = "s"
                else:
                    # Default to string array
                    signature = "s" * len(args)

                LOGGER.debug(
                    "D-Bus call: %s.%s(%s) [sig=%s] on %s",
                    self.interface_name,
                    method_name,
                    args,
                    signature,
                    self.proxy_obj.object_path,
                )

                msg = new_method_call(
                    DBusAddress(
                        self.proxy_obj.object_path,
                        bus_name=self.proxy_obj.bus_name,
                        interface=self.interface_name,
                    ),
                    method_name,
                    signature,
                    args if args else (),
                )

                LOGGER.debug("Sending D-Bus message, waiting for reply...")
                # DBusRouter.send_and_get_reply() is thread-safe
                reply = self.proxy_obj.router.send_and_get_reply(msg)
                LOGGER.debug("Received D-Bus reply: body=%s", reply.body)

                # Return empty tuple for void methods, single value for single returns,
                # or full tuple for multiple returns
                if not reply.body:
                    return ()  # Void method
                if len(reply.body) == 1:
                    return reply.body[0]  # Single return value
                return reply.body  # Multiple return values
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.error(
                    "D-Bus call failed: %s.%s - %s",
                    self.interface_name,
                    method_name,
                    exc,
                )
                raise DBusException(f"{method_name} failed: {exc}") from exc

        return method_call

    def Get(  # pylint: disable=invalid-name
        self, interface: str, property_name: str
    ) -> Any:
        """
        Get a D-Bus property value.

        Matches D-Bus naming convention (Get not get).

        Args:
            interface: Interface name containing the property
            property_name: Name of the property to get

        Returns:
            Property value
        """
        try:
            msg = new_method_call(
                DBusAddress(
                    self.proxy_obj.object_path,
                    bus_name=self.proxy_obj.bus_name,
                    interface="org.freedesktop.DBus.Properties",
                ),
                "Get",
                "ss",
                (interface, property_name),
            )
            # DBusRouter.send_and_get_reply() is thread-safe
            reply = self.proxy_obj.router.send_and_get_reply(msg)

            # D-Bus Properties.Get returns a variant - unwrap it
            result = reply.body[0] if reply.body else None
            # Unwrap variant tuples: ('i', 5) or (5,) → 5
            while isinstance(result, tuple) and len(result) <= 2:
                if len(result) == 2:
                    # Format: (signature, value)
                    result = result[1]
                elif len(result) == 1:
                    # Format: (value,)
                    result = result[0]
                else:
                    break
            return result
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise DBusException(f"Get property failed: {exc}") from exc


# Module-level singleton
# pylint: disable=invalid-name
_GLOBAL_BUS: Optional[_SystemBus] = None
_GLOBAL_BUS_LOCK = threading.Lock()


def get_system_bus() -> _SystemBus:
    """
    Get singleton system bus instance.

    Returns:
        _SystemBus singleton instance
    """
    global _GLOBAL_BUS  # pylint: disable=global-statement
    if _GLOBAL_BUS is None:
        with _GLOBAL_BUS_LOCK:
            if _GLOBAL_BUS is None:  # Double-check after acquiring lock
                _GLOBAL_BUS = _SystemBus()
    return _GLOBAL_BUS


# Create module-level objects for compatibility
class exceptions:  # pylint: disable=invalid-name,too-few-public-methods
    """Mock dbus.exceptions module."""

    DBusException = DBusException


# Compatibility function
def SystemBus() -> _SystemBus:  # pylint: disable=invalid-name
    """
    Get system bus connection (dbus-python compatibility).

    Returns:
        _SystemBus instance
    """
    return get_system_bus()
