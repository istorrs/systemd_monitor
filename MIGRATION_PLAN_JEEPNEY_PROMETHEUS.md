# Migration Plan: Jeepney + Prometheus

> **⚠️ HISTORICAL DOCUMENT**
>
> This document was written during the planning phase in October 2024.
> **The migration to Jeepney has been COMPLETED** as of October 2025.
>
> The package now uses:
> - ✅ Jeepney (pure Python D-Bus) - 100% complete
> - ✅ Prometheus metrics - 100% complete
> - ✅ No C dependencies (dbus-python/PyGObject removed)
>
> This document is retained for historical reference only.

---

## Executive Summary

**Question:** Can Jeepney be a drop-in replacement for dbus-python?

**Answer:** ❌ **NO - Not a drop-in replacement**

Jeepney requires **significant architectural changes** because:
1. No GLib.MainLoop support (uses asyncio or blocking I/O)
2. Different signal handling paradigm
3. Different API surface (not compatible with dbus-python)

**Recommendation:** Evaluate if benefits outweigh the ~1000+ lines of code rewrite.

---

## Part 1: Jeepney Analysis

### Current Architecture (dbus-python)

```python
# GLib event loop integration
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
main_loop = GLib.MainLoop()

# Automatic signal handling
unit_obj.connect_to_signal(
    "PropertiesChanged",
    callback_function,
    dbus_interface="org.freedesktop.DBus.Properties"
)

main_loop.run()  # Blocks and handles events
```

**Key Features:**
- GLib.MainLoop handles all events automatically
- `connect_to_signal()` is declarative and simple
- Signals fire callbacks automatically
- Integrates well with GTK applications

### Proposed Architecture (Jeepney)

Jeepney has **two viable approaches:**

#### Option A: Asyncio (Recommended)

```python
import asyncio
from jeepney import DBusAddress, new_method_call, MatchRule
from jeepney.io.asyncio import open_dbus_connection, Proxy

async def monitor_services():
    async with open_dbus_connection(bus='SYSTEM') as connection:
        # Subscribe to signals
        rule = MatchRule(
            type="signal",
            interface="org.freedesktop.DBus.Properties",
            member="PropertiesChanged",
            path="/org/freedesktop/systemd1/unit/..."
        )

        async with connection.filter(rule) as signal_queue:
            while True:
                signal = await signal_queue.get()
                await handle_properties_changed(signal)

# Run with asyncio
asyncio.run(monitor_services())
```

**Pros:**
- Modern Python async/await
- Better concurrency for multiple services
- Can run Prometheus HTTP server concurrently
- More testable with async mocks

**Cons:**
- Complete rewrite of event handling
- All callbacks become `async def`
- Tests need async framework (pytest-asyncio)
- Different error handling patterns

#### Option B: Blocking I/O (Simpler but Limited)

```python
from jeepney.io.blocking import open_dbus_connection, Proxy

with open_dbus_connection(bus='SYSTEM') as connection:
    # Must manually poll for signals
    while True:
        msg = connection.receive()
        if msg.header.message_type == MessageType.signal:
            handle_signal(msg)
```

**Pros:**
- No async complexity
- Easier to understand

**Cons:**
- Manual message polling required
- Blocking I/O harder to test
- Less efficient for multiple services
- Prometheus server needs separate thread

### API Differences: Side-by-Side Comparison

| Task | dbus-python | Jeepney |
|------|-------------|---------|
| **Get service state** | `unit_props.Get(interface, "ActiveState")` | `await proxy.Get(interface, "ActiveState")` |
| **Subscribe to signals** | `obj.connect_to_signal("PropertiesChanged", callback)` | `async with connection.filter(MatchRule(...))` |
| **Event loop** | `GLib.MainLoop().run()` | `asyncio.run(main())` or manual polling |
| **Signal handling** | Automatic callback dispatch | Manual message queue processing |
| **Error handling** | `dbus.exceptions.DBusException` | `jeepney.wrappers.DBusErrorResponse` |

### Dependencies Impact

**Current (dbus-python):**
```
dbus-python>=1.2.0  # C extension, system dbus required
PyGObject>=3.36.0   # C extension, GLib/GTK required
```

**Proposed (Jeepney):**
```
jeepney>=0.9.0      # Pure Python, zero dependencies
```

**Benefits:**
- ✅ No C compilation needed
- ✅ Easier to install (pip only)
- ✅ Works in environments without system dbus libs
- ✅ Better for containers/minimal environments
- ✅ Easier cross-platform support

**Trade-offs:**
- ❌ No GLib integration (incompatible with GTK apps)
- ❌ Must rewrite event loop
- ❌ Different API requires code changes

---

## Part 2: Prometheus Integration

### Proposed Metrics

```python
from prometheus_client import start_http_server, Gauge, Counter

# Service state as numeric gauge
systemd_service_state = Gauge(
    'systemd_service_state',
    'Service state: 1=active, 0=inactive, 2=activating, 3=deactivating, -1=failed, -2=unloaded',
    ['service']
)

# Counters for state transitions
systemd_service_starts_total = Counter(
    'systemd_service_starts_total',
    'Total number of service starts',
    ['service']
)

systemd_service_stops_total = Counter(
    'systemd_service_stops_total',
    'Total number of service stops',
    ['service']
)

systemd_service_crashes_total = Counter(
    'systemd_service_crashes_total',
    'Total number of service crashes (failed state)',
    ['service']
)

# Metadata about the monitor itself
systemd_monitor_info = Gauge(
    'systemd_monitor_info',
    'Metadata about systemd_monitor',
    ['version', 'monitored_services']
)

# Last state change timestamp
systemd_service_last_change_timestamp = Gauge(
    'systemd_service_last_change_timestamp',
    'Unix timestamp of last state change',
    ['service']
)
```

### Integration Points

Update `handle_properties_changed()`:

```python
def handle_properties_changed(service_name, interface, changed, invalidated):
    # ... existing logic ...

    # Update Prometheus metrics
    state_value = {
        'active': 1,
        'inactive': 0,
        'activating': 2,
        'deactivating': 3,
        'failed': -1,
        'unloaded': -2
    }.get(current_active_state, -99)

    systemd_service_state.labels(service=service_name).set(state_value)
    systemd_service_last_change_timestamp.labels(service=service_name).set(
        time.time()
    )

    if start_detected:
        systemd_service_starts_total.labels(service=service_name).inc()

    if stop_detected:
        systemd_service_stops_total.labels(service=service_name).inc()

    if crash_detected:
        systemd_service_crashes_total.labels(service=service_name).inc()
```

### Initialization

In `main()`:

```python
def main():
    # ... existing setup ...

    # Start Prometheus HTTP server
    prometheus_port = app_config.prometheus_port  # default 9100
    if prometheus_port:
        start_http_server(prometheus_port)
        LOGGER.info(f"Prometheus metrics available at http://localhost:{prometheus_port}/metrics")

    # Initialize gauges from persisted state
    for service, state in SERVICE_STATES.items():
        state_value = STATE_MAP.get(state['last_state'], -99)
        systemd_service_state.labels(service=service).set(state_value)

        # Counters must be set from persisted values
        # Prometheus counters can only increment, so we set them once
        # Note: This is tricky - counters don't support .set()
        # We need a different approach for persistence
```

### Configuration Changes

Add to `config.py`:

```python
class Config:
    def __init__(self, ...):
        # ... existing ...
        self.prometheus_enabled = kwargs.get('prometheus_enabled', True)
        self.prometheus_port = kwargs.get('prometheus_port', 9100)
```

Add CLI arguments:

```python
parser.add_argument('--prometheus-port', type=int, default=9100,
                   help='Port for Prometheus metrics endpoint')
parser.add_argument('--no-prometheus', action='store_true',
                   help='Disable Prometheus metrics')
```

### Prometheus Counter Persistence Challenge

**Problem:** Prometheus Counters can only increment, never decrease.

When we restart the monitor, we have persisted counts (starts=5, stops=3), but Prometheus counters start at 0.

**Solutions:**

#### Option 1: Track Delta Only (Recommended)
```python
# Only count NEW starts/stops/crashes since monitor started
# Persisted values are for logging only
systemd_service_starts_total.labels(service=service_name).inc()
```

**Pros:** Clean Prometheus semantics
**Cons:** Loses historical data on restart

#### Option 2: Custom Gauge + Rate
```python
# Use Gauges instead of Counters, set from persisted values
systemd_service_starts_gauge.labels(service=service_name).set(persisted_starts)

# In Prometheus, use rate() to calculate changes:
# rate(systemd_service_starts_gauge[5m])
```

**Pros:** Preserves historical counts
**Cons:** Not standard Prometheus pattern

#### Option 3: Expose Both
```python
# Current session counters (resets on restart)
systemd_service_starts_total.labels(service=service_name).inc()

# Historical total as gauge (from persistence file)
systemd_service_starts_historical.labels(service=service_name).set(total_starts)
```

**Pros:** Best of both worlds
**Cons:** More metrics, slight complexity

**Recommendation:** Use Option 3 for maximum flexibility

---

## Part 3: Implementation Plan

### Phase 1: Prometheus Integration (Independent)

**Goal:** Add Prometheus without changing dbus library

**Changes:**
1. Add `prometheus_client` dependency
2. Define metrics in new `metrics.py` module
3. Add metric updates to `handle_properties_changed()`
4. Add `--prometheus-port` configuration
5. Start HTTP server in `main()`
6. Add tests for metric updates
7. Update documentation

**Effort:** ~2-3 days
**Risk:** Low - additive change only
**Dependencies:** None

**Deliverables:**
- Working Prometheus endpoint
- Grafana dashboard example
- Documentation updates
- 90%+ test coverage maintained

### Phase 2: Jeepney Research Spike (Optional)

**Goal:** Prototype Jeepney implementation to validate approach

**Tasks:**
1. Create proof-of-concept in separate branch
2. Implement basic service monitoring with Jeepney
3. Benchmark performance vs dbus-python
4. Test signal handling reliability
5. Evaluate code complexity

**Effort:** ~3-5 days
**Risk:** Medium - research outcome uncertain
**Decision point:** Go/No-Go based on findings

### Phase 3: Jeepney Migration (If Approved)

**Goal:** Replace dbus-python with Jeepney

**Sub-phases:**

#### 3A: Core Infrastructure
- Switch to asyncio event loop
- Implement D-Bus connection management
- Port signal subscription logic
- Update error handling

#### 3B: Signal Handling
- Rewrite `handle_properties_changed()` as async
- Implement signal filtering with MatchRule
- Handle reconnection logic

#### 3C: State Management
- Make `save_state()` / `load_state()` async-safe
- Update all callback functions to async

#### 3D: Testing
- Migrate all tests to pytest-asyncio
- Update mocking strategy
- Add integration tests with real D-Bus

#### 3E: Documentation
- Update README with new dependencies
- Document async architecture
- Update installation instructions

**Effort:** ~2-3 weeks
**Risk:** High - major architectural change
**Dependencies:** Phase 2 approval

---

## Part 4: Trade-off Analysis

### Benefits of Migrating to Jeepney

| Benefit | Impact | Notes |
|---------|--------|-------|
| **Pure Python** | High | No C compilation, easier installation |
| **Zero dependencies** | Medium | Simpler deployment, smaller containers |
| **Modern async/await** | Medium | Better concurrency, testability |
| **Cross-platform** | Low | Already works on Linux only |
| **Easier to debug** | Medium | Pure Python stack traces |

### Costs of Migrating to Jeepney

| Cost | Impact | Notes |
|------|--------|-------|
| **Complete rewrite** | High | ~1000+ lines of code changes |
| **Test rewrite** | High | All 77 tests need async updates |
| **Learning curve** | Medium | Team needs async Python knowledge |
| **Risk of bugs** | High | New code = new bugs |
| **Lost GLib integration** | Low | Not using GTK anyway |
| **Development time** | High | 2-3 weeks vs 2-3 days for Prometheus |

### Recommendation Matrix

| Scenario | Recommendation |
|----------|----------------|
| **Just want Prometheus metrics** | ✅ **Phase 1 only** - Don't migrate to Jeepney |
| **Installation issues with dbus-python** | ⚠️ **Consider migration** - Jeepney helps |
| **Running in containers** | ⚠️ **Consider migration** - Pure Python is easier |
| **Team unfamiliar with async** | ❌ **Don't migrate** - Too risky |
| **Production system, risk-averse** | ❌ **Don't migrate** - Stick with proven dbus-python |
| **Want latest Python features** | ✅ **Migrate** - async/await is modern |

---

## Part 5: Detailed Code Examples

### Example 1: Current vs Jeepney Signal Handling

**Current (dbus-python):**
```python
def setup_dbus_monitor():
    for service_name in MONITORED_SERVICES:
        unit_path = MANAGER_INTERFACE.GetUnit(service_name)
        unit_obj = SYSTEM_BUS.get_object(SYSTEMD_DBUS_SERVICE, str(unit_path))

        unit_obj.connect_to_signal(
            "PropertiesChanged",
            lambda interface, changed, invalidated, s=service_name: (
                handle_properties_changed(s, interface, changed, invalidated)
            ),
            dbus_interface=SYSTEMD_PROPERTIES_INTERFACE,
        )
```

**Jeepney (asyncio):**
```python
async def setup_dbus_monitor():
    async with open_dbus_connection(bus='SYSTEM') as connection:
        # Get systemd manager proxy
        systemd = Proxy(
            MessageGenerator(
                object_path='/org/freedesktop/systemd1',
                bus_name='org.freedesktop.systemd1'
            ),
            connection
        )

        # Get unit paths for all monitored services
        tasks = []
        for service_name in MONITORED_SERVICES:
            unit_path = await systemd.GetUnit(service_name)

            # Create match rule for this unit's PropertiesChanged signals
            rule = MatchRule(
                type="signal",
                interface="org.freedesktop.DBus.Properties",
                member="PropertiesChanged",
                path=unit_path
            )

            # Start monitoring task
            task = asyncio.create_task(
                monitor_service(connection, service_name, rule)
            )
            tasks.append(task)

        # Wait for all monitoring tasks
        await asyncio.gather(*tasks)

async def monitor_service(connection, service_name, rule):
    """Monitor a single service for PropertiesChanged signals."""
    async with connection.filter(rule) as signal_queue:
        while True:
            signal = await signal_queue.get()

            # Extract args from signal message
            interface = signal.body[0]
            changed = signal.body[1]
            invalidated = signal.body[2]

            await handle_properties_changed(
                service_name, interface, changed, invalidated
            )
```

### Example 2: Async State Management

**Current (sync):**
```python
def handle_properties_changed(service_name, interface, changed, invalidated):
    # ... state detection logic ...

    if counter_changed:
        save_state()
```

**Jeepney (async):**
```python
async def handle_properties_changed(service_name, interface, changed, invalidated):
    # ... state detection logic ...

    if counter_changed:
        await save_state()

async def save_state():
    """Async version of save_state()."""
    os.makedirs(PERSISTENCE_DIR, exist_ok=True)

    # Use aiofiles for async file I/O
    async with aiofiles.open(PERSISTENCE_FILE, 'w') as f:
        await f.write(json.dumps(serializable_states, indent=4))
```

### Example 3: Main Loop Comparison

**Current:**
```python
def main():
    main_loop = GLib.MainLoop()

    signal.signal(signal.SIGINT, partial(signal_handler, main_loop=main_loop))
    signal.signal(signal.SIGTERM, partial(signal_handler, main_loop=main_loop))

    if setup_dbus_monitor():
        sys.exit(1)

    main_loop.run()  # Blocks forever
```

**Jeepney:**
```python
async def main():
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown_handler(shutdown_event))
        )

    # Start monitoring
    monitor_task = asyncio.create_task(setup_dbus_monitor())

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    monitor_task.cancel()
    await save_state()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Part 6: Testing Strategy

### Current Test Approach

```python
# Mock dbus at import time
sys.modules["dbus"] = MagicMock()
sys.modules["gi.repository.GLib"] = MagicMock()
```

### Jeepney Test Approach

```python
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def mock_dbus_connection():
    """Mock Jeepney D-Bus connection."""
    connection = AsyncMock()
    connection.filter = AsyncMock()
    # ... setup mocks ...
    return connection

@pytest.mark.asyncio
async def test_handle_properties_changed():
    """Test async property change handler."""
    await handle_properties_changed(
        "test.service",
        "org.freedesktop.systemd1.Unit",
        {"ActiveState": "active"},
        []
    )
    # assertions...
```

**Required changes:**
- Add `pytest-asyncio` dependency
- Convert all test functions to `async def`
- Use `@pytest.mark.asyncio` decorator
- Update mocking strategy for Jeepney
- ~77 tests need conversion

---

## Part 7: Migration Timeline

### Conservative Estimate (Jeepney + Prometheus)

| Phase | Duration | Parallel Work |
|-------|----------|---------------|
| **Prometheus Integration** | 3 days | Can be done independently |
| **Jeepney Research Spike** | 5 days | After Prometheus |
| **Jeepney Core Migration** | 5 days | - |
| **Test Migration** | 5 days | Can overlap with core |
| **Integration & Bug Fixes** | 5 days | - |
| **Documentation** | 2 days | Can overlap |
| **Code Review & QA** | 3 days | - |
| **Total** | **~4 weeks** | With overlap: ~3 weeks |

### Aggressive Estimate (Prometheus Only)

| Phase | Duration |
|-------|----------|
| **Prometheus Integration** | 2 days |
| **Testing** | 1 day |
| **Documentation** | 0.5 days |
| **Total** | **~3-4 days** |

---

## Part 8: Recommendation

### My Recommendation: **Prometheus Now, Jeepney Later (Maybe Never)**

**Rationale:**

1. **Prometheus provides immediate value**
   - Metrics exportable to Grafana
   - Industry-standard monitoring
   - Small, low-risk change

2. **Jeepney migration has unclear ROI**
   - Huge effort (2-3 weeks)
   - High risk of bugs
   - Current dbus-python works fine
   - Benefits (pure Python) are nice-to-have, not need-to-have

3. **Better alternatives exist**
   - If installation is the issue: Document system package installation
   - If containers are the issue: Multi-stage builds work fine
   - If dependencies are the issue: They're already required for systemd integration

### Proposed Next Steps

**Step 1: Implement Prometheus (This Week)**
- Add prometheus_client dependency
- Implement metrics as shown above
- Test with Grafana
- Ship it!

**Step 2: Evaluate Jeepney Need (Future)**
- Wait for actual pain points with dbus-python
- If installation becomes a real blocker: Revisit
- If team wants async/await: Revisit
- Otherwise: Keep current architecture

**Step 3: Alternative: Incremental Improvements**
Instead of rewriting with Jeepney, consider:
- Better error handling with current dbus-python
- Add reconnection logic for robustness
- Improve test coverage to 100%
- Add more metrics (response time, queue depth, etc.)

---

## Part 9: Risks & Mitigation

### Prometheus Integration Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Port conflict | Low | Low | Make port configurable |
| Memory leak | Low | Medium | Monitor in testing |
| Performance impact | Low | Low | Metrics are lightweight |
| Counter persistence | Medium | Low | Use dual metric approach |

### Jeepney Migration Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Signal delivery issues | Medium | High | Extensive integration testing |
| Performance degradation | Low | Medium | Benchmark before/after |
| Async bugs | High | High | Comprehensive test coverage |
| Team knowledge gap | Medium | Medium | Training + documentation |
| Production incidents | Medium | High | Gradual rollout, feature flag |
| Schedule overrun | High | Medium | Use timeboxing, be ready to abort |

---

## Appendices

### Appendix A: Prometheus Query Examples

```promql
# Current state of all services
systemd_service_state

# Services in failed state
systemd_service_state == -1

# Restart rate (starts per minute)
rate(systemd_service_starts_total[1m])

# Services with crashes
systemd_service_crashes_total > 0

# Time since last state change
time() - systemd_service_last_change_timestamp
```

### Appendix B: Grafana Dashboard JSON

```json
{
  "dashboard": {
    "title": "systemd Services",
    "panels": [
      {
        "title": "Service States",
        "targets": [{
          "expr": "systemd_service_state",
          "legendFormat": "{{service}}"
        }],
        "type": "graph"
      },
      {
        "title": "Crash Count",
        "targets": [{
          "expr": "systemd_service_crashes_total",
          "legendFormat": "{{service}}"
        }],
        "type": "stat"
      }
    ]
  }
}
```

### Appendix C: Dependencies Comparison

**Current:**
```
dbus-python>=1.2.0
PyGObject>=3.36.0
```

**With Prometheus:**
```
dbus-python>=1.2.0
PyGObject>=3.36.0
prometheus-client>=0.19.0
```

**With Jeepney + Prometheus:**
```
jeepney>=0.9.0
prometheus-client>=0.19.0
aiofiles>=23.0.0  # For async file I/O
```

### Appendix D: Code Size Estimate

| Component | Current LoC | With Prometheus | With Jeepney | Change |
|-----------|-------------|-----------------|--------------|--------|
| systemd_monitor.py | 650 | 720 | 850 | +200 |
| config.py | 140 | 160 | 160 | +20 |
| metrics.py | 0 | 80 | 80 | +80 |
| tests/ | 1020 | 1100 | 1300 | +280 |
| **Total** | **1810** | **2060** | **2390** | **+580** |

---

## Conclusion

**Prometheus:** ✅ **Highly Recommended** - Clear value, low risk

**Jeepney:** ⚠️ **Not Recommended Now** - High effort, unclear benefit

**Suggested Path:**
1. Implement Prometheus this week
2. Ship it and gather feedback
3. Revisit Jeepney only if dbus-python causes real problems
4. Focus on features users actually need

**The perfect is the enemy of the good.** Let's ship Prometheus and add value today, rather than spend weeks rewriting code that already works.
