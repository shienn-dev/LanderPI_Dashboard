"""Going online from inside the dashboard: the button that fixes OFFLINE.

Why this file exists
--------------------
"OFFLINE" is a *launch* state, not a fault: started without ``--chassis-live``,
the dashboard builds the direction pad with no event handler at all, so every
press is ignored -- no error, no notification, no log line -- while the page
looks perfectly normal. On 2026-10-22 that cost a whole session, and on
2026-10-26 the same state came back. The panel now says OFFLINE loudly and
offers a button that opens the real chassis port on request.

These tests cover that path without a serial device. They prove the three
things that matter:

* opening the port moves nothing (the idle stream writes no frame at all);
* a refused port leaves the dashboard honestly OFFLINE and says why;
* the stream waits out the measured 2,36 s the board is deaf after ``open()``,
  so the first hold is not swallowed -- the failure mode that looks exactly
  like a dead button.
"""

from __future__ import annotations

import pytest

from amr_core.robot.interfaces import ConnectionState
from amr_dashboard import app as dash
from amr_dashboard import chassis_panel, robot_runtime


class _ScriptedPort:
    """In-memory stand-in for the STM32 port: records every byte written."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes, /) -> int:
        self.writes.append(bytes(data))
        return len(data)

    def flush(self) -> None:  # pragma: no cover - nothing to flush
        pass

    def close(self) -> None:
        self.closed = True


class _PortFactory:
    """Counts opens and hands out scripted ports."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.ports: list[_ScriptedPort] = []
        self.opens = 0
        self.fail_with = fail_with

    def __call__(self, port: str, baud: int) -> _ScriptedPort:
        self.opens += 1
        if self.fail_with is not None:
            raise self.fail_with
        handle = _ScriptedPort()
        self.ports.append(handle)
        return handle


@pytest.fixture(autouse=True)
def _clean_registry():
    robot_runtime.reset_adapters()
    yield
    robot_runtime.reset_adapters()


def test_going_live_opens_the_port_and_writes_no_motion() -> None:
    """The ONLINE button opens a port; it must never make the robot move."""
    factory = _PortFactory()

    result = robot_runtime.activate_live_chassis(
        "/dev/fake", port_factory=factory, settle_s=0.0
    )

    assert result.ok is True
    assert result.state is ConnectionState.CONNECTED
    adapters = robot_runtime.get_adapters()
    assert adapters.live is True
    assert adapters.chassis.state() is ConnectionState.CONNECTED
    assert adapters.guard is not None
    assert factory.opens == 1
    # Not a single frame: no command was requested, so the stream stays idle.
    assert factory.ports[0].writes == []


def test_a_refused_port_leaves_the_dashboard_offline_and_says_why() -> None:
    factory = _PortFactory(
        fail_with=OSError("/dev/fake is already open in another process (pid 4242)")
    )

    result = robot_runtime.activate_live_chassis(
        "/dev/fake", port_factory=factory, settle_s=0.0
    )

    assert result.ok is False
    assert result.state is ConnectionState.UNAVAILABLE
    assert "/dev/fake" in result.message
    assert "already open" in result.message
    assert "OFFLINE" in result.message

    # The dashboard must still be the safe offline set, not a live one that
    # silently transmits nothing.
    adapters = robot_runtime.get_adapters()
    assert adapters.live is False
    assert adapters.chassis.state() is ConnectionState.DISABLED
    assert adapters.guard is None


def test_going_live_twice_does_not_open_a_second_stream() -> None:
    """A double click must not put two writers on one port."""
    factory = _PortFactory()

    first = robot_runtime.activate_live_chassis(
        "/dev/fake", port_factory=factory, settle_s=0.0
    )
    second = robot_runtime.activate_live_chassis(
        "/dev/fake", port_factory=factory, settle_s=0.0
    )

    assert first.ok is True
    assert second.ok is True
    assert "sudah LIVE" in second.message
    assert factory.opens == 1


def test_the_live_stream_waits_out_the_measured_dead_window() -> None:
    """The first frame must be later than the 2,36 s the board is deaf.

    The adapter's own default (0,3 s) is right for a port opened at server
    start-up and wrong for a port opened from the UI, where the operator is
    already holding a button. This is the guard that keeps the online path from
    silently eating the first hold.
    """
    assert robot_runtime.BOOT_WINDOW_S >= 2.36

    adapters = robot_runtime.build_adapters(live=True, port="/dev/fake")
    assert adapters.chassis.settle_s == robot_runtime.BOOT_WINDOW_S

    # And the value that actually reaches the adapter is the measured one.
    factory = _PortFactory()
    robot_runtime.activate_live_chassis("/dev/fake", port_factory=factory)
    live = robot_runtime.get_adapters()
    assert live.chassis.settle_s >= 2.36


def test_the_layout_rebuilds_when_the_chassis_goes_live() -> None:
    """The signature is the mechanism: without it the pad would never change."""
    state = dash.DashboardState()
    before = dash.layout_signature(state)

    factory = _PortFactory()
    robot_runtime.activate_live_chassis("/dev/fake", port_factory=factory, settle_s=0.0)

    after = dash.layout_signature(state)
    assert before == ("competition", "offline")
    assert after == ("competition", "live")


def test_the_offline_panel_renders_the_online_control_and_stays_silent() -> None:
    """Rendering OFFLINE must offer the way out and still transmit nothing."""
    assert callable(chassis_panel._online_controls)

    adapters = robot_runtime.build_adapters(live=False)
    chassis_panel.chassis_control_panel(adapters)

    assert adapters.chassis.state() is ConnectionState.DISABLED
    assert adapters.chassis.last_command() is None
    assert adapters.guard is None


def test_the_port_the_button_opens_follows_the_command_line() -> None:
    """--chassis-port must not be ignored just because the server is offline."""
    robot_runtime.set_default_port("/dev/ttyACM9")
    assert robot_runtime.default_port() == "/dev/ttyACM9"

    factory = _PortFactory()
    robot_runtime.activate_live_chassis(port_factory=factory, settle_s=0.0)
    assert factory.opens == 1

    # An empty argument falls back to the real default instead of "".
    robot_runtime.set_default_port("")
    assert robot_runtime.default_port() == "/dev/ttyACM0"
