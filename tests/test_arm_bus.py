"""Tests for the bus-servo arm transport (frame bytes, clamps, gripper rule)."""

from __future__ import annotations

import struct

from amr_core.robot.arm_bus import (
    ARM_JOINT_IDS,
    GRIPPER_ID,
    MEASURED_LIMITS,
    MIN_DURATION_S,
    BusServoArmAdapter,
    build_set_position_frame,
    build_stop_frame,
)
from amr_core.robot.interfaces import ArmCommand, ConnectionState


class RecordingPort:
    """Stands in for a serial port: records writes, never talks to hardware."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        return len(data)

    def close(self) -> None:
        self.closed = True


def _vendor_frame(duration_s: float, positions: list[tuple[int, int]]) -> bytes:
    """The vendor SDK's own construction, re-derived here on purpose.

    ``bus_servo_set_position`` in ``ros_robot_controller_sdk.py``: payload is
    ``01 <dur_lo> <dur_hi> <count>`` then ``<id> <pulse_lo> <pulse_hi>`` per
    servo, wrapped by ``buf_write`` as ``AA 55 <func> <len> payload crc8``.
    """
    from amr_core.robot.stm32_protocol import crc8

    duration = int(duration_s * 1000)
    payload = [0x01, duration & 0xFF, 0xFF & (duration >> 8), len(positions)]
    for servo_id, pulse in positions:
        payload.extend(struct.pack("<BH", servo_id, pulse))
    buf = [0xAA, 0x55, 5, len(payload), *payload]
    buf.append(crc8(bytes(buf[2:])))
    return bytes(buf)


def decode_frame(frame: bytes) -> tuple[int, int, list[tuple[int, int]]]:
    """(duration_ms, count, [(id, pulse), ...]) from one set-position frame."""
    assert frame[:3] == b"\xaa\x55\x05"
    length = frame[3]
    assert len(frame) == 4 + length + 1
    payload = frame[4 : 4 + length]
    assert payload[0] == 0x01
    duration_ms = payload[1] | (payload[2] << 8)
    count = payload[3]
    moves = []
    for index in range(count):
        base = 4 + index * 3
        servo_id = payload[base]
        pulse = payload[base + 1] | (payload[base + 2] << 8)
        moves.append((servo_id, pulse))
    return duration_ms, count, moves


def test_frame_matches_the_vendor_layout_byte_for_byte() -> None:
    cases = [
        (2.0, [(1, 500), (5, 530)]),
        (1.5, [(3, 60)]),
        (0.5, [(1, 50), (2, 40), (3, 0), (4, 70), (5, 50)]),
    ]
    for duration, moves in cases:
        assert build_set_position_frame(duration, moves) == _vendor_frame(duration, moves)


def test_the_five_joints_are_what_the_measured_limits_cover() -> None:
    assert ARM_JOINT_IDS == (1, 2, 3, 4, 5)
    assert set(MEASURED_LIMITS) == set(ARM_JOINT_IDS)
    assert GRIPPER_ID not in ARM_JOINT_IDS


def test_positions_are_clamped_to_each_servos_measured_limit() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    assert adapter.open(port)[0] is True
    # 0 and 1000 are inside the generic 0..1000 envelope but outside the
    # measured limits of every joint, so each must be clamped.
    outcome = adapter.submit(ArmCommand(positions=(0, 1000, 0, 1000, 0), duration_s=1.0))
    assert outcome.accepted is True and outcome.transmitted is True
    _duration, _count, moves = decode_frame(port.writes[-1])
    for servo_id, pulse in moves:
        low, high = MEASURED_LIMITS[servo_id]
        assert low <= pulse <= high


def test_a_command_carrying_the_gripper_is_refused_and_sends_nothing() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    adapter.open(port)
    outcome = adapter.submit(ArmCommand(positions=(500, 500, 125, 165, 500, 200), duration_s=1.0))
    assert outcome.accepted is False
    assert outcome.transmitted is False
    assert "gripper" in outcome.reason.lower()
    assert port.writes == []


def test_a_too_fast_move_is_refused() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    adapter.open(port)
    outcome = adapter.submit(ArmCommand(positions=(500,), duration_s=MIN_DURATION_S / 2))
    assert outcome.accepted is False
    assert "too fast" in outcome.reason
    assert port.writes == []


def test_without_an_open_port_the_command_is_validated_but_not_transmitted() -> None:
    adapter = BusServoArmAdapter()
    outcome = adapter.submit(ArmCommand(positions=(500, 500, 125, 165, 500), duration_s=1.0))
    assert outcome.accepted is True
    assert outcome.transmitted is False
    assert "not open" in outcome.reason
    assert adapter.state() is ConnectionState.DISABLED
    # The frame that *would* go out is still available for inspection.
    assert adapter.stats.last_frame[:3] == b"\xaa\x55\x05"


def test_open_without_a_port_refuses_and_says_where_to_open_it() -> None:
    """This package may not import pyserial; the opener lives in the dashboard."""
    adapter = BusServoArmAdapter()
    ok, reason = adapter.open(None)
    assert ok is False
    assert "arm_transport" in reason
    assert adapter.state() is ConnectionState.DISCONNECTED


def test_open_adopts_the_port_and_reports_connected() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    ok, reason = adapter.open(port)
    assert ok is True and "open" in reason
    assert adapter.state() is ConnectionState.CONNECTED
    assert adapter.open(port)[1] == "already open"
    adapter.close()
    assert port.closed is True
    assert adapter.state() is ConnectionState.DISABLED


def test_stop_lists_the_five_joints_and_nothing_else() -> None:
    frame = build_stop_frame(ARM_JOINT_IDS)
    assert frame[:3] == b"\xaa\x55\x05"
    payload = frame[4:-1]
    assert payload[0] == 0x03
    assert payload[1] == len(ARM_JOINT_IDS)
    assert tuple(payload[2:]) == ARM_JOINT_IDS
    assert GRIPPER_ID not in payload[2:]


def test_submit_rejects_non_integer_positions() -> None:
    adapter = BusServoArmAdapter()
    outcome = adapter.submit(ArmCommand(positions=(500.5,), duration_s=1.0))  # type: ignore[arg-type]
    assert outcome.accepted is False
    assert "integer" in outcome.reason