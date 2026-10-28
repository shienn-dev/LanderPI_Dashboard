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

#: The LiDAR's angle grows **clockwise seen from above** in this mount, the
#: opposite of the usual counter-clockwise assumption. Measured 2026-10-28 with
#: the same bottle placed twice and a 10 s scan each time: on the robot's
#: front-left (~1,17 m) it landed in 315-330 deg, on the front-right (~1,07 m)
#: it landed in 30-60 deg, and every other sector stayed put within 13 mm.
#: Since 0 deg is the front, raw angles drawn straight to SVG (``y = center -
#: r*sin``) mirror the whole picture -- exactly the "mirror tapi aneh" the
#: operator reported. So the plot converts the angle (see
#: :func:`_screen_angle_deg`): a true top-down view, drawn with the front at the
#: top because that is the orientation the operator reads the plot in.
LIDAR_ANGLE_CLOCKWISE = True


def _screen_angle_deg(angle_deg: float) -> float:
    """LiDAR-frame angle -> SVG screen angle: a top-down view, front upwards.

    ``90 - angle`` for a clockwise frame: the front (0 deg) is drawn at the top,
    the robot's own left (315-330 deg, measured) on the left of the plot and its
    right (30-60 deg) on the right. The scan stays in the LiDAR's own frame
    everywhere else -- reader, probe tools and this module's constants -- so
    only the drawing carries the conversion and no probe has to be re-derived
    when the view changes.
    """
    return 90.0 - angle_deg if LIDAR_ANGLE_CLOCKWISE else 90.0 + angle_deg

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

    The picture is a **top-down view, not mirrored, drawn with the front at the
    top**: the LiDAR's own (clockwise) frame is converted before drawing, see
    :data:`LIDAR_ANGLE_CLOCKWISE` and :func:`_screen_angle_deg`. So the top of
    the plot is where the robot looks, its own left is on the left and its right
    is on the right -- with the front arrow at 90 deg instead of 0 deg. Drawing
    the raw frame directly is what made the plot mirror the room. Valid points
    are coloured by distance (near = warm, far = cool). Invalid (zero-distance)
    points are not drawn; their count is reported in the panel text.

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
        rad = math.radians(_screen_angle_deg(point.angle_deg))
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
    """A small top-down robot at the centre, its nose along the front.

    A rounded chassis with a chevron nose and the word DEPAN, instead of the
    filled triangle it used to be: the operator's words were "arah hadap robot
    jangan segitiga gitu, jelek", and a triangle between the scan dots also
    reads like an obstacle. Drawn as a symbol, not to scale -- at 4 m of display
    range a true-to-size 30 cm chassis would be an 11 px smudge.

    Converted with :func:`_screen_angle_deg` exactly like the scan points, so
    the nose and the dots can never end up in two different frames. The
    chassis is built pointing up and then rotated, because SVG rotates
    clockwise on screen: a nose-up rectangle needs ``90 - screen_angle``, which
    for a front offset of 1 deg comes out as a 1 deg tilt -- the measured
    mounting offset, visible as a tilt rather than hidden as a constant.
    """
    screen = _screen_angle_deg(front_offset_deg)
    rad = math.radians(screen)
    rotate = 90.0 - screen
    half_width = 12.0
    length = 30.0
    chevron = 9.0
    label_gap = length / 2 + chevron + 12.0
    top = center - length / 2
    label_x = center + label_gap * math.cos(rad)
    label_y = center - label_gap * math.sin(rad)
    turn = f'rotate({rotate:.1f} {center:.1f} {center:.1f})'
    parts = [
        f'<rect x="{center - half_width:.1f}" y="{top:.1f}" '
        f'width="{2 * half_width:.1f}" height="{length:.1f}" rx="5" '
        f'fill="#0ea5e9" fill-opacity="0.18" stroke="#38bdf8" '
        f'stroke-width="1.4" transform="{turn}"/>',
        f'<polyline points="{center - half_width * 0.7:.1f},{top:.1f} '
        f'{center:.1f},{top - chevron:.1f} '
        f'{center + half_width * 0.7:.1f},{top:.1f}" fill="none" '
        f'stroke="#38bdf8" stroke-width="2.4" stroke-linecap="round" '
        f'stroke-linejoin="round" transform="{turn}"/>',
        f'<text x="{label_x:.1f}" y="{label_y + 3.5:.1f}" fill="#38bdf8" '
        f'font-size="10" text-anchor="middle">DEPAN</text>',
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
                    "Bidang biru di tengah = robot (simbol, bukan skala); "
                    "hidungnya = DEPAN, di sudut "
                    f"{LIDAR_FRONT_OFFSET_DEG:.1f} deg frame LiDAR (terukur dari "
                    "dinding arena datar, sisa 5 mm), jadi ia miring 1 deg dari "
                    "atas."
                ).classes("text-xs text-gray-600")
                ui.label(
                    "Plot = tampak atas, DEPAN selalu di ATAS, dan tidak "
                    "ter-mirror: frame LiDAR di robot ini berputar searah jarum "
                    "jam (terukur 28 Okt: botol di kiri-depan mendarat di "
                    "315-330 deg), jadi gambarnya dibalik dulu. Sisi KIRI robot "
                    "tampil di kiri plot, sisi KANAN di kanan."
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
