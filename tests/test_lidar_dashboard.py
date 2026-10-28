"""Tests for the LiDAR dashboard panel (SVG rendering) and runtime singleton."""

from __future__ import annotations

import re

import pytest

from amr_core.lidar.protocol import POINTS_PER_PACKET, build_packet, decode_packet
from amr_core.lidar.scan import ScanAccumulator
from amr_dashboard import lidar_panel, lidar_runtime


def _snapshot(packets: int = 3):
    acc = ScanAccumulator(buckets=360)
    for k in range(packets):
        start = (k * 12) % 360
        packet = decode_packet(
            build_packet(
                speed_dps=3580,
                start_angle_deg=float(start),
                end_angle_deg=float((start + 11) % 360),
                timestamp_ms=0,
                measurements=[(1000, 1)] * POINTS_PER_PACKET,
            )
        )
        acc.add_packet(packet)
    return acc.snapshot()


def test_render_scan_svg_is_well_formed() -> None:
    svg = lidar_panel.render_scan_svg(_snapshot())
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "circle" in svg  # at least the background ring
    # One dot per valid point (plus background/rings/crosshair lines).
    assert svg.count("<circle") > len(_snapshot().points)


def test_render_scan_svg_rejects_bad_arguments() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError):
        lidar_panel.render_scan_svg(snapshot, size=0)
    with pytest.raises(ValueError):
        lidar_panel.render_scan_svg(snapshot, max_range_mm=0)


def test_render_scan_svg_skips_invalid_points() -> None:
    acc = ScanAccumulator(buckets=360)
    packet = decode_packet(
        build_packet(
            speed_dps=3580,
            start_angle_deg=0.0,
            end_angle_deg=11.0,
            timestamp_ms=0,
            measurements=[(0, 0)] * POINTS_PER_PACKET,  # all invalid
        )
    )
    acc.add_packet(packet)
    svg = lidar_panel.render_scan_svg(acc.snapshot())
    # Background + 4 range rings only: no data dots.
    assert svg.count("<circle") == 5


def _point_at(angle_deg: float, distance_mm: int = 1000):
    """One valid return, placed at a chosen angle of the LiDAR's own frame."""
    acc = ScanAccumulator(buckets=360)
    acc.add_packet(
        decode_packet(
            build_packet(
                speed_dps=3580,
                start_angle_deg=angle_deg,
                end_angle_deg=(angle_deg + 11.0) % 360.0,
                timestamp_ms=0,
                measurements=[(distance_mm, 1)] * POINTS_PER_PACKET,
            )
        )
    )
    return acc.snapshot()


def _data_dots(svg: str) -> list[tuple[float, float]]:
    """The plotted scan dots (r=1.8), as (x, y) on the SVG canvas."""
    return [
        (float(x), float(y))
        for x, y in re.findall(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="1\.8"', svg)
    ]


def test_the_plot_puts_the_front_up_and_the_robots_left_on_the_left() -> None:
    """A bottle on the floor proved the raw LiDAR frame is clockwise.

    Measured 2026-10-28, same bottle, one 10 s scan per placement: on the
    robot's front-left (~1,17 m) it appeared in 315-330 deg, on the front-right
    (~1,07 m) it appeared in 30-60 deg, and every other sector stayed put within
    13 mm. Drawn as a top-down view with the front up, a point in 315-330 deg
    must land in the upper-left quadrant and a point in 30-60 deg in the
    upper-right one. Drawing the raw angle directly mirrored the room instead.
    """
    assert lidar_panel.LIDAR_ANGLE_CLOCKWISE is True
    center = 150.0
    left = _data_dots(lidar_panel.render_scan_svg(_point_at(315.0)))
    right = _data_dots(lidar_panel.render_scan_svg(_point_at(45.0)))
    assert left and right
    # Both sectors are in front of the robot, so both are above the centre.
    assert all(y < center for _x, y in left + right)
    assert all(x < center for x, _y in left)   # kiri robot = kiri plot
    assert all(x > center for x, _y in right)  # kanan robot = kanan plot


def test_the_front_marker_is_the_robot_and_carries_no_label() -> None:
    """Operator: "gausah dikasi tulisan depan ... ga kaya geometri jelek gitu"."""
    svg = lidar_panel.render_scan_svg(
        _snapshot(), front_offset_deg=lidar_panel.LIDAR_FRONT_OFFSET_DEG
    )
    assert '<g class="robot-marker"' in svg
    group = svg.split('<g class="robot-marker" transform="rotate(', 1)[1]
    rotation = float(group.split(" ", 1)[0])
    assert 0.0 <= rotation <= 5.0   # nose up, only the 1,0 deg mount offset
    assert "DEPAN" not in svg       # no word on the plot
    assert "<polygon" not in svg    # no triangle
    assert svg.count('class="wheel"') == 4


def _body_rect(svg: str) -> tuple[float, float]:
    """(width, height) of the chassis rectangle in px, from the rendered SVG."""
    group = svg.split('<g class="robot-marker"', 1)[1]
    rect = group.split('<rect x="', 1)[1].split("/>", 1)[0]
    width = float(rect.split('width="', 1)[1].split('"', 1)[0])
    height = float(rect.split('height="', 1)[1].split('"', 1)[0])
    return width, height


def test_the_robot_is_drawn_to_scale_so_a_one_metre_gap_looks_like_one_metre() -> None:
    """Operator: a big marker made a 1,17 m wall look like it touched the robot.

    Footprint is nominal (``ROBOT_FOOTPRINT_MM``) but the scale is real: every
    pixel the robot occupies comes from millimetres times the plot's own
    px/millimetre, so it shrinks and grows with the display range instead of
    sitting there as a fixed 32 px symbol that ate the gap to the wall.
    """
    width_mm, length_mm = lidar_panel.ROBOT_FOOTPRINT_MM
    radius = 300 / 2 - 8
    px_per_mm = radius / lidar_panel._DEFAULT_MAX_RANGE_MM
    width, height = _body_rect(
        lidar_panel.render_scan_svg(
            _snapshot(), front_offset_deg=lidar_panel.LIDAR_FRONT_OFFSET_DEG
        )
    )
    assert width == pytest.approx(width_mm * px_per_mm, abs=0.05)
    assert height == pytest.approx(length_mm * px_per_mm, abs=0.05)
    # At 4 m the chassis is ~12 px long: a wall at 1,17 m sits 41 px away, so the
    # gap now reads as the metre it is instead of as 10 px of empty space.
    assert height < 14.0

    zoomed = _body_rect(
        lidar_panel.render_scan_svg(
            _snapshot(),
            front_offset_deg=lidar_panel.LIDAR_FRONT_OFFSET_DEG,
            max_range_mm=lidar_panel._DEFAULT_MAX_RANGE_MM / 2,
        )
    )
    assert zoomed[1] == pytest.approx(2 * height, rel=0.02)


def test_runtime_exposes_a_single_shared_reader() -> None:
    lidar_runtime.reset_lidar_runtime()
    try:
        first = lidar_runtime.get_lidar_reader()
        second = lidar_runtime.get_lidar_reader()
        assert first is second  # one reader per process -> one port owner
    finally:
        lidar_runtime.reset_lidar_runtime()


def test_runtime_configure_replaces_config_before_use() -> None:
    from amr_core.lidar.config import LidarConfig

    lidar_runtime.reset_lidar_runtime()
    try:
        lidar_runtime.configure(LidarConfig(port="/dev/ttyUSB9", enabled=False))
        reader = lidar_runtime.get_lidar_reader()
        assert reader.config.port == "/dev/ttyUSB9"
        assert reader.config.enabled is False
        # Disabled config means start_lidar() does not open the port.
        assert lidar_runtime.start_lidar() is False
    finally:
        lidar_runtime.reset_lidar_runtime()
