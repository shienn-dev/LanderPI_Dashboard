"""NiceGUI panel for the *live* LiDAR (real hardware).

The panel is read-only and separated from the serial reader: it only calls
``reader.snapshot()`` / ``reader.stats()`` and renders the result. The scan is
drawn as an inline SVG polar plot, which needs no extra dependency.

This data comes from the physical LiDAR and is labelled as such — it is kept
visually distinct from the simulated prototype data elsewhere on the dashboard.
"""

from __future__ import annotations

import math

from nicegui import ui

from amr_core.lidar.reader import LidarReader, LidarStatus
from amr_core.lidar.scan import ScanSnapshot
from amr_dashboard import robot_runtime

# Colour per status (NiceGUI badge colour name).
_STATUS_COLOR: dict[LidarStatus, str] = {
    LidarStatus.RUNNING: "green-7",
    LidarStatus.CONNECTING: "amber-7",
    LidarStatus.ERROR: "red-7",
    LidarStatus.STOPPED: "grey-7",
    LidarStatus.UNAVAILABLE: "orange-8",
}

_STATUS_LABEL: dict[LidarStatus, str] = {
    LidarStatus.RUNNING: "LIVE — reading hardware",
    LidarStatus.CONNECTING: "connecting…",
    LidarStatus.ERROR: "error — retrying",
    LidarStatus.STOPPED: "stopped",
    LidarStatus.UNAVAILABLE: "unavailable (pyserial missing)",
}

_DEFAULT_MAX_RANGE_MM = 4000.0

#: LiDAR-frame direction of the robot's front, **measured on this robot**:
#: a flat arena wall fitted as ``d = D/cos(theta - theta0)`` gave
#: ``theta0 = 1,0 deg`` with a 5 mm residual over 132 points, and the arc the
#: robot's own body blocks is centred on exactly 180,0 deg. Two independent
#: readings agreeing within a degree: the LiDAR's 0 deg is the front (the side
#: the arm is on). Do not treat this as a general truth -- it is this mount.
LIDAR_FRONT_OFFSET_DEG = 1.0

#: Returns closer than this are the robot's own body (measured at 20-30 mm),
#: not the room. Drawing them separately is the difference between "there is
#: something right in front of me" and "I am looking at my own chassis".
SELF_RETURN_MM = 60.0


def heading_dial_svg(
    heading_deg: float | None,
    *,
    size: int = 120,
    reference_label: str = "0 deg = arah saat LIVE dimulai",
) -> str:
    """A small dial showing the heading the IMU integrates, relative to the reset.

    Why a separate dial and not an arrow inside the scan plot: the scan plot is
    drawn in the **LiDAR's own frame**, which turns with the robot. The robot's
    front therefore sits at a *fixed* angle in that picture (it is drawn as a
    marker), and a heading arrow there would be constant and meaningless. The
    heading only means something against the room, so it gets its own dial with
    the facing at reset drawn as "up".

    ``heading_deg is None`` means no IMU data yet, and the dial says so instead
    of showing a zero that has not been measured.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    center = size / 2.0
    radius = center - 10.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">',
        f'<circle cx="{center}" cy="{center}" r="{radius}" fill="#0b1220" '
        f'stroke="#334155" stroke-width="1"/>',
    ]
    for fraction in (0.5, 1.0):
        parts.append(
            f'<circle cx="{center}" cy="{center}" r="{radius * fraction:.1f}" '
            f'fill="none" stroke="#1e293b" stroke-width="1"/>'
        )
    # Tick marks every 30 deg, with the reference direction ("up") emphasised.
    for step in range(0, 360, 30):
        rad = math.radians(90 - step)
        inner = radius - (6 if step == 0 else 3)
        parts.append(
            f'<line x1="{center + inner * math.cos(rad):.1f}" '
            f'y1="{center - inner * math.sin(rad):.1f}" '
            f'x2="{center + radius * math.cos(rad):.1f}" '
            f'y2="{center - radius * math.sin(rad):.1f}" '
            f'stroke="{"#94a3b8" if step == 0 else "#334155"}" stroke-width="1"/>'
        )

    if heading_deg is None:
        parts.append(
            f'<text x="{center}" y="{center - 4}" fill="#f97316" font-size="10" '
            f'text-anchor="middle">belum ada data IMU</text>'
        )
        parts.append(
            f'<text x="{center}" y="{center + 10}" fill="#64748b" font-size="9" '
            f'text-anchor="middle">butuh port chassis LIVE</text>'
        )
    else:
        # 0 deg points up; a left turn (+gz) rotates the needle counter-clockwise.
        rad = math.radians(90.0 + heading_deg)
        tip_x = center + (radius - 8) * math.cos(rad)
        tip_y = center - (radius - 8) * math.sin(rad)
        parts.append(
            f'<line x1="{center}" y1="{center}" x2="{tip_x:.1f}" y2="{tip_y:.1f}" '
            f'stroke="#f59e0b" stroke-width="3" stroke-linecap="round"/>'
        )
        parts.append(
            f'<circle cx="{center}" cy="{center}" r="3" fill="#f59e0b"/>'
        )
        parts.append(
            f'<text x="{center}" y="{size - 3}" fill="#e2e8f0" font-size="11" '
            f'text-anchor="middle">{heading_deg:+.1f} deg</text>'
        )
    parts.append(
        f'<text x="{center}" y="10" fill="#64748b" font-size="8" '
        f'text-anchor="middle">acuan</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_scan_svg(
    snapshot: ScanSnapshot,
    *,
    size: int = 300,
    max_range_mm: float = _DEFAULT_MAX_RANGE_MM,
    front_offset_deg: float | None = None,
) -> str:
    """Render a scan snapshot as an inline SVG polar plot.

    Angle 0 deg points right (+x) and increases counter-clockwise, matching the
    LiDAR's own convention. Valid points are coloured by distance (near = warm,
    far = cool). Invalid (zero-distance) points are not drawn; their count is
    reported in the panel text.

    Returns closer than ``SELF_RETURN_MM`` are drawn dark grey: on this robot
    they are the machine's own body (20-30 mm across a 150 deg arc), and calling
    them obstacles is how the operator ends up unable to tell what the plot is
    showing.

    ``front_offset_deg`` draws the robot at the centre with an arrow along the
    direction its front points, in the LiDAR's frame (see
    :data:`LIDAR_FRONT_OFFSET_DEG`). Without it the plot has no orientation
    reference at all.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if max_range_mm <= 0:
        raise ValueError("max_range_mm must be positive")

    center = size / 2.0
    radius = center - 8.0
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}">',
        f'<circle cx="{center}" cy="{center}" r="{radius}" '
        f'fill="#0b1220" stroke="#334155" stroke-width="1"/>',
    ]

    # Range rings at 25/50/75/100 % of the display range.
    for fraction in (0.25, 0.5, 0.75, 1.0):
        parts.append(
            f'<circle cx="{center}" cy="{center}" r="{radius * fraction:.1f}" '
            f'fill="none" stroke="#1e293b" stroke-width="1"/>'
        )
    # Crosshair.
    parts.append(
        f'<line x1="{center - radius:.1f}" y1="{center}" '
        f'x2="{center + radius:.1f}" y2="{center}" stroke="#1e293b" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{center}" y1="{center - radius:.1f}" '
        f'x2="{center}" y2="{center + radius:.1f}" stroke="#1e293b" stroke-width="1"/>'
    )

    for point in snapshot.points:
        if not point.valid:
            continue
        distance = min(point.distance_mm, max_range_mm)
        r = distance / max_range_mm * radius
        rad = math.radians(point.angle_deg)
        x = center + r * math.cos(rad)
        y = center - r * math.sin(rad)
        if point.distance_mm < SELF_RETURN_MM:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" fill="#64748b"/>')
            continue
        t = distance / max_range_mm
        color = f"rgb({int(239 * (1 - t) + 34 * t)},{int(68 * (1 - t) + 197 * t)},59)"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" fill="{color}"/>'
        )

    if front_offset_deg is not None:
        parts.extend(_robot_front_marker(center, front_offset_deg))

    # Range label.
    parts.append(
        f'<text x="6" y="{size - 6}" fill="#64748b" font-size="10">'
        f"0–{max_range_mm / 1000:.0f} m</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _robot_front_marker(center: float, front_offset_deg: float) -> list[str]:
    """The robot's hull plus a bold arrow for the direction its front points."""
    rad = math.radians(front_offset_deg)
    right = math.radians(front_offset_deg - 90.0)
    length = 34.0
    half_width = 9.0
    tip = (center + length * math.cos(rad), center - length * math.sin(rad))
    back = (center - 6 * math.cos(rad), center + 6 * math.sin(rad))
    left = (
        back[0] + half_width * math.cos(right),
        back[1] - half_width * math.sin(right),
    )
    other = (
        back[0] - half_width * math.cos(right),
        back[1] + half_width * math.sin(right),
    )
    parts = [
        f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} {left[0]:.1f},{left[1]:.1f} '
        f'{other[0]:.1f},{other[1]:.1f}" fill="#38bdf8" fill-opacity="0.85" '
        f'stroke="#0ea5e9" stroke-width="1"/>',
        f'<text x="{tip[0] + 4 * math.cos(rad):.1f}" '
        f'y="{tip[1] - 4 * math.sin(rad):.1f}" fill="#38bdf8" font-size="10">'
        f'DEPAN</text>',
    ]
    return parts


def lidar_panel(reader: LidarReader) -> None:
    """Render the live LiDAR card (status, counters and scan plot)."""
    stats = reader.stats()
    snapshot = reader.snapshot()

    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-3 w-full"):
            ui.icon("radar")
            ui.label("LiDAR (live hardware)").classes("text-sm text-gray-500 uppercase")
            ui.badge(_STATUS_LABEL[stats.status]).props(
                f"color={_STATUS_COLOR[stats.status]} text-color=white"
            )
            ui.label(f"{stats.port} @ {stats.baud} baud").classes(
                "text-xs text-gray-500 font-mono"
            )

        if stats.status is LidarStatus.UNAVAILABLE:
            ui.label(
                "pyserial is not installed in this environment. "
                "Install it (pip install pyserial) to read the physical LiDAR."
            ).classes("text-xs text-orange-700")
            return

        if stats.status is LidarStatus.ERROR and stats.last_error:
            ui.label(f"Last serial error: {stats.last_error}").classes(
                "text-xs text-red-700"
            )

        with ui.row().classes("w-full gap-4 items-start"):
            ui.html(
                render_scan_svg(snapshot, front_offset_deg=LIDAR_FRONT_OFFSET_DEG)
            ).classes("shrink-0")
            with ui.column().classes("gap-1 grow"):
                _metric_row("Packets OK", f"{stats.packets_ok}")
                _metric_row("Packets/s", f"{stats.packets_per_s:.0f}")
                _metric_row("CRC failures", f"{stats.crc_failures}")
                _metric_row("Sync failures", f"{stats.sync_failures}")
                _metric_row("Bytes read", f"{stats.bytes_read}")
                _metric_row("Reconnects", f"{stats.reconnects}")
                ui.separator()
                _metric_row("Scan points", f"{len(snapshot.points)} / {snapshot.buckets}")
                _metric_row("Coverage", f"{snapshot.coverage_fraction:.0%}")
                _metric_row("Revolutions", f"{snapshot.revolutions}")
                if snapshot.invalid_count:
                    ui.label(
                        f"{snapshot.invalid_count} point(s) with no valid return "
                        "(distance 0) — treated as invalid, not free space."
                    ).classes("text-xs text-amber-700")

        # --- orientation: what the plot is actually showing ------------------ #
        self_returns = sum(
            1 for point in snapshot.points if point.valid
            and point.distance_mm < SELF_RETURN_MM
        )
        with ui.row().classes("w-full gap-4 items-center"):
            _heading_source = robot_runtime.yaw_integrator()
            heading = _heading_source.heading_deg if _heading_source.available else None
            ui.html(heading_dial_svg(heading)).classes("shrink-0")
            with ui.column().classes("gap-0"):
                ui.label(
                    "Cincin tengah: panah biru = DEPAN robot, di sudut "
                    f"{LIDAR_FRONT_OFFSET_DEG:.1f} deg frame LiDAR (terukur dari "
                    "dinding arena datar, sisa 5 mm)."
                ).classes("text-xs text-gray-600")
                ui.label(
                    f"Titik abu-abu (jarak < {SELF_RETURN_MM:.0f} mm, "
                    f"{self_returns} titik sekarang) = badan robot sendiri, "
                    "bukan halangan."
                ).classes("text-xs text-gray-600")
                ui.label(
                    "Dial kiri = arah hadap dari IMU (`gz`, deg/s, kiri positif), "
                    "relatif terhadap saat LIVE dimulai. Nilai ini bisa melenceng "
                    "perlahan (integrasi gyro) — tombol RESET arah ada di panel "
                    "Remote chassis control di atas."
                ).classes("text-xs text-gray-600")

        if snapshot.points:
            ui.label(
                "Accumulated scan from multiple packets, arranged by angle. "
                "One packet is not a full revolution."
            ).classes("text-xs text-gray-500")
        else:
            ui.label("Waiting for valid scan data…").classes("text-xs text-gray-500")

        notes = reader.recent_notes()
        if notes:
            with ui.expansion("LiDAR reader log", icon="terminal").classes("w-full"):
                for note in notes[-12:]:
                    ui.label(note).classes("text-xs font-mono text-gray-600")


def _metric_row(caption: str, value: str) -> None:
    with ui.row().classes("items-center justify-between w-full"):
        ui.label(caption).classes("text-xs text-gray-500")
        ui.label(value).classes("text-sm font-mono")
