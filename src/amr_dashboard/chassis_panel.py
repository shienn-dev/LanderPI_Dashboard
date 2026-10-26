"""Interactive chassis control: hold a button, the robot moves.

This panel is rendered **once per page** and is never re-rendered by the
dashboard's refresh tick, because a button that is replaced while the pointer
is still down would lose the "release" event. The camera and odometry panels
stay in the refreshed region; this one does not. (The layout is rebuilt only
when ``app.layout_signature`` changes, and that signature includes whether the
chassis is live -- which is how the ONLINE button takes effect.)

How a hold works
----------------
``pointerdown`` on a direction button asks the
:class:`~amr_core.robot.motion_guard.MotionGuard` for permission to move. The
guard grants it only when the session holds the control lease, the software
E-stop is not latched, and the heartbeat is fresh. The command is then stored
in the guard, and the chassis adapter's stream thread sends it at 50 Hz until
the guard withdraws it.

Three things can withdraw it:

* the operator lets go (``pointerup`` / ``pointerleave``);
* the browser says "I am still in control" less often than every 300 ms
  (the heartbeat) -- this catches a lost release, a crashed tab, a dropped
  network or a sleeping laptop;
* the software E-stop is tripped, or another session takes the lease.

The heartbeat is a client-side timer that dispatches an event into the
server. If the page dies entirely, the heartbeat stops, the guard stops the
robot, and the board's own watchdog stops the motors if the frames stop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from nicegui import context, ui

from amr_core.robot.interfaces import ChassisCommand, ConnectionState
from amr_core.robot.kinematics import (
    MAX_FORWARD_RPS,
    STALL_THRESHOLD_RPS,
    command_for_speed,
    drive_command,
    is_above_stall_threshold,
    yaw_rate_for_wheel_rate,
)
from amr_dashboard import robot_runtime
from amr_dashboard.robot_runtime import RobotAdapters

#: Speed slider range, in m/s. The lower end is the stall threshold: below
#: ~0,3 rps the motors buzz without moving (sesi 2 §9.7), so offering less
#: would only confuse the operator.
MIN_SPEED_MPS = 0.06
MAX_SPEED_MPS = 0.19

#: Extra travel applied to the longitudinal axis only.
#:
#: Forward/backward was reported as too slow at full slider. It was not a bug:
#: at 1,0 rps the m/s mapping gives forward and strafe the same wheel rate, so
#: 0,19 m/s capped *every* axis. The lateral and yaw axes are right where the
#: operator wants them, so only the longitudinal one gets the extra: full
#: slider now asks for ``MAX_FORWARD_RPS``, which puts the previously measured
#: top speed at about 77 % of full travel.
LONGITUDINAL_GAIN = MAX_FORWARD_RPS / command_for_speed(MAX_SPEED_MPS)

#: A rate this far above the stall threshold has real torque margin. Below it
#: the robot may still crawl, or may just buzz on a tired battery -- the status
#: bar says which, because a silent no-motion is what made this look broken.
COMFORTABLE_RATE_RPS = 2.0 * STALL_THRESHOLD_RPS

#: How often the browser tells the server it is still in control.
HEARTBEAT_INTERVAL_MS = 100

#: How long ago a measured loop stall still explains a "heartbeat lost" stop.
#: Beyond this the panel stops blaming the server: a maximum from minutes ago
#: says nothing about why *this* hold died.
RECENT_STALL_S = 3.0

#: 3x3 direction pad. ``None`` is an empty cell (it keeps the grid's geometry
#: stable), ``"stop"`` is the STOP button. Keys match ``_DIRECTIONS``.
_PAD: tuple[str | None, ...] = (
    None, "forward", None,
    "left", "stop", "right",
    "yaw_ccw", "backward", "yaw_cw",
)

#: Every pad button has the same fixed size. This is load-bearing, not cosmetic:
#: a button that changes size or position while it is held fires
#: ``pointerleave``, and ``pointerleave`` stops the robot. Holding MAJU used to
#: stop itself because the status text below it grew the card every 250 ms.
_PAD_BUTTON_CLASSES = "w-28 h-11"

_DIRECTIONS: tuple[tuple[str, str, str, tuple[float, float, float]], ...] = (
    ("Maju", "arrow_upward", "forward", (1.0, 0.0, 0.0)),
    ("Mundur", "arrow_downward", "backward", (-1.0, 0.0, 0.0)),
    ("Kiri", "arrow_back", "left", (0.0, 1.0, 0.0)),
    ("Kanan", "arrow_forward", "right", (0.0, -1.0, 0.0)),
    ("Putar L", "rotate_left", "yaw_ccw", (0.0, 0.0, 1.0)),
    ("Putar R", "rotate_right", "yaw_cw", (0.0, 0.0, -1.0)),
)


@dataclass
class _Hold:
    """Server-side state of one page's hold controls."""

    session_id: str
    active: str | None = None
    started_at: float | None = None
    speed_mps: float = MIN_SPEED_MPS
    #: The command as it was actually built for the active button. Kept so the
    #: status bar reports what the wheels are told to do, not what was asked
    #: for before clamping.
    command: ChassisCommand | None = None


def chassis_control_panel(adapters: RobotAdapters) -> None:
    """Render the live chassis controls. Called once per page.

    Layout rules that exist because of a real bug: the card is ``w-full`` and
    the status line has a fixed height with ``overflow-hidden``. It used to be
    ``flex-1 min-w-[360px]`` with an unconstrained label, so every 250 ms tick
    made the label wider ("hold 0,5 s", stream counters), the card grew, the
    buttons slid sideways under the operator's finger, ``pointerleave`` fired
    and the robot stopped mid-hold. Nothing inside this card may resize as a
    function of its text.
    """
    chassis = adapters.chassis
    guard = adapters.guard
    live = adapters.live and guard is not None
    limits = chassis.limits
    session_id = context.client.id
    hold = _Hold(session_id=session_id)
    heading_label = None

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center gap-3 flex-nowrap"):
            ui.icon("sports_esports")
            ui.label("Remote chassis control").classes("text-sm text-gray-500 uppercase")
            _state_badge(chassis.state())
            if live:
                ui.badge("LIVE").props("color=red-7 text-color=white")
            ui.space()
            ui.label(
                f"batas: x {limits.max_linear_x:.2f} · y {limits.max_linear_y:.2f} m/s · "
                f"rot {limits.max_angular_z:.2f} rad/s"
            ).classes("text-xs text-gray-500")

        if live:
            ui.label(
                "LIVE: robot bergerak selama tombol ditahan. E-stop fisik tetap "
                "di tangan. Lepas tombol, koneksi putus, atau E-stop software "
                "akan menghentikannya."
            ).classes("text-xs text-red-700")
        else:
            ui.label(
                "OFFLINE: perintah divalidasi dan di-clamp, tapi TIDAK dikirim. "
                "Tombol di bawah membuka port chassis tanpa perlu restart server."
            ).classes("text-xs text-red-700")

        with ui.row().classes("w-full items-start gap-6 flex-nowrap"):
            # --- controls ---------------------------------------------------
            with ui.column().classes("grow min-w-0 gap-2"):
                ui.label(
                    f"Speed 0,{int(MIN_SPEED_MPS * 100):02d}-0,{int(MAX_SPEED_MPS * 100):02d}: "
                    f"maju/mundur sampai ~{MAX_SPEED_MPS * LONGITUDINAL_GAIN:.2f} m/s, "
                    f"samping & putar ~{MAX_SPEED_MPS:.2f} m/s"
                ).classes("text-xs text-gray-500 uppercase")
                speed = ui.slider(
                    min=MIN_SPEED_MPS,
                    max=MAX_SPEED_MPS,
                    step=0.01,
                    value=MIN_SPEED_MPS,
                ).classes("w-full")

                # Fixed height: the text may change every tick, the geometry
                # may not.
                status = ui.label("").classes(
                    "text-xs font-mono text-gray-600 w-full h-12 overflow-hidden "
                    "leading-tight"
                )

                if not live:
                    _online_controls(adapters)

                if live:
                    # Built here on purpose: this card is never refreshed, so a
                    # button in it can actually be clicked (a button inside the
                    # 1 Hz LiDAR region would be rebuilt under the pointer).
                    heading_label = _heading_row()

                _estop_controls(adapters, status if live else None)

            # --- direction pad ----------------------------------------------
            with ui.column().classes("shrink-0 gap-2"):
                ui.label("Arah").classes("text-xs text-gray-500 uppercase")
                if live:
                    _install_hold_buttons(adapters, hold, speed, status)
                else:
                    _offline_pad()

        if live:
            _install_heartbeat(adapters, session_id, status)
            # Refresh the hold timer while a button is held, so the operator can
            # read the exact hold time instead of trusting a stopwatch. The time
            # and the ruler distance together give the speed that was achieved.
            ui.timer(
                0.25,
                lambda: _refresh_status(
                    adapters,
                    hold,
                    status,
                    moving=hold.active is not None,
                    heading=heading_label,
                ),
            )


def _state_badge(state: ConnectionState) -> None:
    from amr_dashboard.robot_panel import _STATE_COLOR

    ui.badge(state.value).props(f"color={_STATE_COLOR[state]} text-color=white")


def _command_for(axis: tuple[float, float, float], speed: float) -> ChassisCommand:
    """Build the body command for one direction button.

    One slider feeds all six directions. For the translational axes its number
    is metres per second, which is what the operator reads. For the yaw axis
    that same number would be rad/s, and at the slider's own range it asks for
    roughly 0,05 rps -- seven times below the stall threshold, so turning could
    never move the robot. The yaw rate is therefore derived from the wheel rate
    the slider implies, so every button means the same thing: "drive the wheels
    this hard".

    The longitudinal axis gets an extra gain (``LONGITUDINAL_GAIN``) so that
    full slider reaches ``MAX_FORWARD_RPS``. Forward/back was the only axis the
    operator asked to speed up; lateral and yaw are left exactly as they were.
    """
    return ChassisCommand(
        linear_x=axis[0] * speed * LONGITUDINAL_GAIN,
        linear_y=axis[1] * speed,
        angular_z=axis[2] * yaw_rate_for_wheel_rate(command_for_speed(speed)),
    )


def _online_controls(adapters: RobotAdapters) -> None:
    """The OFFLINE branch's way back online: a button, not a server restart.

    Why this exists
    ---------------
    OFFLINE is a *launch* state, not a fault: without ``--chassis-live`` the pad
    is built disabled and nothing is transmitted. What the operator sees is a
    normal looking dashboard whose direction buttons ignore every press -- no
    error, no notification, no log line -- and the only way out used to be
    "stop the server and start it again with a flag". That is how a whole
    session was lost on 2026-10-22, and how it came back on 2026-10-26.

    So the state stays visible (red label, disabled pad) and this button is the
    way out of it: it opens the real chassis port from inside the running
    dashboard. Pressing it moves nothing -- it only opens the port and starts
    the idle stream -- and the pad only becomes live if the port really opened,
    because ``app.layout_signature`` includes the live/offline state and the
    tick rebuilds the panel from it.

    The confirmation checkbox is deliberate: opening the port is what makes this
    dashboard able to drive a real robot, so it is not something a stray click
    should be able to do.
    """
    ui.label(
        "Tombol arah DINONAKTIFKAN: mode OFFLINE tidak mengirim perintah."
    ).classes("text-sm font-bold text-red-700")

    safe = ui.checkbox(
        "Area robot aman dan E-stop fisik terjangkau (wajib untuk mengaktifkan LIVE)"
    )
    note = ui.label("").classes("text-xs font-mono text-gray-600 w-full")

    def _go_live() -> None:
        if not safe.value:
            ui.notify(
                'Centang dulu "Area robot aman ..." untuk mengaktifkan LIVE.',
                color="warning",
                position="top",
            )
            return
        result = robot_runtime.activate_live_chassis()
        note.set_text(result.message)
        ui.notify(
            result.message,
            color="positive" if result.ok else "negative",
            position="top",
        )

    ui.button(
        "AKTIFKAN LIVE (buka port chassis)",
        icon="power_settings_new",
        on_click=_go_live,
    ).props("color=primary")
    ui.label(
        f"Port yang dipakai: {robot_runtime.default_port()} — diubah dengan "
        "--chassis-port saat menjalankan server."
    ).classes("text-xs text-gray-500")


def _heading_text(integrator) -> str:
    """Heading readout; honest when there is no IMU data yet."""
    if not integrator.available:
        return "— belum ada data IMU (port chassis belum LIVE / belum ada frame)"
    return (
        f"{integrator.heading_deg:+.1f} deg   "
        f"({integrator.samples} sampel, drift ~0,3 deg/menit)"
    )


def _heading_row():
    """Heading from the IMU plus its reset, inside the card that is never refreshed.

    Why here and not next to the LiDAR plot: the plot lives in a region that the
    1 s tick rebuilds, and a button rebuilt under the operator's pointer is
    exactly the fault that made the direction pad stop mid-hold (sesi 5 §8).
    The readout is updated by the same 250 ms timer as the status line, so this
    row stays static and stays clickable.

    The heading is *relative* and a gyro always drifts, so it says both, and the
    reset is one click: whatever the robot faces then becomes 0 deg.
    """
    integrator = robot_runtime.yaw_integrator()
    with ui.row().classes("w-full items-center gap-3 flex-wrap"):
        ui.icon("explore")
        ui.label("Arah hadap (IMU)").classes("text-xs text-gray-500 uppercase")
        label = ui.label(_heading_text(integrator)).classes("text-sm font-mono")

        def _reset() -> None:
            robot_runtime.reset_heading()
            label.set_text(_heading_text(robot_runtime.yaw_integrator()))
            ui.notify(
                "Arah hadap di-reset: arah robot sekarang = 0 deg",
                color="primary",
                position="top",
            )

        ui.button("RESET arah", icon="explore", on_click=_reset).props("outline")
        ui.label(
            "relatif terhadap saat LIVE dimulai (IMU gz = deg/s, kiri positif)."
        ).classes("text-xs text-gray-500")
    return label


def _install_hold_buttons(
    adapters: RobotAdapters,
    hold: _Hold,
    speed,
    status,
) -> None:
    """Build the six hold-to-move buttons."""
    guard = adapters.guard
    chassis = adapters.chassis
    assert guard is not None

    def _start(axis: tuple[float, float, float], name: str) -> None:
        if not guard.arm(hold.session_id):
            ui.notify("Control is held by another session.", color="negative", position="top")
            return
        guard.heartbeat(hold.session_id)
        target_speed = float(speed.value or MIN_SPEED_MPS)
        command = _command_for(axis, target_speed)
        # The guard decides whether the robot may move; the adapter validates
        # and clamps what actually reaches the wire.
        if not guard.request_motion(hold.session_id, command):
            ui.notify(
                guard.stopped_reason or "motion refused",
                color="negative",
                position="top",
            )
            return
        outcome = chassis.submit(command)
        if not outcome.accepted:
            guard.release_motion(hold.session_id)
            ui.notify(outcome.reason, color="negative", position="top")
            return
        hold.active = name
        hold.speed_mps = target_speed
        hold.command = command
        hold.started_at = time.monotonic()
        _refresh_status(adapters, hold, status, moving=True)

    def _stop() -> None:
        hold.active = None
        hold.started_at = None
        hold.command = None
        guard.release_motion(hold.session_id)
        _refresh_status(adapters, hold, status, moving=False)

    def _stop_now() -> None:
        """The pad's STOP: release the lease and send an explicit stop frame."""
        hold.active = None
        hold.command = None
        hold.started_at = None
        guard.release_motion(hold.session_id)
        chassis.stop()
        _refresh_status(adapters, hold, status, moving=False)

    by_key = {key: (label, icon, axis) for label, icon, key, axis in _DIRECTIONS}

    with ui.grid(columns=3).classes("gap-2"):
        for slot in _PAD:
            if slot is None:
                # Empty cell keeps the pad's 3x3 geometry; without it the
                # buttons would reflow into different columns.
                ui.element("div").classes(_PAD_BUTTON_CLASSES)
                continue
            if slot == "stop":
                ui.button("STOP", icon="stop", on_click=_stop_now).props(
                    "color=orange text-color=white"
                ).classes(_PAD_BUTTON_CLASSES)
                continue
            label, icon, axis = by_key[slot]
            button = ui.button(label, icon=icon).classes(_PAD_BUTTON_CLASSES)
            button.on("pointerdown", lambda e, a=axis, k=slot: _start(a, k))
            button.on("pointerup", lambda e: _stop())
            button.on("pointerleave", lambda e: _stop())
            button.on("pointercancel", lambda e: _stop())


def _offline_pad() -> None:
    """The same pad, disabled, so the layout does not jump when mode changes."""
    by_key = {key: (label, icon) for label, icon, key, _axis in _DIRECTIONS}
    with ui.grid(columns=3).classes("gap-2"):
        for slot in _PAD:
            if slot is None:
                ui.element("div").classes(_PAD_BUTTON_CLASSES)
                continue
            if slot == "stop":
                ui.button("STOP", icon="stop").props("color=orange disable").classes(
                    _PAD_BUTTON_CLASSES
                )
                continue
            label, icon = by_key[slot]
            ui.button(label, icon=icon).props("outline disable").classes(
                _PAD_BUTTON_CLASSES
            )


def _install_heartbeat(adapters: RobotAdapters, session_id: str, status) -> None:
    """Wire the client heartbeat and the global release net.

    Two hidden elements carry the events: one is ticked every 100 ms by the
    browser to renew the lease, the other is fired by the browser whenever a
    pointer is released anywhere on the page, or the window loses focus, or the
    tab is hidden. Both use a plain ``change`` event so no custom-event
    support is needed.
    """
    guard = adapters.guard
    assert guard is not None

    beat = ui.element("input").props("type=hidden id=guard-heartbeat")
    beat.on("change", lambda e: guard.heartbeat(session_id))

    release = ui.element("input").props("type=hidden id=guard-release")
    release.on("change", lambda e: _release_all(adapters, session_id))

    ui.add_body_html(
        """
        <script>
        (function () {
          function fire(id) {
            const el = document.getElementById(id);
            if (el) { el.value = String(Date.now()); el.dispatchEvent(new Event('change')); }
          }
          setInterval(function () { fire('guard-heartbeat'); }, HEARTBEAT_MS);
          ['pointerup', 'pointercancel'].forEach(function (name) {
            window.addEventListener(name, function () { fire('guard-release'); }, true);
          });
          window.addEventListener('blur', function () { fire('guard-release'); });
          document.addEventListener('visibilitychange', function () {
            if (document.hidden) { fire('guard-release'); }
          });
        })();
        </script>
        """.replace("HEARTBEAT_MS", str(HEARTBEAT_INTERVAL_MS))
    )


def _release_all(adapters: RobotAdapters, session_id: str) -> None:
    guard = adapters.guard
    if guard is None:
        return
    guard.release_motion(session_id)


def _transmitted_rate(command: ChassisCommand | None) -> float:
    """Peak wheel rate (rps) that ``command`` actually puts on the wire.

    This runs the same kinematics the adapter uses, so it includes the safety
    clamp and the 1,0 rps cap. Reporting the *requested* rate instead is what
    hid the real fault: the panel said "MOVING, 0,33 rps, no warning" while the
    wheels were being told 0,27 rps and simply buzzed.
    """
    if command is None:
        return 0.0
    pairs = drive_command(
        command.linear_x, command.linear_y, command.angular_z
    )
    return max((abs(rate) for _motor_id, rate in pairs), default=0.0)


def _rate_note(rate_rps: float) -> str:
    """Say out loud when the commanded rate cannot turn the wheels."""
    if not is_above_stall_threshold(rate_rps):
        return "  <-- DI BAWAH AMBANG STALL: roda berdesis, robot TIDAK jalan"
    if not is_above_stall_threshold(rate_rps, threshold_rps=COMFORTABLE_RATE_RPS):
        return "  <-- dekat ambang stall: naikkan slider kalau robot tidak jalan"
    return ""


def _reason_note(reason: str, diag: robot_runtime.LoopDiagnostics, now: float) -> str:
    """Explain a stop reason, and separate our own slow loop from a dead browser.

    "heartbeat lost" (fault A4/F8) is not one fault: either the browser stopped
    reporting -- dropped Wi-Fi, sleeping laptop, throttled tab -- in which case
    stopping the robot is correct, or *this server* was too busy to process the
    heartbeats that did arrive, in which case the robot stopped for our fault.
    The top-level watchdog measures our own lateness, so the panel can say which
    one it was instead of leaving the operator to guess.

    The attribution uses *recency*: a late tick that just happened explains a
    stop that just happened. A stale maximum from minutes ago does not -- and
    blaming the server for a client that really went quiet would be worse than
    saying nothing.
    """
    if reason != "heartbeat lost":
        return ""
    recent = now - diag.max_delay_at_s
    if diag.max_delay_s >= robot_runtime.LOOP_DELAY_ALARM_S and recent < RECENT_STALL_S:
        return (
            f"  <-- HEARTBEAT HILANG, tapi loop server ini telat "
            f"{diag.max_delay_s * 1000:.0f} ms sekitar {recent:.1f} s lalu "
            f"({diag.late_ticks}x): penyebabnya sisi server, browser Anda masih "
            "hidup. Tekan tombolnya lagi."
        )
    return (
        "  <-- HEARTBEAT HILANG: loop server normal, jadi browser ini berhenti "
        "melapor. Periksa koneksi Wi-Fi/kabel atau tab yang tidak aktif, lalu "
        "tekan tombolnya lagi."
    )


def _refresh_status(
    adapters: RobotAdapters,
    hold: _Hold,
    status,
    *,
    moving: bool,
    heading=None,
) -> None:
    guard = adapters.guard
    if guard is None:
        return
    if heading is not None:
        heading.set_text(_heading_text(robot_runtime.yaw_integrator()))
    # "MOVING" must mean the wire is carrying a command: the guard may have
    # withdrawn it (heartbeat lost, e-stop) while the button is still held, and
    # saying MOVING then is the same class of lie that hid the clamp bug.
    moving = moving and guard.command() is not None
    age = guard.heartbeat_age()
    rate = _transmitted_rate(hold.command)
    stall_note = _rate_note(rate)
    elapsed = ""
    if moving and hold.started_at is not None:
        elapsed = f"  |  hold {time.monotonic() - hold.started_at:5.1f} s"
    stream = ""
    stats = getattr(adapters.chassis, "stats", None)
    if stats is not None:
        stream = (
            f"  |  stream {stats.measured_rate_hz:4.1f} Hz"
            f"  max gap {stats.max_gap_s * 1000:5.0f} ms"
            f"  frames {stats.frames_sent}"
        )
    diag = robot_runtime.loop_diagnostics()
    status.set_text(
        f"{'MOVING' if moving else 'idle'}{elapsed}  |  "
        f"slider {hold.speed_mps:.2f} -> roda {rate:.2f} rps{stall_note}  |  "
        f"hb {age:.2f} s  |  loop {diag.max_delay_s * 1000:.0f} ms{stream}  |  "
        f"{guard.stopped_reason}"
        f"{_reason_note(guard.stopped_reason, diag, time.monotonic())}"
    )


def _estop_controls(adapters: RobotAdapters, status=None) -> None:
    estop = adapters.estop
    guard = adapters.guard
    if estop.latched:
        ui.label(f"SOFTWARE E-STOP LATCHED ({estop.reason})").classes(
            "text-sm font-bold text-red-700"
        )
    else:
        ui.label("Software E-stop: not latched.").classes("text-xs text-gray-500")

    def _trip() -> None:
        estop.trip("operator (software)")
        if guard is not None:
            guard.trip("operator (software)")
        adapters.chassis.stop()
        ui.notify(
            "Software E-STOP latched. This is NOT the physical E-stop.",
            color="negative",
            position="top",
        )

    confirmed = ui.checkbox("I have verified the robot area is safe to clear the stop")

    def _clear() -> None:
        if guard is not None:
            guard.clear(confirmed_safe=bool(confirmed.value))
        if estop.clear(confirmed_safe=bool(confirmed.value)):
            ui.notify("Software E-STOP cleared.", color="positive")
        else:
            ui.notify("Not cleared: confirm the area is safe first.", color="warning")

    with ui.row().classes("gap-2"):
        ui.button("E-STOP (software)", icon="pan_tool", on_click=_trip).props("color=red")
        ui.button("Clear stop", icon="lock_open", on_click=_clear).props("outline")