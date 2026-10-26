"""Chassis control panel tests: the panel must render and never move the robot.

These are not browser tests: they call the panel builder directly, which is
enough to catch a broken render (a missing attribute, a bad NiceGUI call) and
to prove that rendering the panel does not transmit anything.
"""

from __future__ import annotations

import pytest

from amr_core.robot import kinematics
from amr_core.robot.interfaces import ConnectionState
from amr_core.robot.safety import validate_chassis_command
from amr_dashboard import chassis_panel, robot_runtime
from amr_dashboard.robot_runtime import LIVE_LIMITS


def test_offline_panel_renders_and_stays_silent() -> None:
    adapters = robot_runtime.build_adapters(live=False)
    chassis_panel.chassis_control_panel(adapters)
    assert adapters.chassis.state() is ConnectionState.DISABLED
    assert adapters.chassis.last_command() is None
    assert adapters.guard is None


def test_live_panel_renders_without_opening_the_port() -> None:
    """Rendering must not open the port: only the operator's start-up does."""
    adapters = robot_runtime.build_adapters(live=True, port="/dev/does-not-exist")
    chassis_panel.chassis_control_panel(adapters)
    assert adapters.guard is not None
    assert adapters.chassis.state() is ConnectionState.DISABLED
    assert adapters.chassis.last_command() is None


def test_the_hold_command_maps_the_axes_to_the_body_frame() -> None:
    command = chassis_panel._command_for((0.0, 1.0, 0.0), 0.1)
    assert command.linear_x == 0.0
    assert command.linear_y == 0.1
    assert command.angular_z == 0.0
    # The yaw axis does NOT take the slider's m/s number as rad/s. Doing that
    # asked for ~0,05 rps at the slider's minimum -- far below the 0,3 rps stall
    # threshold -- so "Putar" could never move the robot. The yaw rate is the
    # one that drives the wheels as hard as the slider says.
    turn = chassis_panel._command_for((0.0, 0.0, -1.0), 0.1)
    expected = -kinematics.yaw_rate_for_wheel_rate(kinematics.command_for_speed(0.1))
    assert turn.angular_z == pytest.approx(expected)
    assert turn.linear_x == 0.0
    assert turn.linear_y == 0.0


def test_yaw_rate_is_the_inverse_of_the_yaw_term() -> None:
    """A yaw rate must turn every wheel at the rate it was derived from."""
    for rate in (0.3, 0.5, 1.0):
        yaw = kinematics.yaw_rate_for_wheel_rate(rate)
        pairs = kinematics.command_for_body_velocity(0.0, 0.0, yaw)
        peak = max(abs(value) for _motor_id, value in pairs)
        assert peak == pytest.approx(rate, rel=1e-6)


@pytest.mark.parametrize("direction", chassis_panel._DIRECTIONS)
def test_every_direction_clears_the_stall_threshold_at_the_minimum_slider(
    direction: tuple[str, str, str, tuple[float, float, float]],
) -> None:
    """No button may be dead at any slider position.

    This is the regression test for the fault that made the dashboard look
    broken: with ``max_linear_y=0,05`` every strafe command was clamped to
    0,273 rps and with the slider used as rad/s every turn asked for 0,046 rps.
    Both are below the 0,3 rps stall threshold, so the wheels buzzed and the
    robot did not move -- while the status bar happily reported "MOVING".
    """
    _label, _icon, _key, axis = direction
    worst = None
    for speed in (chassis_panel.MIN_SPEED_MPS, 0.1, chassis_panel.MAX_SPEED_MPS):
        command = chassis_panel._command_for(axis, speed)
        clamped, _reason = validate_chassis_command(command, LIVE_LIMITS)
        assert clamped is not None
        pairs = kinematics.drive_command(
            clamped.linear_x, clamped.linear_y, clamped.angular_z
        )
        peak = max(abs(value) for _motor_id, value in pairs)
        if worst is None or peak < worst[0]:
            worst = (peak, speed)
    assert worst is not None
    assert worst[0] >= kinematics.STALL_THRESHOLD_RPS, (
        f"{_label} only reaches {worst[0]:.3f} rps at slider {worst[1]} "
        f"(stall threshold {kinematics.STALL_THRESHOLD_RPS})"
    )


def test_transmitted_rate_reports_the_wire_value_not_the_request() -> None:
    """The status bar must show what the wheels are told, after clamping."""
    command = chassis_panel._command_for((0.0, 1.0, 0.0), chassis_panel.MAX_SPEED_MPS)
    reported = chassis_panel._transmitted_rate(command)
    pairs = kinematics.drive_command(
        command.linear_x, command.linear_y, command.angular_z
    )
    assert reported == pytest.approx(max(abs(v) for _m, v in pairs))
    assert reported <= kinematics.MAX_TESTED_RPS + 1e-9


def test_forward_gets_more_travel_than_the_lateral_axis() -> None:
    """Full slider must be faster forward than sideways.

    Forward/back is the axis the operator asked to speed up; lateral and yaw
    were reported as correct and stay at the measured envelope. The exact ratio
    is a tuning decision (``MAX_FORWARD_RPS``), so this test pins the structure
    -- forward gets the longitudinal cap, lateral does not -- and not a
    particular percentage.
    """
    full = chassis_panel.MAX_SPEED_MPS

    forward = chassis_panel._command_for((1.0, 0.0, 0.0), full)
    forward_pairs = kinematics.drive_command(
        forward.linear_x, forward.linear_y, forward.angular_z
    )
    forward_peak = max(abs(v) for _m, v in forward_pairs)
    assert forward_peak == pytest.approx(kinematics.MAX_FORWARD_RPS, rel=1e-3)
    assert forward_peak > kinematics.MAX_TESTED_RPS

    lateral = chassis_panel._command_for((0.0, 1.0, 0.0), full)
    lateral_pairs = kinematics.drive_command(
        lateral.linear_x, lateral.linear_y, lateral.angular_z
    )
    lateral_peak = max(abs(v) for _m, v in lateral_pairs)
    assert lateral_peak == pytest.approx(kinematics.MAX_TESTED_RPS, rel=1e-3)

    # Backward gets exactly the same treatment as forward.
    backward = chassis_panel._command_for((-1.0, 0.0, 0.0), full)
    backward_pairs = kinematics.drive_command(
        backward.linear_x, backward.linear_y, backward.angular_z
    )
    assert max(abs(v) for _m, v in backward_pairs) == pytest.approx(
        forward_peak, rel=1e-3
    )


def test_a_mixed_command_never_uses_the_forward_cap() -> None:
    """Diagonals and turns stay inside the measured envelope."""
    assert kinematics.rate_cap_for(0.2, 0.0, 0.0) == kinematics.MAX_FORWARD_RPS
    assert kinematics.rate_cap_for(-0.2, 0.0, 0.0) == kinematics.MAX_FORWARD_RPS
    assert kinematics.rate_cap_for(0.2, 0.1, 0.0) == kinematics.MAX_TESTED_RPS
    assert kinematics.rate_cap_for(0.2, 0.0, 0.3) == kinematics.MAX_TESTED_RPS
    assert kinematics.rate_cap_for(0.0, 0.1, 0.0) == kinematics.MAX_TESTED_RPS


def test_the_longitudinal_gain_is_not_clamped_away_by_the_limits() -> None:
    """LIVE_LIMITS must let the longitudinal gain through untouched.

    This is the guard against silently undoing a future retune: raise
    ``MAX_FORWARD_RPS`` and forget this limit, and the clamp quietly trims the
    command back down -- the operator just sees "still too slow" with no error.
    """
    needed = kinematics.speed_for_rate(kinematics.MAX_FORWARD_RPS)
    assert LIVE_LIMITS.max_linear_x >= needed - 1e-9

    command = chassis_panel._command_for((1.0, 0.0, 0.0), chassis_panel.MAX_SPEED_MPS)
    clamped, _reason = validate_chassis_command(command, LIVE_LIMITS)
    assert clamped is not None
    # Not trimmed at all, not merely close.
    assert clamped.linear_x == pytest.approx(command.linear_x, rel=1e-9)
    assert clamped.linear_x == pytest.approx(needed, rel=1e-3)


def test_rate_note_warns_below_the_stall_threshold() -> None:
    assert "AMBANG STALL" in chassis_panel._rate_note(0.0)
    assert "AMBANG STALL" in chassis_panel._rate_note(0.1)
    assert chassis_panel._rate_note(1.0) == ""
