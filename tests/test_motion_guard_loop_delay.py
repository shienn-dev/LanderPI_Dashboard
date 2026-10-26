"""Fault A4/F8: a hold that dies with "heartbeat lost" while it is still held.

The guard stops the robot when the browser stops saying "I am still in control".
That is correct when the browser really went quiet. It is wrong when *this
process* was too busy to process the heartbeats that did arrive -- and that is
the fault the operator keeps reporting ("kanan kiri dan Putar R & L terjadi
Heartbeat Loss", and earlier A4/F8: "robot berhenti mendadak").

The stream thread polls at 50 Hz in its own thread, so it notices a stale
heartbeat *while* the event loop is still blocked. Forgiving the stall after the
fact is therefore too late: the guard has to know, at the moment it decides,
whether the silence is the client's or ours. It does that with the loop-tick
timestamp the watchdog refreshes every 50 ms.

These tests pin all of it: our own stall does not kill the hold, a genuinely
silent client still does, and neither tolerance is unbounded.
"""

from __future__ import annotations

import pytest

from amr_core.robot.interfaces import ChassisCommand
from amr_core.robot.motion_guard import (
    DEFAULT_BUSY_ALLOWANCE_CAP_S,
    DEFAULT_HEARTBEAT_TIMEOUT_S,
    DEFAULT_LOOP_STALL_STOP_S,
    MotionGuard,
)
from amr_dashboard import chassis_panel, robot_runtime


class FakeClock:
    """Deterministic clock: the tests own the timeline."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


SESSION = "browser-1"
COMMAND = ChassisCommand(linear_x=0.1, linear_y=0.0, angular_z=0.0)


def _armed_guard(clock: FakeClock) -> MotionGuard:
    guard = MotionGuard(clock=clock)
    assert guard.arm(SESSION) is True
    assert guard.heartbeat(SESSION) is True
    assert guard.request_motion(SESSION, COMMAND) is True
    guard.note_loop_tick()
    return guard


def _null_port_factory(_port: str, _baud: int):
    return _NullPort()


class _NullPort:
    def write(self, data: bytes, /):
        return len(data)

    def flush(self) -> None: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# Our own stall must not look like a dead browser
# --------------------------------------------------------------------------- #

def test_a_hold_survives_this_process_being_blocked() -> None:
    """The A4/F8 case: the loop is stuck, so the guard must not judge the client."""
    clock = FakeClock()
    guard = _armed_guard(clock)

    # The loop is blocked for 1,0 s: longer than the 0,8 s timeout. No tick and
    # no heartbeat can be processed, and the stream thread polls 50 times a
    # second throughout.
    clock.advance(1.0)
    assert guard.loop_age() == pytest.approx(1.0)

    assert guard.heartbeat_fresh() is True
    assert guard.poll() == COMMAND


def test_a_blocked_loop_still_stops_the_robot_if_it_lasts_too_long() -> None:
    """The tolerance for our own stall is bounded, not open-ended."""
    clock = FakeClock()
    guard = _armed_guard(clock)

    clock.advance(DEFAULT_LOOP_STALL_STOP_S + 0.1)

    assert guard.poll() is None
    assert guard.stopped_reason == "heartbeat lost"


def test_the_loop_keeps_ticking_and_the_silent_client_is_refused() -> None:
    """Our own liveness must not become an excuse for a client that went away."""
    clock = FakeClock()
    guard = _armed_guard(clock)
    guard.release_motion(SESSION)

    end = clock.now + DEFAULT_HEARTBEAT_TIMEOUT_S + 0.2
    while clock.now < end:            # loop is alive the whole time
        clock.advance(0.05)
        guard.note_loop_tick()

    assert guard.request_motion(SESSION, COMMAND) is False
    assert guard.stopped_reason == "heartbeat lost"


def test_the_busy_allowance_covers_the_batch_after_the_loop_resumes() -> None:
    """When the loop comes back, the queued heartbeats are not yet processed.

    The watchdog ticks first and reports the delay; without the allowance the
    stream thread would kill the hold in the few milliseconds before the queued
    heartbeat events are handled.
    """
    clock = FakeClock()
    guard = _armed_guard(clock)

    clock.advance(1.2)              # blocked
    guard.note_loop_tick()          # loop is back
    guard.note_busy(1.2)            # and it says why it was away
    assert guard.poll() == COMMAND  # hold survives the resume

    # The queued heartbeat then arrives, and normal rules apply again.
    guard.heartbeat(SESSION)
    assert guard.heartbeat_age() == pytest.approx(0.0)


def test_a_silent_client_with_a_healthy_loop_is_still_stopped() -> None:
    """The safety net is untouched: no heartbeat, no excuse, no motion."""
    clock = FakeClock()
    guard = _armed_guard(clock)

    # The loop keeps ticking all along -- only the client goes quiet.
    end = clock.now + DEFAULT_HEARTBEAT_TIMEOUT_S + 0.2
    while clock.now < end:
        clock.advance(0.05)
        guard.note_loop_tick()

    assert guard.poll() is None
    assert guard.stopped_reason == "heartbeat lost"


def test_the_forgiveness_is_capped() -> None:
    """A huge reported delay cannot excuse an unlimited silence."""
    clock = FakeClock()
    guard = _armed_guard(clock)

    guard.note_busy(10.0)
    clock.advance(DEFAULT_HEARTBEAT_TIMEOUT_S + DEFAULT_BUSY_ALLOWANCE_CAP_S - 0.05)
    guard.note_loop_tick()
    assert guard.heartbeat_fresh() is True

    clock.advance(0.2)
    guard.note_loop_tick()
    assert guard.poll() is None
    assert guard.stopped_reason == "heartbeat lost"


def test_the_forgiveness_resets_on_every_heartbeat() -> None:
    """A heartbeat proves the client is alive now, so the allowance is spent."""
    clock = FakeClock()
    guard = _armed_guard(clock)

    guard.note_busy(1.5)
    assert guard.state.busy_s == pytest.approx(1.5)
    guard.heartbeat(SESSION)
    assert guard.state.busy_s == 0.0

    clock.advance(DEFAULT_HEARTBEAT_TIMEOUT_S + 0.1)
    guard.note_loop_tick()
    assert guard.poll() is None


def test_a_new_motion_request_survives_our_own_stall() -> None:
    """request_motion uses the same rule as poll()."""
    clock = FakeClock()
    guard = _armed_guard(clock)
    guard.release_motion(SESSION)

    clock.advance(0.9)              # blocked
    assert guard.request_motion(SESSION, COMMAND) is True


# --------------------------------------------------------------------------- #
# The watchdog plumbing and what the panel says about it
# --------------------------------------------------------------------------- #

def _installed_adapters() -> robot_runtime.RobotAdapters:
    robot_runtime.reset_adapters()
    robot_runtime.reset_loop_diagnostics()
    adapters = robot_runtime.build_adapters(
        live=True, port="/dev/fake", port_factory=_null_port_factory, settle_s=0.0
    )
    robot_runtime._adapters = adapters
    return adapters


def test_the_watchdog_reaches_the_guard_that_owns_the_robot() -> None:
    adapters = _installed_adapters()
    guard = adapters.guard
    assert guard is not None
    guard.arm(SESSION)
    guard.heartbeat(SESSION)

    robot_runtime.note_loop_tick()
    robot_runtime.record_loop_delay(0.45)

    diag = robot_runtime.loop_diagnostics()
    assert diag.max_delay_s == pytest.approx(0.45)
    assert diag.late_ticks == 1
    assert guard.state.busy_s == pytest.approx(0.45)
    robot_runtime.reset_adapters()
    robot_runtime.reset_loop_diagnostics()


def test_a_short_tick_delay_is_measured_but_not_charged_to_the_guard() -> None:
    adapters = _installed_adapters()
    guard = adapters.guard
    assert guard is not None
    guard.arm(SESSION)
    guard.heartbeat(SESSION)

    robot_runtime.record_loop_delay(0.05)

    diag = robot_runtime.loop_diagnostics()
    assert diag.last_delay_s == pytest.approx(0.05)
    assert diag.late_ticks == 0
    assert guard.state.busy_s == 0.0
    robot_runtime.reset_adapters()
    robot_runtime.reset_loop_diagnostics()


def test_the_panel_says_which_side_lost_the_heartbeat() -> None:
    """The operator must not be left guessing between the two causes."""
    now = 1000.0
    # A stall that just happened explains a stop that just happened.
    fresh = robot_runtime.LoopDiagnostics(
        max_delay_s=0.9, late_ticks=3, max_delay_at_s=now - 0.5
    )
    note = chassis_panel._reason_note("heartbeat lost", fresh, now)
    assert "sisi server" in note
    assert "900" in note

    # A maximum from minutes ago explains nothing: the client is the suspect.
    stale = robot_runtime.LoopDiagnostics(
        max_delay_s=0.9, late_ticks=3, max_delay_at_s=now - 120.0
    )
    note = chassis_panel._reason_note("heartbeat lost", stale, now)
    assert "loop server normal" in note
    assert "Wi-Fi" in note

    healthy = robot_runtime.LoopDiagnostics(max_delay_s=0.02, late_ticks=0, max_delay_at_s=now)
    assert "loop server normal" in chassis_panel._reason_note("heartbeat lost", healthy, now)

    # Any other reason is reported by the guard already; no extra story.
    assert chassis_panel._reason_note("button released", fresh, now) == ""