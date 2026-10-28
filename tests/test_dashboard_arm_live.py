"""Tests for the live arm path: opt-in, silent until pressed, gripper-free."""

from __future__ import annotations

from amr_core.robot.interfaces import ArmCommand, ConnectionState
from amr_dashboard import robot_panel, robot_runtime


class FakeArmPort:
    """A port that records writes and answers reads with silence."""

    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        return len(data)

    def read(self, _size: int = 64) -> bytes:
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _factory(port: FakeArmPort):
    def open_port(_name: str, _baud: int | None = None) -> FakeArmPort:
        return port

    return open_port


def test_arm_stays_offline_without_the_flag() -> None:
    robot_runtime.reset_adapters()
    try:
        adapters = robot_runtime.get_adapters()
        assert adapters.arm_live is False
        outcome = adapters.arm.submit(ArmCommand(positions=(500, 500), duration_s=1.0))
        assert outcome.transmitted is False
    finally:
        robot_runtime.reset_adapters()


def test_activating_the_arm_opens_one_port_and_moves_nothing() -> None:
    """Opening a port is not a motion command -- the same rule as the chassis."""
    robot_runtime.reset_adapters()
    port = FakeArmPort()
    try:
        activation = robot_runtime.activate_live_arm(
            "/dev/fake", port_factory=_factory(port)
        )
        assert activation.ok is True
        adapters = robot_runtime.get_adapters()
        assert adapters.arm_live is True
        assert adapters.arm.state() is ConnectionState.CONNECTED
        assert port.writes == []          # nothing on the wire just from opening

        # Idempotent: a second call must not open a second port.
        again = robot_runtime.activate_live_arm("/dev/fake", port_factory=_factory(FakeArmPort()))
        assert again.ok is True and "sudah LIVE" in again.message

        # One step, one frame, joint 4 only, gripper never.
        outcome = adapters.arm.move_joints({4: 120}, duration_s=0.8)
        assert outcome.transmitted is True
        assert len(port.writes) == 1
        assert adapters.arm.move_joints({10: 300}, duration_s=0.8).accepted is False
        assert len(port.writes) == 1
    finally:
        robot_runtime.reset_adapters()


def test_the_live_panel_renders_without_offering_the_gripper() -> None:
    robot_runtime.reset_adapters()
    try:
        robot_runtime.activate_live_arm("/dev/fake", port_factory=_factory(FakeArmPort()))
        adapters = robot_runtime.get_adapters()
        robot_panel.arm_control_panel(adapters)   # must not raise
        assert adapters.arm_live is True
    finally:
        robot_runtime.reset_adapters()
