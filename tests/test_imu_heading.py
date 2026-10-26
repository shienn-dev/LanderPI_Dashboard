"""Heading from the board's IMU, and the orientation cues on the LiDAR plot.

The operator could not tell which way the plot was pointing ("aku bingung ini dia
ngedeteksi yang mana ya"), and asked for the robot's facing to be shown. Before
any of this was drawn, two things were *measured* on the robot (sesi 6 §12.9):

* `gz` is the yaw axis and its unit is degrees/second (+-90 deg hand rotation
  integrated to 96,8 deg*s; rad/s would have given 1,5708), with `+gz` = turning
  left, confirmed by the operator;
* the LiDAR's 0 deg points at the robot's front: fitting a flat arena wall as
  d = D/cos(theta - theta0) gave theta0 = 1,0 deg with a 5 mm residual, and the
  arc the robot's own body blocks is centred on 180,0 deg.

These tests lock in the arithmetic and the honesty of the display: no heading is
claimed before an IMU sample exists, a long silence is not integrated as motion,
and the plot always names the front and separates the robot's own returns.
"""

from __future__ import annotations

import math

import pytest

from amr_core.robot.imu import DEFAULT_DEADBAND_DPS, YawIntegrator
from amr_core.robot.stm32_protocol import ImuReading
from amr_dashboard import lidar_panel, robot_runtime


class FakeClock:
    def __init__(self, start: float = 500.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _reading(gz: float, *, gx: float = 0.0, gy: float = 0.0) -> ImuReading:
    return ImuReading(ax=0.03, ay=0.09, az=1.027, gx=gx, gy=gy, gz=gz)


# --------------------------------------------------------------------------- #
# Integration
# --------------------------------------------------------------------------- #

def test_integrating_a_ninety_degree_left_turn_gives_ninety_degrees() -> None:
    """The measured scale: gz is deg/s, so a 90 deg turn integrates to 90 deg."""
    clock = FakeClock()
    integrator = YawIntegrator(clock=clock)

    # 45 deg/s for 2 s = 90 deg. The measured peak during a hand rotation was
    # 96-128 deg/s, so this is a realistic rate. The first sample only sets the
    # time reference (there is no previous stamp to measure a step against), so
    # 100 samples at 50 Hz integrate 99 steps = 1,98 s.
    for _ in range(100):
        clock.now += 0.02
        integrator.update(_reading(45.0))

    assert integrator.available is True
    assert integrator.heading_deg == pytest.approx(45.0 * 0.02 * 99, abs=0.05)
    assert integrator.seconds_integrated == pytest.approx(1.98, abs=0.01)


def test_turning_right_gives_a_negative_heading() -> None:
    clock = FakeClock()
    integrator = YawIntegrator(clock=clock)
    for _ in range(50):
        clock.now += 0.02
        integrator.update(_reading(-45.0))
    assert integrator.heading_deg == pytest.approx(-45.0 * 0.02 * 49, abs=0.05)


def test_a_silent_board_is_not_integrated_as_rotation() -> None:
    """The board stays deaf for ~2,3 s after the port opens: don't invent an angle."""
    clock = FakeClock()
    integrator = YawIntegrator(clock=clock)
    integrator.update(_reading(45.0))
    clock.now += 2.3  # the boot window
    integrator.update(_reading(45.0))

    assert integrator.heading_deg == pytest.approx(0.0)
    assert integrator.skipped_steps == 1


def test_at_rest_noise_does_not_accumulate() -> None:
    """Measured at-rest spread on gz is +-0,03 deg/s; a deadband eats it."""
    clock = FakeClock()
    integrator = YawIntegrator(clock=clock)
    for index in range(600):  # 12 s at 50 Hz
        clock.now += 0.02
        integrator.update(_reading(0.03 if index % 2 else -0.03))

    assert abs(integrator.heading_deg) < 0.05
    # ...and rotation is still integrated: the deadband is far below any real turn.
    assert DEFAULT_DEADBAND_DPS < 1.0


def test_reset_makes_the_current_facing_the_new_zero() -> None:
    clock = FakeClock()
    integrator = YawIntegrator(clock=clock)
    for _ in range(50):
        clock.now += 0.02
        integrator.update(_reading(90.0))
    assert integrator.heading_deg > 40

    integrator.reset()
    assert integrator.heading_deg == 0.0
    assert integrator.available is False
    assert integrator.samples == 0


def test_the_heading_is_reported_as_unavailable_before_any_sample() -> None:
    integrator = YawIntegrator()
    assert integrator.available is False
    assert "belum ada data IMU" in lidar_panel_heading_text(integrator)
    assert "belum ada data IMU" in _chassis_heading_text(integrator)


def lidar_panel_heading_text(integrator) -> str:
    """The dial must not draw a zero it has not measured."""
    svg = lidar_panel.heading_dial_svg(
        integrator.heading_deg if integrator.available else None
    )
    return svg


def _chassis_heading_text(integrator) -> str:
    from amr_dashboard import chassis_panel

    return chassis_panel._heading_text(integrator)


def test_the_live_adapter_feeds_the_process_wide_integrator() -> None:
    """Wiring: the heading the panel shows comes from the port the adapter owns."""
    robot_runtime.reset_adapters()
    factory_port = _NullPort()
    adapters = robot_runtime.build_adapters(
        live=True, port="/dev/fake", port_factory=lambda _p, _b: factory_port,
        settle_s=0.0,
    )
    robot_runtime._adapters = adapters
    integrator = robot_runtime.yaw_integrator()

    # A fresh live set resets the reference.
    integrator.update(_reading(45.0))
    assert integrator.samples == 1
    robot_runtime.build_adapters(live=True, port="/dev/fake")
    assert integrator.samples == 0

    # The adapter's read path is wired to the integrator.
    adapter = adapters.chassis
    listener = adapter._imu_listener
    assert listener is not None
    listener(_reading(45.0))
    assert integrator.samples == 1
    robot_runtime.reset_adapters()


class _NullPort:
    """A port that supports telemetry reads, as the board's does."""

    def __init__(self) -> None:
        self.buffer = b""

    @property
    def in_waiting(self) -> int:
        return len(self.buffer)

    def read(self, size: int) -> bytes:
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def write(self, data: bytes, /):
        return len(data)

    def flush(self) -> None: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# The plot: front marker and self-returns
# --------------------------------------------------------------------------- #

def _snapshot():
    from amr_core.lidar.protocol import LidarPacket
    from amr_core.lidar.scan import ScanAccumulator

    accumulator = ScanAccumulator(buckets=360)
    for step in range(30):
        start = step * 12.0
        accumulator.add_packet(
            LidarPacket(
                speed_dps=360,
                start_angle_deg=start,
                end_angle_deg=start + 11.99,
                timestamp_ms=step * 20,
                measurements=tuple((500, 50) for _ in range(12)),
            )
        )
    return accumulator.snapshot()


def test_the_plot_draws_the_front_arrow_at_the_measured_offset() -> None:
    svg = lidar_panel.render_scan_svg(
        _snapshot(), front_offset_deg=lidar_panel.LIDAR_FRONT_OFFSET_DEG
    )
    assert "DEPAN" in svg
    # The marker points along the LiDAR's 0 deg (measured offset ~1 deg), i.e.
    # along +x from the centre: the arrow tip is to the right of centre.
    assert lidar_panel.LIDAR_FRONT_OFFSET_DEG == pytest.approx(1.0)
    tip = _marker_tip(svg)
    assert tip[0] > 150 + 30  # right of centre by roughly the arrow length
    assert abs(tip[1] - 150) < 12


def _marker_tip(svg: str) -> tuple[float, float]:
    """First point of the DEPAN polygon, from the rendered SVG."""
    polygon = svg.split('<polygon points="', 1)[1].split('"', 1)[0]
    first = polygon.split(" ", 1)[0]
    x, y = first.split(",")
    return float(x), float(y)


def test_the_plot_has_no_orientation_marker_unless_asked() -> None:
    """Kept opt-in so the plot without a measured offset cannot imply one."""
    assert "DEPAN" not in lidar_panel.render_scan_svg(_snapshot())


def test_the_plot_separates_the_robots_own_returns() -> None:
    """The robot's own body must not be drawn like an obstacle.

    Measured: the body blocks 105-255 deg at 20-30 mm. Those points must be
    grey, and the panel reports how many there are.
    """
    from amr_core.lidar.protocol import LidarPacket
    from amr_core.lidar.scan import ScanAccumulator

    accumulator = ScanAccumulator(buckets=360)
    for step in range(30):
        start = step * 12.0
        distance = 20 if 120 <= start < 240 else 900
        accumulator.add_packet(
            LidarPacket(
                speed_dps=360,
                start_angle_deg=start,
                end_angle_deg=start + 11.99,
                timestamp_ms=step * 20,
                measurements=tuple((distance, 50) for _ in range(12)),
            )
        )
    svg = lidar_panel.render_scan_svg(accumulator.snapshot())
    assert svg.count('fill="#64748b"') > 50   # the self-returns, drawn grey
    assert lidar_panel.SELF_RETURN_MM == pytest.approx(60.0)
    assert all(
        point.distance_mm < lidar_panel.SELF_RETURN_MM
        for point in accumulator.snapshot().points
        if 120 <= point.angle_deg < 240
    )


def test_the_dial_shows_a_zero_heading_only_when_it_was_measured() -> None:
    unknown = lidar_panel.heading_dial_svg(None)
    assert "belum ada data IMU" in unknown
    assert "+0.0 deg" not in unknown

    known = lidar_panel.heading_dial_svg(37.5)
    assert "37.5 deg" in known
    # A left turn (positive heading) points counter-clockwise: up-left on screen.
    needle = known.split('stroke="#f59e0b"', 1)[0].rsplit("<line", 1)[1]
    x2 = float(needle.split('x2="', 1)[1].split('"', 1)[0])
    y2 = float(needle.split('y2="', 1)[1].split('"', 1)[0])
    center = 120 / 2.0
    assert x2 < center and y2 < center


def test_the_dial_uses_the_screen_convention_of_the_scan_plot() -> None:
    """Heading 0 points up; the dial and the plot must not disagree on handedness."""
    up = lidar_panel.heading_dial_svg(0.0)
    needle = up.split('stroke="#f59e0b"', 1)[0].rsplit("<line", 1)[1]
    x2 = float(needle.split('x2="', 1)[1].split('"', 1)[0])
    y2 = float(needle.split('y2="', 1)[1].split('"', 1)[0])
    assert x2 == pytest.approx(60.0, abs=0.5)
    assert y2 < 60.0
    # Sanity: at 90 deg left it points along -x (left of the dial).
    left = lidar_panel.heading_dial_svg(90.0)
    needle = left.split('stroke="#f59e0b"', 1)[0].rsplit("<line", 1)[1]
    x2 = float(needle.split('x2="', 1)[1].split('"', 1)[0])
    assert x2 < 60.0 and math.isclose(x2 - 60.0, -42.0, abs_tol=1.0)
