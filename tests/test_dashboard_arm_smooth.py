"""Tests for the smooth arm path: one drag, one frame, never the gripper.

The operator's complaint (2026-10-29) that started this file: moving one joint
200 pulses cost twenty clicks of 10 pulses each. These tests pin the fix -- a
single ``set position`` frame whose duration is distance/speed -- and keep the
three fences: measured-limit clamp, silent servo is not moved by a guess, and
servo 10 is never in a frame.
"""

from __future__ import annotations

import struct

import pytest

from amr_core.robot.arm_bus import (
    MEASURED_LIMITS,
    MIN_DURATION_S,
    BusServoArmAdapter,
    build_frame,
)
from amr_dashboard.arm_jog import (
    DEFAULT_SPEED_PPS,
    FLUSH_INTERVAL_S,
    MAX_SPEED_PPS,
    MIN_SPEED_PPS,
    SETTLE_S,
    ArmJogController,
    clamp_speed,
    plan_move,
)

FUNC_BUS_SERVO = 5
SUB_SET_POSITION = 0x01
SUB_STOP = 0x03
READ_POSITION = 0x05


def _position_reply(servo_id: int, pulse: int) -> bytes:
    """The reply the board gave us on 2026-10-28: id, cmd echo, status 0, pulse."""
    info = int(pulse).to_bytes(2, "little", signed=True)
    return build_frame(FUNC_BUS_SERVO, bytes([servo_id, READ_POSITION, 0x00]) + info)


class EchoPort:
    """A fake board: records writes, answers position reads with real positions."""

    def __init__(self, positions: dict[int, int] | None = None) -> None:
        self.positions = dict(positions if positions is not None else {})
        self.writes: list[bytes] = []
        self._rx = bytearray()

    def write(self, data: bytes) -> int:
        frame = bytes(data)
        self.writes.append(frame)
        if len(frame) == 7 and frame[4] == READ_POSITION:
            pulse = self.positions.get(frame[5])
            if pulse is not None:
                self._rx.extend(_position_reply(frame[5], pulse))
        return len(frame)

    def read(self, size: int = 64) -> bytes:
        out = bytes(self._rx[:size])
        del self._rx[:size]
        return out

    def reset_input_buffer(self) -> None:
        self._rx.clear()

    def close(self) -> None:
        return None

    # -- helpers for assertions -----------------------------------------
    def set_position_frames(self) -> list[tuple[int, int, list[tuple[int, int]]]]:
        """``[(duration_ms, count, [(id, pulse)...])]`` for every move frame."""
        out = []
        for frame in self.writes:
            payload = frame[4:-1]
            if len(payload) < 4 or payload[0] != SUB_SET_POSITION:
                continue
            _sub, duration_ms, count = struct.unpack("<BHB", payload[:4])
            moves = []
            for index in range(count):
                servo_id, pulse = struct.unpack("<BH", payload[4 + index * 3 : 7 + index * 3])
                moves.append((servo_id, pulse))
            out.append((duration_ms, count, moves))
        return out

    def stop_frames(self) -> list[list[int]]:
        out = []
        for frame in self.writes:
            payload = frame[4:-1]
            if payload[0] != SUB_STOP:
                continue
            out.append(list(payload[2 : 2 + payload[1]]))
        return out


def _adapter(port: EchoPort) -> BusServoArmAdapter:
    adapter = BusServoArmAdapter(port="/dev/fake")
    ok, _reason = adapter.open(port)
    assert ok is True
    return adapter


def _jog(arm, **kwargs) -> ArmJogController:
    """A controller that sends on the very next flush unless a test says otherwise.

    ``settle_s=0`` keeps the older tests about *what* is sent readable; the
    settle behaviour itself (the fix for the stutter) has its own tests with a
    fake clock.
    """
    kwargs.setdefault("settle_s", 0.0)
    return ArmJogController(arm, **kwargs)


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# -- planning -------------------------------------------------------------


def test_a_long_move_becomes_one_frame_with_a_proportional_duration() -> None:
    """200 pulses at the vendor's speed is 1,3 s -- not twenty 0,8 s presses."""
    plan = plan_move(3, 500, 700, limits=MEASURED_LIMITS)
    assert plan.changed is True
    assert plan.target == 700
    assert plan.duration_s == pytest.approx(200 / DEFAULT_SPEED_PPS)
    assert plan.duration_s > MIN_DURATION_S


def test_a_short_move_never_goes_below_the_floor() -> None:
    """10 pulses would be 0,07 s; the arm needs at least MIN_DURATION_S."""
    plan = plan_move(3, 500, 510, limits=MEASURED_LIMITS)
    assert plan.duration_s == pytest.approx(MIN_DURATION_S)


def test_the_target_is_clamped_to_that_servo_s_measured_limit() -> None:
    plan = plan_move(1, 500, 5000, limits=MEASURED_LIMITS)
    assert plan.target == MEASURED_LIMITS[1][1]
    below = plan_move(1, 500, -400, limits=MEASURED_LIMITS)
    assert below.target == MEASURED_LIMITS[1][0]


def test_a_target_equal_to_the_start_is_not_a_move() -> None:
    assert plan_move(4, 300, 300, limits=MEASURED_LIMITS).changed is False


def test_an_unknown_servo_cannot_be_planned() -> None:
    with pytest.raises(ValueError):
        plan_move(10, 500, 600, limits=MEASURED_LIMITS)


def test_speed_is_kept_inside_the_vendor_band() -> None:
    assert clamp_speed(0) == MIN_SPEED_PPS
    assert clamp_speed(10_000) == MAX_SPEED_PPS
    assert clamp_speed(150) == 150


def test_a_faster_setting_shortens_the_frame_but_not_past_the_floor() -> None:
    slow = plan_move(2, 200, 600, limits=MEASURED_LIMITS, speed_pps=40)
    fast = plan_move(2, 200, 600, limits=MEASURED_LIMITS, speed_pps=400)
    assert slow.duration_s > fast.duration_s
    assert fast.duration_s == pytest.approx(1.0)


# -- controller -----------------------------------------------------------


def test_one_drag_sends_one_frame_not_a_stream_of_clicks() -> None:
    port = EchoPort({5: 500})
    arm = _adapter(port)
    controller = _jog(arm)
    controller.set_target(5, 700)          # what a slider drag ends up calling
    results = controller.flush()
    assert len(results) == 1 and results[0].sent is True

    moves = port.set_position_frames()
    assert len(moves) == 1
    duration_ms, count, pairs = moves[0]
    assert count == 1 and pairs == [(5, 700)]
    assert duration_ms == int(round(200 / DEFAULT_SPEED_PPS * 1000))


def test_many_slider_events_before_one_flush_still_send_one_frame() -> None:
    """A drag fires dozens of events; only the latest value may reach the board."""
    port = EchoPort({1: 400})
    controller = _jog(_adapter(port))
    for pulse in range(410, 610, 10):
        controller.set_target(1, pulse)
    controller.flush()
    moves = port.set_position_frames()
    assert len(moves) == 1
    assert moves[0][2] == [(1, 600)]


def test_two_joints_dragged_send_two_frames_each_naming_one_joint() -> None:
    port = EchoPort({2: 300, 4: 400})
    controller = _jog(_adapter(port))
    controller.set_target(2, 400)
    controller.set_target(4, 500)
    controller.flush()
    moves = port.set_position_frames()
    assert len(moves) == 2
    assert sorted(pair for _duration, _count, pairs in moves for pair in pairs) == [
        (2, 400),
        (4, 500),
    ]


def test_a_silent_servo_is_not_moved_by_a_guess() -> None:
    port = EchoPort({})                    # no servo answers
    controller = _jog(_adapter(port))
    controller.set_target(3, 600)
    results = controller.flush()
    assert results[0].sent is False
    assert "tidak menjawab" in results[0].reason
    assert port.set_position_frames() == []


def test_the_gripper_cannot_be_targeted_at_all() -> None:
    controller = _jog(_adapter(EchoPort({1: 500})))
    with pytest.raises(ValueError):
        controller.set_target(10, 500)


def test_a_programmatic_slider_sync_is_not_a_command() -> None:
    controller = _jog(_adapter(EchoPort({1: 500})))
    controller.syncing = True
    with pytest.raises(RuntimeError):
        controller.set_target(1, 900)
    controller.syncing = False
    controller.set_target(1, 900)
    assert controller.preview(1) is not None


def test_stop_drops_the_pending_drag_and_never_names_the_gripper() -> None:
    port = EchoPort({1: 500})
    controller = _jog(_adapter(port))
    controller.set_target(1, 900)
    result = controller.stop()
    assert result.sent is True
    assert controller.flush() == []        # the in-flight drag is gone
    assert port.set_position_frames() == []
    stops = port.stop_frames()
    assert stops and stops[0] == [1, 2, 3, 4, 5]
    assert 10 not in stops[0]


def test_a_new_drag_after_stop_is_allowed_again() -> None:
    port = EchoPort({1: 500})
    controller = _jog(_adapter(port))
    controller.stop()
    assert controller.halted is True
    controller.set_target(1, 600)
    assert controller.halted is False
    controller.flush()
    assert port.set_position_frames()[-1][2] == [(1, 600)]


def test_a_drag_that_was_only_previewed_sends_nothing_until_release() -> None:
    """Round 2: while the handle moves the panel only previews the plan.

    Re-targeting a bus servo several times a second restarts its motion profile
    each time -- that was the "nyendet-nyendet" the operator reported at the
    default speed. So a whole drag (dozens of previews) must put *zero* frames on
    the wire, and the release must put exactly one.
    """
    port = EchoPort({2: 400})
    controller = _jog(_adapter(port))
    for pulse in range(410, 700, 10):        # what a slow drag emits
        plan = controller.plan_for(2, pulse)
        assert plan.target == pulse
    assert port.set_position_frames() == []  # previews are free
    assert controller.preview(2) is None     # nothing pending yet

    controller.set_target(2, 690)            # the release
    controller.flush()
    moves = port.set_position_frames()
    assert len(moves) == 1
    assert moves[0][2] == [(2, 690)]
    assert moves[0][0] == int(round(290 / DEFAULT_SPEED_PPS * 1000))


def test_the_preview_never_exceeds_the_servo_s_own_limit() -> None:
    controller = _jog(_adapter(EchoPort({3: 100})))
    assert controller.plan_for(3, 5000).target == MEASURED_LIMITS[3][1]
    assert controller.plan_for(3, -90).target == MEASURED_LIMITS[3][0]


def test_the_duration_follows_the_last_commanded_pulse_not_the_first_reading() -> None:
    """Second move of a drag measures from where we just told it to go."""
    port = EchoPort({5: 300})
    controller = _jog(_adapter(port))
    controller.set_target(5, 500)
    controller.flush()
    controller.set_target(5, 700)
    controller.flush()
    durations = [duration for duration, _c, _p in port.set_position_frames()]
    assert durations[0] == durations[1]      # both 200 pulses, same speed
    assert durations[0] == int(round(200 / DEFAULT_SPEED_PPS * 1000))


def test_a_pty_is_exempt_from_the_port_holder_check() -> None:
    """The fake-board harness answers on a PTY, so it may not trip the guard.

    The guard itself stays as strict as before for real devices: two writers on
    /dev/ttyACM0 must still be refused.
    """
    from amr_dashboard.chassis_transport import is_pty, other_processes_holding

    assert is_pty("/dev/pts/3") is True
    assert other_processes_holding("/dev/pts/3") == []
    assert is_pty("/dev/ttyACM0") is False


def test_a_moving_handle_never_reaches_the_board() -> None:
    """Round 2, the actual complaint: default speed, and the joint stuttered.

    The mechanism: a drag emits events tens of times a second, and a frame per
    event re-targets the servo every time, restarting its motion profile. So a
    drag of one second, flushed every panel tick, must put *zero* frames on the
    wire; the joint is told once, after the handle settles.
    """
    clock = FakeClock()
    port = EchoPort({4: 300})
    controller = ArmJogController(_adapter(port), clock=clock)   # default settle window

    for _tick in range(5):                 # 5 panel ticks = 1 s of dragging
        controller.set_target(4, 300 + 20 * (_tick + 1))
        clock.advance(FLUSH_INTERVAL_S)
        assert controller.flush() == []     # nothing while the handle moves
    assert port.set_position_frames() == []

    clock.advance(SETTLE_S + 0.01)          # the handle has been still
    results = controller.flush()
    assert len(results) == 1
    moves = port.set_position_frames()
    assert len(moves) == 1                  # one frame for the whole drag
    assert moves[0][2] == [(4, 400)]        # the value the operator stopped on
    assert moves[0][0] == int(round(100 / DEFAULT_SPEED_PPS * 1000))


def test_the_settle_window_is_short_enough_to_still_feel_live() -> None:
    assert SETTLE_S <= 0.5
    assert FLUSH_INTERVAL_S <= SETTLE_S


def test_the_ten_pulse_buttons_are_sent_on_the_next_flush() -> None:
    """A button press is one deliberate act; it must not wait for a settle."""
    port = EchoPort({1: 500})
    controller = _jog(_adapter(port), clock=FakeClock())   # settle 0 for clarity
    controller.set_target(1, 510, immediate=True)
    assert len(controller.flush()) == 1


def test_a_button_press_is_immediate_even_with_a_settle_window() -> None:
    port = EchoPort({1: 500})
    controller = ArmJogController(_adapter(port), clock=FakeClock())  # default settle
    controller.set_target(1, 510, immediate=True)
    assert len(controller.flush()) == 1
    assert port.set_position_frames()[-1][2] == [(1, 510)]


def test_the_flush_interval_is_fast_enough_to_feel_continuous() -> None:
    assert FLUSH_INTERVAL_S <= 0.25


def test_a_dead_port_does_not_raise_from_the_timer_callback() -> None:
    class DeadPort(EchoPort):
        def write(self, data: bytes) -> int:
            raise OSError("port hilang")

    arm = _adapter(DeadPort({1: 500}))
    controller = _jog(arm)
    controller.set_target(1, 600)
    results = controller.flush()            # must not raise
    assert results[0].sent is False