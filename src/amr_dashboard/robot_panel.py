"""Robot panels: camera status, odometry status, remote chassis + arm control.

Every panel is honest about availability. A missing link is shown as
NOT CONNECTED / UNAVAILABLE, never as a live feed or a fabricated pose. The
arm control submits to an *offline* adapter that validates but never
transmits, and the panel says so on every action. The live chassis control
lives in :mod:`amr_dashboard.chassis_panel`.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from amr_core.robot.camera import probe_camera
from amr_core.robot.interfaces import ArmCommand, CommandOutcome, ConnectionState
from amr_dashboard import arm_jog, camera_feed, camera_stream, robot_runtime
from amr_dashboard.robot_runtime import RobotAdapters

#: The camera panel is re-rendered once per second, so it needs the previous
#: (seq, monotonic_ms) to compute a frame rate. One process, one camera: a single
#: module-level slot is enough, and it keeps the panel a plain function.
_CAMERA_VIEW: dict[str, Any] = {"previous": None}

_STATE_COLOR: dict[ConnectionState, str] = {
    ConnectionState.CONNECTED: "green-7",
    ConnectionState.DISCONNECTED: "amber-7",
    ConnectionState.UNAVAILABLE: "orange-8",
    ConnectionState.DISABLED: "grey-7",
}


def robot_panels(adapters: RobotAdapters) -> None:
    """Render the read-only robot panel that is safe to rebuild (odometry).

    Everything that must not be rebuilt lives outside this region: the
    interactive panels (chassis, arm) lose whatever the operator is doing, and
    the camera preview owns a live HTTP response that a rebuild would restart
    once per tick -- which is exactly what made a 15 fps camera look like a
    slide show. ``camera_live_panel`` is built once with the other live panels.
    """
    odometry_panel(adapters)


def _state_badge(state: ConnectionState) -> None:
    ui.badge(state.value).props(f"color={_STATE_COLOR[state]} text-color=white")


def _report(outcome: CommandOutcome) -> None:
    color = "positive" if outcome.accepted else "negative"
    prefix = "VALIDATED (not transmitted)" if outcome.accepted else "REJECTED"
    ui.notify(f"{prefix}: {outcome.reason}", color=color, position="top")


def _metric(caption: str, value: str) -> None:
    with ui.column().classes("gap-0"):
        ui.label(caption).classes("text-xs text-gray-500 uppercase")
        ui.label(value).classes("text-base font-mono")


#: Pratinjau yang bisa dipilih -> (query string, keterangan). ``rgb`` adalah
#: gambar kamera biasa (sensor RGB-nya ada dan mengalir sebagai NV12); dua yang
#: lain adalah peta jarak (depth) dengan skala *palsu*, bukan foto berwarna.
CAMERA_VIEWS = {
    "rgb": ("source=rgb", "kamera biasa: warna asli dari sensor RGB (NV12)"),
    "turbo": (
        "source=depth&palette=turbo",
        "peta jarak: dekat = merah/kuning, jauh = biru-ungu, tanpa data = hitam",
    ),
    "grey": (
        "source=depth&palette=grey",
        "peta jarak: dekat = terang, jauh = gelap, tanpa data = hitam",
    ),
}
CAMERA_PREVIEW_PATH = "/camera/live.mjpg"


def _camera_preview_html(view: str) -> str:
    """The ``<img>`` that carries the stream; its ``src`` switches feed/scale."""
    query, _note = CAMERA_VIEWS.get(view, CAMERA_VIEWS["rgb"])
    return (
        f'<img src="{CAMERA_PREVIEW_PATH}?{query}" alt="kamera"'
        ' style="width:100%;max-width:520px;border:1px solid #cbd5e1">'
    )


def _metric_labels(captions: tuple[str, ...]) -> tuple[ui.element, dict[str, ui.label]]:
    """One row of metric cells: (container, value labels).

    The labels are handed back so a timer can set their text without rebuilding
    the card, and the container so a whole row can be hidden when it does not
    apply (depth percentiles mean nothing for a colour picture).
    """
    handles: dict[str, ui.label] = {}
    with ui.grid(columns=len(captions)).classes("w-full gap-2") as row:
        for caption in captions:
            with ui.column().classes("gap-0"):
                ui.label(caption).classes("text-xs text-gray-500 uppercase")
                handles[caption] = ui.label("-").classes("text-base font-mono")
    return row, handles


def camera_live_panel(adapters: RobotAdapters) -> None:
    """Kamera (robot): pratinjau yang benar-benar mengalir, warna atau depth.

    Dibangun **sekali**, di luar wilayah yang di-render ulang oleh tick dashboard
    -- alasan yang sama dengan panel arm. Kalau kartunya dibangun ulang tiap tick,
    setiap tick juga me-restart respons HTTP pratinjau, dan kamera 15 fps tampil
    seperti slideshow. Angka-angkanya menimpa teks pada label yang sudah ada.

    Dua sumber, dua kebenaran yang terpisah: ``rgb`` (sensor warna, NV12) dan
    ``depth`` (peta jarak uint16 mm). Keduanya dibaca dari berkas seqlock yang
    ditulis satu proses pembaca; panel memeriksa kesegaran tiap detik, jadi
    pembaca yang mati tidak pernah tampil sebagai "hidup".
    """
    status = adapters.camera  # potret saat server start; hanya untuk catatan
    view = {"value": "rgb"}

    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-3"):
            icon = ui.icon("videocam_off")
            ui.label("Camera (robot)").classes("text-sm text-gray-500 uppercase")
            badge = ui.badge(status.state.value).props(
                f"color={_STATE_COLOR[status.state]} text-color=white"
            )
            kind = ui.badge(f"kind: {status.kind}").props("color=blue-grey-7 text-color=white")
            toggle = ui.toggle(
                {"rgb": "kamera (warna)", "turbo": "depth (warna)", "grey": "depth (abu-abu)"},
                value="rgb",
            ).props("dense")
            toggle.on_value_change(
                lambda event: _set_camera_view(event.value, view, preview, scale)
            )

        preview = ui.html(_camera_preview_html(view["value"])).classes("w-full")
        scale = ui.label(CAMERA_VIEWS[view["value"]][1]).classes("text-xs text-gray-500")
        silent = ui.label("").classes("text-sm font-medium text-red-700")

        metrics = _metric_labels(("resolusi", "umur frame", "laju", "frame total"))[1]
        depth_row, depth = _metric_labels(("median", "p10", "p90", "tanpa data"))
        detail = ui.label("").classes("text-xs text-gray-500 font-mono")

    def update() -> None:
        chosen = view["value"]
        source = "rgb" if chosen == "rgb" else "depth"
        depth_status = probe_camera()
        rgb_frame = camera_feed.live_rgb_frame()
        depth_frame = camera_feed.live_frame() if depth_status.frames_available else None
        frame = rgb_frame if source == "rgb" else depth_frame

        available = frame is not None
        drawable = available and camera_stream.pillow_available()
        icon.name = "videocam" if available else "videocam_off"
        badge.text = (
            ConnectionState.CONNECTED.value if available else ConnectionState.UNAVAILABLE.value
        )
        state_now = ConnectionState.CONNECTED if available else ConnectionState.UNAVAILABLE
        badge.props(f"color={_STATE_COLOR[state_now]} text-color=white")
        kind.text = f"kind: {source}"
        preview.set_visibility(drawable)
        scale.set_visibility(drawable)
        silent.set_visibility(not drawable)
        depth_row.set_visibility(source == "depth" and drawable)

        if not drawable:
            for handle in (*metrics.values(), *depth.values()):
                handle.text = "-"
            if available and not camera_stream.pillow_available():
                reason = "Pillow tidak terpasang — pratinjau tidak bisa digambar."
            elif source == "rgb":
                reason = (
                    "feed warna belum ada — jalankan ~/camera_depth_live.sh "
                    "(satu proses mengalirkan warna + depth)"
                )
            else:
                reason = depth_status.detail
            silent.text = f"NO LIVE FEED — {reason}"
            detail.text = f"status saat server start: {status.state.value} ({status.detail})"
            return

        if source == "rgb":
            assert rgb_frame is not None
            rate = camera_feed.rate_from_counters(
                _CAMERA_VIEW.get("rgb"), rgb_frame.frames_total, rgb_frame.host_ms
            )
            _CAMERA_VIEW["rgb"] = (rgb_frame.frames_total, rgb_frame.host_ms)
            metrics["resolusi"].text = f"{rgb_frame.width}x{rgb_frame.height}"
            metrics["umur frame"].text = f"{rgb_frame.age_ms} ms"
            metrics["laju"].text = "mengukur..." if rate is None else f"{rate:.1f} fps"
            metrics["frame total"].text = str(rgb_frame.frames_total)
            detail.text = (
                f"warna NV12 {rgb_frame.width}x{rgb_frame.height}, frame "
                f"{rgb_frame.age_ms} ms lalu ({camera_feed.DEFAULT_RGB_PATH})"
            )
            return

        assert depth_frame is not None
        stats = camera_feed.depth_stats(depth_frame)
        rate = camera_feed.frame_rate(_CAMERA_VIEW.get("depth"), depth_frame.header)
        _CAMERA_VIEW["depth"] = (depth_frame.header.frames_total, depth_frame.header.host_ms)
        metrics["resolusi"].text = f"{depth_frame.width}x{depth_frame.height}"
        metrics["umur frame"].text = f"{depth_frame.header.age_ms} ms"
        metrics["laju"].text = "mengukur..." if rate is None else f"{rate:.1f} fps"
        metrics["frame total"].text = str(depth_frame.header.frames_total)
        depth["median"].text = f"{stats.median} mm"
        depth["p10"].text = f"{stats.p10} mm"
        depth["p90"].text = f"{stats.p90} mm"
        depth["tanpa data"].text = f"{stats.invalid_pct:.1f} %"
        detail.text = depth_status.detail

    update()
    ui.timer(1.0, update)


def _set_camera_view(value: str, view: dict[str, str], preview, scale) -> None:
    """Ganti sumber/skala pratinjau. ``src`` baru = stream baru; sekali per klik."""
    if value not in CAMERA_VIEWS:
        return
    view["value"] = value
    scale.text = CAMERA_VIEWS[value][1]
    preview.content = _camera_preview_html(value)


def odometry_panel(adapters: RobotAdapters) -> None:
    source = adapters.odometry
    sample = source.sample()
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("explore")
            ui.label("Odometry (robot)").classes("text-sm text-gray-500 uppercase")
            _state_badge(source.state())
            ui.label(f"source: {source.name}").classes("text-xs text-gray-500 font-mono")
        ui.label(source.detail()).classes("text-xs text-gray-600")
        if sample is None:
            ui.label("No odometry data available.").classes("text-sm text-amber-800")
        else:
            with ui.grid(columns=3).classes("w-full gap-2"):
                _metric("x", f"{sample.x:.2f} m")
                _metric("y", f"{sample.y:.2f} m")
                _metric("yaw", f"{sample.yaw:.1f} deg")
                _metric("v", f"{sample.linear_x:.2f} m/s")
                _metric("omega", f"{sample.angular_z:.2f} rad/s")
                _metric("stamp", f"{sample.stamp_s:.2f} s")


def arm_control_panel(adapters: RobotAdapters) -> None:
    arm = adapters.arm
    if getattr(adapters, "arm_live", False):
        if arm.state() is ConnectionState.CONNECTED:
            _live_arm_panel(arm)
        else:
            _unconnected_arm_panel(arm)
        return
    with ui.card().classes("flex-1 min-w-[320px]"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("precision_manufacturing")
            ui.label("Arm control").classes("text-sm text-gray-500 uppercase")
            _state_badge(arm.state())
        ui.label(
            "NOT CONNECTED — the arm command interface is unverified on this board, so "
            "no arm command is sent. The controls below only validate input."
        ).classes("text-xs text-red-700")
        ui.label(
            "Upstream uses 5 joints + gripper as bus-servo pulse widths (0..1000). "
            "Joint count, safe ranges and limits are NOT yet verified here."
        ).classes("text-xs text-gray-600")

        joints = ui.input("Joints (comma-separated pulse widths)", value="500,500,500,500,500")
        duration = ui.number("Duration (s)", value=1.0, min=0.02, max=30.0)

        def _submit() -> None:
            raw = str(joints.value or "")
            try:
                positions = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
            except ValueError:
                ui.notify("Invalid joint list: use comma-separated integers.", color="negative")
                return
            command = ArmCommand(positions=positions, duration_s=float(duration.value or 1.0))
            _report(arm.submit(command))

        ui.button("Validate arm command", icon="rule", on_click=_submit).props("outline")
        last = arm.last_command()
        if last is not None:
            ui.label(
                f"Last validated: {last.positions} @ {last.duration_s:.2f}s (NOT transmitted)"
            ).classes("text-xs text-gray-500 font-mono")


def _live_arm_panel(arm) -> None:
    """The arm with a real transport behind it: drag a slider, one move.

    Rewritten 2026-10-29 after the operator's complaint that the first version
    was too slow to use: 10 pulses per click, 0,8 s each, so a 200-pulse
    reposition was twenty clicks and twenty seconds. Now each joint has a
    slider across its own *measured* limit, and one drag becomes one
    ``set position`` frame whose duration is the distance divided by a speed
    taken from the vendor's own action groups (see
    :mod:`amr_dashboard.arm_jog`).

    Three fences kept from the button version:

    - every target is clamped to that servo's measured limit;
    - a servo that does not answer is never moved by a guess -- the joint is
      reported as silent and no frame is sent for it;
    - the gripper (servo 10) is absent, and ``move_joints`` refuses it anyway.

    STOP wins: it drops every pending target before the stop frame, so a drag
    that was in flight cannot re-issue itself afterwards.

    The board is told once per settled drag, never once per drag event (round 2,
    2026-10-29): re-targeting a bus servo several times a second restarts its
    motion profile every time, which is what "nyendet-nyendet" was.
    """
    controller = arm_jog.ArmJogController(arm)

    with ui.card().classes("flex-1 min-w-[340px]"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("precision_manufacturing")
            ui.label("Arm control (LIVE)").classes("text-sm text-gray-500 uppercase")
            _state_badge(arm.state())
        ui.label(
            "Geser slider sendi = satu perintah gerak; durasi dihitung dari jarak "
            "dan kecepatan. Perintah baru dikirim setelah slider berhenti "
            "(0,35 s) — saat digeser tidak ada perintah yang dikirim, supaya "
            "gerakannya tidak tersendat."
        ).classes("text-xs text-gray-600")
        ui.label(
            "Gripper (servo 10) tidak ada di panel ini: aturan operator - jangan "
            "disentuh, jangan diperintahkan."
        ).classes("text-xs text-amber-700")

        speed_label = ui.label("").classes("text-xs text-gray-600 font-mono")

        def speed_text() -> str:
            return (
                f"kecepatan: {controller.speed_pps:.0f} pulse/s"
                f"  (200 pulse = {200 / controller.speed_pps:.1f} s)"
            )

        def on_speed(event) -> None:
            controller.set_speed(event.value if event.value is not None else 0)
            speed_label.set_text(speed_text())

        with ui.row().classes("items-center gap-3 w-full"):
            ui.slider(
                min=arm_jog.MIN_SPEED_PPS,
                max=arm_jog.MAX_SPEED_PPS,
                step=10.0,
                value=arm_jog.DEFAULT_SPEED_PPS,
                on_change=on_speed,
            ).props("dense").classes("w-56")
            speed_label.set_text(speed_text())

        positions = ui.label("posisi  (belum dibaca)").classes(
            "text-xs text-gray-500 font-mono"
        )
        status = ui.label("").classes("text-xs text-gray-700 font-mono")

        sliders: dict[int, Any] = {}
        value_labels: dict[int, Any] = {}

        def sync_sliders(values: dict[int, int | None]) -> None:
            """Move the handles to the real positions without commanding them."""
            controller.syncing = True
            try:
                for servo_id, pulse in values.items():
                    slider = sliders.get(servo_id)
                    if slider is not None and pulse is not None:
                        slider.set_value(pulse)
                    label = value_labels.get(servo_id)
                    if label is not None:
                        label.set_text("-" if pulse is None else str(pulse))
            finally:
                controller.syncing = False

        def refresh() -> None:
            values = controller.refresh()
            parts = [f"{sid}:{'-' if pulse is None else pulse}" for sid, pulse in values.items()]
            positions.set_text("posisi  " + "  ".join(parts))
            sync_sliders(values)

        def show_plan(servo_id: int) -> None:
            label = value_labels.get(servo_id)
            if label is None:
                return
            plan = controller.preview(servo_id)
            if plan is None:
                return
            label.set_text(f"{plan.target} (~{plan.duration_s:.1f} s)")

        def on_slide(servo_id: int, value) -> None:
            """A drag: only ever *records* the target, and only sends once still.

            Sending a frame per drag event re-targets the servo several times a
            second, and every frame carries its own move time -- the joint then
            visibly hesitates (the operator's "nyendet-nyendet"). So the drag
            updates a pending value (free), and :mod:`amr_dashboard.arm_jog`
            releases it to the board only after the handle has settled.
            """
            if controller.syncing or value is None:
                return
            if int(value) == controller.measured.get(servo_id):
                return
            try:
                plan = controller.set_target(servo_id, value)
            except (ValueError, RuntimeError) as exc:
                status.set_text(f"ditolak: {exc}")
                return
            label = value_labels.get(servo_id)
            if label is not None:
                label.set_text(f"{plan.target} (~{plan.duration_s:.1f} s)")

        def nudge(servo_id: int, delta: int) -> None:
            base = controller.start_for(servo_id)
            if base is None:
                ui.notify(
                    f"servo {servo_id} tidak menjawab - tidak ada perintah yang dikirim",
                    color="negative",
                )
                return
            try:
                plan = controller.set_target(servo_id, base + delta, immediate=True)
            except (ValueError, RuntimeError) as exc:
                status.set_text(f"ditolak: {exc}")
                return
            slider = sliders.get(servo_id)
            if slider is not None:
                controller.syncing = True
                try:
                    slider.set_value(plan.target)
                finally:
                    controller.syncing = False
            show_plan(servo_id)

        def tick() -> None:
            """Pace the writes: whatever the drag emitted, one frame per joint."""
            results = controller.flush()
            if not results:
                return
            for result in results:
                if result.plan is not None:
                    label = value_labels.get(result.plan.servo_id)
                    if label is not None:
                        label.set_text(str(result.plan.target))
            status.set_text(results[-1].reason)

        def stop() -> None:
            result = controller.stop()
            status.set_text(result.reason)
            ui.notify(result.reason, color="warning", position="top")
            refresh()

        with ui.column().classes("gap-2 w-full"):
            for servo_id in sorted(arm.limits):
                low, high = arm.limits[servo_id]
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.label(f"sendi {servo_id}").classes("text-xs w-14")
                    ui.label(f"{low}-{high}").classes("text-xs text-gray-500 w-20 font-mono")
                    sliders[servo_id] = ui.slider(
                        min=float(low),
                        max=float(high),
                        step=5.0,
                        value=None,
                        on_change=lambda event, sid=servo_id: on_slide(sid, event.value),
                    ).props("dense label").classes("flex-1")
                    value_labels[servo_id] = ui.label("-").classes(
                        "text-xs font-mono w-20 text-right"
                    )
                    ui.button("-10", on_click=lambda sid=servo_id: nudge(sid, -10)).props(
                        "outline dense"
                    )
                    ui.button("+10", on_click=lambda sid=servo_id: nudge(sid, +10)).props(
                        "outline dense"
                    )

        with ui.row().classes("items-center gap-3"):
            ui.button("Baca posisi", icon="refresh", on_click=refresh).props("outline dense")
            ui.button("STOP", icon="stop", on_click=stop).props("color=negative dense")

        ui.timer(arm_jog.FLUSH_INTERVAL_S, tick)
        refresh()


def _unconnected_arm_panel(arm) -> None:
    """The arm was asked for but the port is not open: say why, offer a retry.

    This is the state a second dashboard lands in when the first one already
    holds the board's port -- the two are the *same* port on the same STM32, so
    only one handle can exist. Same for a chassis that went ONLINE first.
    """
    with ui.card().classes("flex-1 min-w-[320px]"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("precision_manufacturing")
            ui.label("Arm control").classes("text-sm text-gray-500 uppercase")
            _state_badge(arm.state())
        stats = getattr(arm, "stats", None)
        reason = getattr(stats, "last_reason", "") or "penyebab tidak dilaporkan"
        ui.label(f"Arm belum tersambung: {reason}").classes("text-xs text-red-700")
        ui.label(
            "Board, chassis dan arm memakai PORT YANG SAMA, jadi hanya satu proses "
            "yang boleh memegangnya. Kalau dashboard lain (atau panel chassis yang "
            "sudah ONLINE) memegang /dev/ttyACM0, arm tidak bisa membuka sendiri."
        ).classes("text-xs text-gray-600")

        def retry() -> None:
            activation = robot_runtime.activate_live_arm()
            ui.notify(activation.message, color="positive" if activation.ok else "negative")

        ui.button("Coba sambungkan", icon="cable", on_click=retry).props("outline")
        ui.label(
            "Gripper (servo 10) tetap tidak akan muncul di panel ini: aturan operator."
        ).classes("text-xs text-amber-700")
