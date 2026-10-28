"""Bus-servo arm transport: the frame builder and a real (opt-in) adapter.

Everything here is measured, not assumed:

- Frame layout from the vendor SDK shipped with this robot family
  (``arm_pc/ros_robot_controller_sdk.py``, ``bus_servo_set_position``)::

      payload = 01 <duration_lo> <duration_hi> <count> [<id> <pulse_lo> <pulse_hi>]*
      frame   = AA 55 <func=5> <len> <payload> crc8

  Verified byte-for-byte against the vendor's own ``buf_write`` before any of
  this was pointed at hardware.
- ``MEASURED_LIMITS`` are the servos' own angle limits, read from the servos on
  2026-10-28 with ``tools/arm_probe.py`` (id: low, high in pulses). They are
  tighter than the generic 0..1000 and are used as the clamp, so a bad command
  cannot drive a joint into its mechanical stop.
- The gripper (servo 10) is **excluded**. Operator rule: "saat udah gerakin,
  JANGAN SENTUH GRIPER". A command that carries a sixth position is refused
  rather than silently dropped, because a silently dropped joint is worse.

Nothing in this module runs by itself: the adapter is constructed, never
registered, and only transmits after ``open()`` succeeds.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from amr_core.robot.interfaces import ArmCommand, CommandOutcome, ConnectionState
from amr_core.robot.safety import validate_arm_command
from amr_core.robot.stm32_protocol import build_frame

PACKET_FUNC_BUS_SERVO = 5
SUB_SET_POSITION = 0x01
SUB_STOP = 0x03

#: The five arm joints this project may command, in command order.
ARM_JOINT_IDS: tuple[int, ...] = (1, 2, 3, 4, 5)

#: The gripper. Never commanded from here (operator rule).
GRIPPER_ID = 10

#: Measured 2026-10-28 on this unit, read from each servo's own angle limit.
MEASURED_LIMITS: dict[int, tuple[int, int]] = {
    1: (50, 950),
    2: (40, 960),
    3: (0, 900),
    4: (70, 970),
    5: (50, 950),
}

#: The arm is not a wheel: below this the joints jerk instead of moving.
MIN_DURATION_S = 0.5


def build_set_position_frame(duration_s: float, moves: list[tuple[int, int]]) -> bytes:
    """One ``set position`` frame for ``[(servo id, pulse), ...]``."""
    if not moves:
        raise ValueError("no joints to move")
    duration_ms = int(round(duration_s * 1000.0))
    payload = struct.pack("<BHB", SUB_SET_POSITION, duration_ms & 0xFFFF, len(moves))
    for servo_id, pulse in moves:
        payload += struct.pack("<BH", servo_id, pulse)
    return build_frame(PACKET_FUNC_BUS_SERVO, payload)


def build_stop_frame(ids: tuple[int, ...] | list[int]) -> bytes:
    """The vendor's bus-servo stop frame (``0x03``, count, ids)."""
    return build_frame(PACKET_FUNC_BUS_SERVO, bytes([SUB_STOP, len(ids), *ids]))


@dataclass
class ArmTransportStats:
    frames_sent: int = 0
    last_frame: bytes = b""
    last_reason: str = ""


class BusServoArmAdapter:
    """Serial transport for the five arm joints. Opt-in, one port owner.

    Mirrors the chassis adapter's contract: ``submit()`` validates and clamps,
    reports ``transmitted=False`` when the port is not open, and never opens a
    port by itself.
    """

    name = "bus-servo"

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 1_000_000,
        *,
        settle_s: float = 3.0,
        limits: dict[int, tuple[int, int]] | None = None,
    ) -> None:
        self.port_name = port
        self.baud = baud
        # The board ignores frames for ~2,36 s after every open (measured).
        self.settle_s = settle_s
        self.limits = dict(limits or MEASURED_LIMITS)
        self._port = None
        self._state = ConnectionState.DISABLED
        self._last: ArmCommand | None = None
        self.stats = ArmTransportStats()

    # -- state -----------------------------------------------------------
    def state(self) -> ConnectionState:
        return self._state

    def last_command(self) -> ArmCommand | None:
        return self._last

    # -- lifecycle -------------------------------------------------------
    def open(self, port) -> tuple[bool, str]:
        """Adopt an ALREADY OPEN port. Never raises, never imports pyserial.

        This package is not allowed to import pyserial -- there is a guard test
        for it (`tests/test_robot_no_actuation.py`), and the reason holds: the
        safety-critical robot package must be importable without a serial stack.
        The device is opened in the dashboard layer
        (`amr_dashboard.arm_transport.open_arm_port`, which reuses the chassis
        opener so DTR/RTS are lowered the same way) and handed in here.
        """
        if self._port is not None:
            return True, "already open"
        if port is None:
            self._state = ConnectionState.DISCONNECTED
            return (
                False,
                "no port supplied: open it in the dashboard layer "
                "(amr_dashboard.arm_transport.open_arm_port) and pass it here",
            )
        self._port = port
        self._state = ConnectionState.CONNECTED
        return True, f"adopted open port {self.port_name} @ {self.baud}"

    def close(self) -> None:
        port, self._port = self._port, None
        self._state = ConnectionState.DISABLED
        if port is not None:
            try:
                port.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass

    # -- commands --------------------------------------------------------
    def submit(self, command: ArmCommand) -> CommandOutcome:
        validated, reason = validate_arm_command(command)
        if validated is None:
            return self._refuse(reason)

        joints = tuple(zip(ARM_JOINT_IDS, validated.positions, strict=False))
        if len(validated.positions) > len(ARM_JOINT_IDS):
            return self._refuse(
                f"command carries {len(validated.positions)} positions; servo "
                f"{GRIPPER_ID} (gripper) is excluded by operator rule -- the arm "
                f"adapter drives ids {list(ARM_JOINT_IDS)} only"
            )
        if not joints:
            return self._refuse("no positions given")

        if validated.duration_s < MIN_DURATION_S:
            return self._refuse(
                f"duration {validated.duration_s:.2f} s < {MIN_DURATION_S} s: too fast for the arm"
            )

        clamped: list[tuple[int, int]] = []
        for servo_id, pulse in joints:
            low, high = self.limits[servo_id]
            clamped.append((servo_id, max(low, min(high, pulse))))

        frame = build_set_position_frame(validated.duration_s, clamped)
        self._last = validated
        if self._port is None:
            self.stats.last_frame = frame
            self.stats.last_reason = "validated; arm port not open (nothing transmitted)"
            return CommandOutcome(
                accepted=True, transmitted=False, reason=self.stats.last_reason
            )
        try:
            self._port.write(frame)
        except Exception as exc:  # noqa: BLE001
            self.stats.last_reason = f"write failed: {type(exc).__name__}: {exc}"
            return CommandOutcome(accepted=False, transmitted=False, reason=self.stats.last_reason)
        self.stats.frames_sent += 1
        self.stats.last_frame = frame
        self.stats.last_reason = "transmitted"
        return CommandOutcome(accepted=True, transmitted=True, reason="transmitted")

    def stop(self) -> CommandOutcome:
        self._last = ArmCommand()
        frame = build_stop_frame(ARM_JOINT_IDS)
        if self._port is None:
            self.stats.last_frame = frame
            return CommandOutcome(
                accepted=True,
                transmitted=False,
                reason="stop validated; arm port not open (nothing transmitted)",
            )
        try:
            self._port.write(frame)
        except Exception as exc:  # noqa: BLE001
            return CommandOutcome(accepted=False, transmitted=False, reason=f"write failed: {exc}")
        self.stats.frames_sent += 1
        self.stats.last_frame = frame
        return CommandOutcome(accepted=True, transmitted=True, reason="stop transmitted")

    # -- helpers ---------------------------------------------------------
    def _refuse(self, reason: str) -> CommandOutcome:
        self.stats.last_reason = reason
        return CommandOutcome(accepted=False, transmitted=False, reason=reason)