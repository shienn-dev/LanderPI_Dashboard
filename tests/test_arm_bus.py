"""Tests for the bus-servo arm transport (frame bytes, clamps, gripper rule)."""

from __future__ import annotations

import struct

from amr_core.robot.arm_bus import (
    ARM_JOINT_IDS,
    GRIPPER_ID,
    MEASURED_LIMITS,
    MIN_DURATION_S,
    BusServoArmAdapter,
    build_read_position_frame,
    build_set_position_frame,
    build_stop_frame,
    decode_position,
    parse_bus_servo_reply,
)
from amr_core.robot.interfaces import ArmCommand, ConnectionState
from amr_core.robot.stm32_protocol import build_frame


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


class QueuedPort(RecordingPort):
    """A port that answers reads with canned bytes, then stays silent."""

    def __init__(self, replies: dict[int, bytes]) -> None:
        super().__init__()
        self.replies = replies
        self.outstanding: bytes = b""
        self.read_calls = 0

    def reset_input_buffer(self) -> None:
        return None

    def write(self, data: bytes) -> int:
        super().write(data)
        # Answer the question that was just asked, the way the board does.
        # A read frame is: aa 55 05 02 <opcode 05> <servo id> <crc> -- the id is
        # the byte before the CRC, not the last byte (that trap cost one run).
        servo_id = data[5] if len(data) >= 6 and data[4] == 0x05 else None
        self.outstanding = self.replies.get(servo_id, b"")
        return len(data)

    def read(self, size: int = 64) -> bytes:
        self.read_calls += 1
        chunk, self.outstanding = self.outstanding[:size], self.outstanding[size:]
        return chunk


def _position_reply(servo_id: int, pulse: int) -> bytes:
    """The exact reply the board sent on 2026-10-28 for servo 1: 491 -> eb 01."""
    return build_frame(5, bytes((servo_id, 0x05, 0x00)) + pulse.to_bytes(2, "little", signed=True))


def test_move_joints_moves_only_what_was_asked_for() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    adapter.open(port)
    outcome = adapter.move_joints({4: 120}, duration_s=0.8)
    assert outcome.accepted is True and outcome.transmitted is True
    duration_ms, count, moves = decode_frame(port.writes[-1])
    assert duration_ms == 800
    assert count == 1
    assert moves == [(4, 120)]  # joint 4 only: the others are not touched


def test_move_joints_clamps_and_refuses_the_gripper() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    adapter.open(port)
    assert adapter.move_joints({3: 5000}, duration_s=0.8).transmitted is True
    _duration, _count, moves = decode_frame(port.writes[-1])
    assert moves == [(3, MEASURED_LIMITS[3][1])]

    before = len(port.writes)
    grip = adapter.move_joints({10: 300}, duration_s=0.8)
    assert grip.accepted is False and "gripper" in grip.reason
    assert adapter.move_joints({9: 300}, duration_s=0.8).accepted is False
    assert adapter.move_joints({}, duration_s=0.8).accepted is False
    assert len(port.writes) == before  # nothing new reached the wire


def test_the_stop_frame_can_not_reach_the_gripper_either() -> None:
    adapter = BusServoArmAdapter()
    port = RecordingPort()
    adapter.open(port)
    adapter.stop()
    assert GRIPPER_ID not in port.writes[-1]


def test_read_position_frame_is_the_one_the_board_answered() -> None:
    # Measured capture: reading servo 1's position sent exactly these bytes.
    assert build_read_position_frame(1).hex(" ") == "aa 55 05 02 05 01 6f"


def test_a_position_reply_decodes_to_the_pulse() -> None:
    assert decode_position(_position_reply(1, 491)) == 491
    assert decode_position(_position_reply(5, 514)) == 514


def test_a_bad_reply_is_rejected_rather_than_guessed() -> None:
    good = _position_reply(1, 491)
    assert decode_position(good[:-1] + bytes([(good[-1] + 1) & 0xFF])) is None  # bad crc
    # status != 0 is a refusal: the vendor reads it as "no info"
    refused = build_frame(5, bytes((1, 0x05, 0xFF, 0x65, 0x0B)))
    assert parse_bus_servo_reply(refused) is not None
    assert decode_position(refused) is None


def test_read_positions_reports_a_silent_joint_as_none_not_as_a_guess() -> None:
    adapter = BusServoArmAdapter()
    port = QueuedPort({1: _position_reply(1, 491), 2: _position_reply(2, 705)})
    assert adapter.open(port)[0] is True
    positions = adapter.read_positions(timeout_s=0.05)
    assert positions[1] == 491
    assert positions[2] == 705
    assert positions[3] is None and positions[4] is None and positions[5] is None
    assert set(positions) == set(ARM_JOINT_IDS)


def test_read_positions_without_a_port_reports_nothing_rather_than_zero() -> None:
    adapter = BusServoArmAdapter()
    assert adapter.read_positions() == dict.fromkeys(ARM_JOINT_IDS)


def test_submit_rejects_non_integer_positions() -> None:
    adapter = BusServoArmAdapter()
    outcome = adapter.submit(ArmCommand(positions=(500.5,), duration_s=1.0))  # type: ignore[arg-type]
    assert outcome.accepted is False
    assert "integer" in outcome.reason