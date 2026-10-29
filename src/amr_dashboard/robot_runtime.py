"""Process-wide robot adapters for the dashboard.

Builds the adapter set once per process. Nothing here opens a device unless
the operator explicitly asked for a **live** chassis: the default is the
offline adapter set, which validates and records commands but transmits
nothing.

The live chassis is opt-in through ``--chassis-live`` on the command line.
That flag is the only thing that can turn a real robot into a moving robot, so
it is deliberately not implied by anything else -- not by the port name, not by
an environment variable, not by the presence of the device.

Design note: the dashboard UI depends only on the adapter *interfaces*
(``amr_core.robot.interfaces``), never on a concrete transport.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from amr_core.robot.arm import OfflineArmAdapter
from amr_core.robot.arm_bus import BusServoArmAdapter
from amr_core.robot.camera import DEFAULT_FEED_PATH as DEFAULT_CAMERA_FEED
from amr_core.robot.camera import probe_camera
from amr_core.robot.chassis import OfflineChassisAdapter
from amr_core.robot.imu import YawIntegrator
from amr_core.robot.interfaces import CameraStatus, ChassisAdapter, ConnectionState
from amr_core.robot.motion_guard import MotionGuard
from amr_core.robot.odometry import NoOdometrySource
from amr_core.robot.safety import EStopLatch, SpeedLimits
from amr_core.robot.serial_chassis import DEFAULT_PORT, SerialChassisAdapter, SerialPort
from amr_dashboard.arm_transport import open_arm_port
from amr_dashboard.chassis_transport import open_serial_port

_ODOMETRY_DETAIL = (
    "No odometry source active: no ROS 2 /odom node is running, and the STM32 "
    "encoder/IMU path on /dev/ttyACM0 is unverified. See docs/robot_integration.md."
)

#: Speed limits used by the live chassis. ``max_linear_x`` must stay at or above
#: ``kinematics.speed_for_rate(kinematics.MAX_FORWARD_RPS)`` (1,80 rps = 0,330
#: m/s) or the clamp here trims the longitudinal gain in ``chassis_panel`` and
#: silently undoes the speed-up -- which is exactly the class of bug that made
#: the buttons feel dead. The gain is what bounds forward speed; this number only
#: stops the clamp from interfering with it.
#:
#: ``max_linear_y`` and ``max_angular_z`` are deliberately **not** tightened
#: below the slider's own range. They were once set to 0,05 and 0,20, which
#: looked conservative but silently broke two axes: the slider bottoms out at
#: 0,06 m/s, so every strafe command was clamped to 0,05 and reached the wheels
#: as 0,273 rps -- below the 0,3 rps stall threshold, i.e. the robot buzzed and
#: never moved sideways no matter where the slider was. Turning was worse still.
#: A safety limit that quietly turns a motion into a no-motion is not a safety
#: limit, it is a bug with a good reputation.
#:
#: The real envelope is enforced downstream: ``kinematics`` caps the lateral and
#: yaw axes at the measured ``MAX_TESTED_RPS`` (1,0 rps) and scales the whole
#: command so no wheel exceeds the cap that applies to it.
LIVE_LIMITS = SpeedLimits(
    max_linear_x=0.34,
    max_linear_y=0.19,
    max_angular_z=1.20,
)

#: Seconds the STM32 board stays deaf after its port is opened. Measured four
#: times on this robot, identical every time: 2.360 / 2.359 / 2.359 / 2.359 s
#: (sesi 5 §3). Frames written inside that window are simply dropped -- the
#: board is not listening yet.
#:
#: This is what the adapter's ``settle_s`` has to cover, because that is the
#: wait before the stream thread's *first* frame. The adapter's own default is
#: 0,3 s, which is fine for a port opened at server start-up (the operator
#: reaches the buttons minutes later) but is 8x too short for a port opened
#: from the UI: the first ~2,4 s of the first hold would be dropped, and a
#: dropped hold is indistinguishable from a dead button. That is exactly the
#: fault this dashboard keeps being accused of, so the live adapter is built
#: with the measured window instead of the default.
BOOT_WINDOW_S = 2.5

#: How the live adapter opens the port: ``(port, baud) -> handle``. Injected so
#: the tests can drive the whole online path without a serial device.
PortFactory = Callable[[str, int], SerialPort]

#: Port the ONLINE button opens when the server was not told otherwise
#: (``--chassis-port`` sets it through :func:`set_default_port`).
_default_port = DEFAULT_PORT

#: Process-wide yaw integrator, fed by the live chassis adapter's read path.
#: The heading it produces is relative (degrees turned since the last reset),
#: because a gyro has no absolute reference -- the panel and the log must say so.
_yaw = YawIntegrator()


def yaw_integrator() -> YawIntegrator:
    """The heading source shown next to the LiDAR plot."""
    return _yaw


def reset_heading() -> None:
    """Make the robot's current facing the new 0 deg reference."""
    _yaw.reset()


def _feed_heading(reading) -> None:
    """Adapter read-path hook: fold one IMU sample into the heading."""
    _yaw.update(reading)

#: How often the app's watchdog ticks, and how late a tick must be before it
#: counts as "this process could not run its event loop for that long".
LOOP_WATCH_INTERVAL_S = 0.05
LOOP_DELAY_ALARM_S = 0.2


@dataclass
class LoopDiagnostics:
    """How late this process' own event loop has been, measured at the top level.

    This is the number behind fault A4/F8 ("heartbeat kadang hilang"): the guard
    cannot tell "the browser went quiet" from "our loop could not process the
    browser's heartbeat". Recording it turns that argument into a measurement,
    and the panel shows it so the operator can see which of the two happened.
    """

    ticks: int = 0
    max_delay_s: float = 0.0
    last_delay_s: float = 0.0
    late_ticks: int = 0
    max_delay_at_s: float = 0.0

    def record(self, delay_s: float, *, now: float | None = None) -> None:
        self.ticks += 1
        self.last_delay_s = delay_s
        if delay_s > self.max_delay_s:
            self.max_delay_s = delay_s
            self.max_delay_at_s = time.monotonic() if now is None else now
        if delay_s >= LOOP_DELAY_ALARM_S:
            self.late_ticks += 1


_loop_diagnostics = LoopDiagnostics()


def loop_diagnostics() -> LoopDiagnostics:
    """Process-wide event-loop lateness counters (read by the chassis panel)."""
    return _loop_diagnostics


def reset_loop_diagnostics() -> LoopDiagnostics:
    global _loop_diagnostics
    _loop_diagnostics = LoopDiagnostics()
    return _loop_diagnostics


def record_loop_delay(delay_s: float) -> None:
    """Report how late the event loop was; forgive it in the motion guard.

    Called by the dashboard's watchdog. A late tick of our own is exactly the
    case where a heartbeat could not be *processed* though it was *sent*, so it
    must not be charged to the operator as a lost client.
    """
    _loop_diagnostics.record(delay_s)
    adapters = _adapters
    if adapters is None or adapters.guard is None:
        return
    if delay_s >= LOOP_DELAY_ALARM_S:
        adapters.guard.note_busy(delay_s)


def note_loop_tick() -> None:
    """Tell the guard that this process' event loop is alive right now.

    Called on every watchdog tick (50 Hz, one timer for the whole process). It
    is the signal that lets the guard tell "the browser went quiet" apart from
    "we were the ones who could not run".
    """
    adapters = _adapters
    if adapters is None or adapters.guard is None:
        return
    adapters.guard.note_loop_tick()


@dataclass
class RobotAdapters:
    """The process-wide set of robot adapters (offline / safe)."""

    chassis: ChassisAdapter
    arm: OfflineArmAdapter | BusServoArmAdapter
    odometry: NoOdometrySource
    camera: CameraStatus
    estop: EStopLatch
    guard: MotionGuard | None = None
    live: bool = False
    #: Whether the arm has a real transport. Separate from ``live`` (chassis):
    #: the wheels can stay offline while the arm is live, and the other way round.
    arm_live: bool = False


def build_adapters(
    *,
    live: bool = False,
    port: str = DEFAULT_PORT,
    port_factory: PortFactory = open_serial_port,
    settle_s: float = BOOT_WINDOW_S,
    arm_live: bool = False,
    camera_feed: str | Path | None = None,
) -> RobotAdapters:
    """Create a fresh adapter set.

    ``live=False`` (the default) never touches a device. ``live=True`` builds
    the serial adapter -- still without opening anything: ``open()`` is the
    caller's job -- and installs the motion guard; the caller is responsible
    for closing it again (the dashboard does that on shutdown).

    ``settle_s`` is the wait before the stream's first frame. It defaults to
    ``BOOT_WINDOW_S``, the measured time the board is deaf after ``open()``
    (see the constant), not to the adapter's shorter default.
    """
    if live:
        # A fresh live set starts a fresh heading reference: whatever direction
        # the robot faces when the port opens is 0 deg. The integrator only ever
        # reports degrees *turned*, never a compass bearing.
        _yaw.reset()
        guard = MotionGuard()
        chassis: ChassisAdapter = SerialChassisAdapter(
            port=port,
            limits=LIVE_LIMITS,
            guard=guard,
            settle_s=settle_s,
            port_factory=port_factory,
            imu_listener=_feed_heading,
        )
    else:
        guard = None
        chassis = OfflineChassisAdapter(limits=SpeedLimits())
    # The arm is a separate switch from the chassis: `--arm-live` gives the arm
    # a real transport while the wheels stay offline (and the other way round).
    # Built, never opened -- open() is the caller's job.
    arm: OfflineArmAdapter | BusServoArmAdapter = (
        BusServoArmAdapter(port=port, settle_s=settle_s) if arm_live else OfflineArmAdapter()
    )
    return RobotAdapters(
        chassis=chassis,
        arm=arm,
        arm_live=arm_live,
        odometry=NoOdometrySource(_ODOMETRY_DETAIL),
        camera=probe_camera(feed_path=camera_feed or DEFAULT_CAMERA_FEED),
        estop=EStopLatch(),
        guard=guard,
        live=live,
    )


_adapters: RobotAdapters | None = None


def get_adapters() -> RobotAdapters:
    """Return the process-wide adapter set, creating it on first use."""
    global _adapters
    if _adapters is None:
        _adapters = build_adapters()
    return _adapters


def configure(
    *, live: bool = False, port: str = DEFAULT_PORT, arm_live: bool = False
) -> RobotAdapters:
    """Install the adapter set the operator asked for (replaces any earlier one)."""
    global _adapters
    close_adapters()
    _adapters = build_adapters(live=live, port=port, arm_live=arm_live)
    return _adapters


def activate_live_arm(
    port: str | None = None,
    *,
    port_factory=open_arm_port,
) -> LiveActivation:
    """Give the arm a real transport, on request, without restarting the server.

    The arm hangs on the same board as the chassis but is a separate switch: the
    wheels can stay offline while the arm is live. Opening the port moves
    nothing -- the arm only moves when a step is submitted -- and a failure
    keeps the offline adapter installed with the real reason attached.

    Idempotent, like the chassis path.
    """
    target = port or default_port()
    adapters = get_adapters()
    if adapters.arm_live and adapters.arm.state() is ConnectionState.CONNECTED:
        return LiveActivation(
            ok=True,
            state=ConnectionState.CONNECTED,
            message=f"arm sudah LIVE di {target}; tidak ada port kedua yang dibuka.",
        )

    candidate = BusServoArmAdapter(port=target, settle_s=BOOT_WINDOW_S)
    try:
        handle = port_factory(target)
    except Exception as exc:  # noqa: BLE001 - the reason is the report
        return LiveActivation(
            ok=False,
            state=ConnectionState.DISCONNECTED,
            message=f"{type(exc).__name__}: {exc}",
        )
    ok, reason = candidate.open(handle)
    if not ok:
        candidate.close()
        return LiveActivation(ok=False, state=candidate.state(), message=reason)

    adapters.arm = candidate
    adapters.arm_live = True
    return LiveActivation(ok=True, state=ConnectionState.CONNECTED, message=reason)


def default_port() -> str:
    """Port the live chassis opens (``--chassis-port``, else ``/dev/ttyACM0``)."""
    return _default_port


def set_default_port(port: str) -> None:
    """Remember the chassis port even when the server starts offline.

    The ONLINE button in the panel has no command line of its own; without this
    it would always open ``/dev/ttyACM0`` and silently ignore
    ``--chassis-port``.
    """
    global _default_port
    _default_port = port or DEFAULT_PORT


@dataclass(frozen=True)
class LiveActivation:
    """Result of bringing the chassis online from inside a running dashboard."""

    ok: bool
    state: ConnectionState
    message: str


def activate_live_chassis(
    port: str | None = None,
    *,
    port_factory: PortFactory = open_serial_port,
    settle_s: float = BOOT_WINDOW_S,
) -> LiveActivation:
    """Open the real chassis port on request, without restarting the server.

    This is what the panel's ONLINE button calls. It exists because "offline"
    is a *launch* state, not a fault: a dashboard started without
    ``--chassis-live`` shows a disabled direction pad that ignores every press,
    with no error at all, and the operator's only way out used to be to stop the
    server and start it again with the right flag.

    Opening the port moves nothing: the adapter's stream is idle until the guard
    holds a command, and the guard only gets one when a direction button is
    held. What it does do is make this dashboard capable of driving a real
    robot, so the caller is expected to have asked the operator first.

    Failure is never silent: the port that is already open elsewhere, a missing
    device or an unreadable port all come back as ``ok=False`` with the reason,
    the previous (offline) adapter set stays installed, and the dashboard keeps
    reporting OFFLINE -- which is the honest state.

    Idempotent: once the chassis is live, a second call is a no-op rather than a
    second stream on the same port.
    """
    global _adapters
    target = port or default_port()

    current = get_adapters()
    if current.live and current.chassis.state() is ConnectionState.CONNECTED:
        return LiveActivation(
            ok=True,
            state=ConnectionState.CONNECTED,
            message=f"chassis sudah LIVE di {target}; tidak ada port kedua yang dibuka.",
        )

    candidate = build_adapters(
        live=True, port=target, port_factory=port_factory, settle_s=settle_s
    )
    opener = getattr(candidate.chassis, "open", None)
    state = opener() if opener is not None else ConnectionState.UNAVAILABLE
    if state is not ConnectionState.CONNECTED:
        stats = getattr(candidate.chassis, "stats", None)
        reason = getattr(stats, "last_error", "") or "penyebab tidak dilaporkan"
        _close_chassis(candidate)
        return LiveActivation(
            ok=False,
            state=state,
            message=(
                f"GAGAL LIVE: {target} -> {state.value} ({reason}). "
                "Dashboard tetap OFFLINE: tombol arah masih tidak mengirim perintah."
            ),
        )

    _adapters = candidate
    _close_chassis(current)
    return LiveActivation(
        ok=True,
        state=state,
        message=(
            f"LIVE: {target} terbuka ({state.value}). Board menerima perintah "
            f"~{settle_s:.1f} s setelah port dibuka -- tahan tombol agak lama pada "
            "hold pertama."
        ),
    )


def _close_chassis(adapters: RobotAdapters) -> None:
    """Close one adapter set's chassis port, if it owns one."""
    chassis = adapters.chassis
    if hasattr(chassis, "close"):
        chassis.close()  # type: ignore[attr-defined]


def close_adapters() -> None:
    """Close the live chassis and arm ports, if there are any."""
    if _adapters is None:
        return
    _close_chassis(_adapters)
    arm = _adapters.arm
    if hasattr(arm, "close"):
        arm.close()  # type: ignore[attr-defined]


def open_live_chassis() -> ConnectionState:
    """Open the live chassis port, if the live adapter is installed.

    Returns the resulting connection state; the offline adapter reports
    ``DISABLED`` and nothing is opened.
    """
    adapters = get_adapters()
    opener = getattr(adapters.chassis, "open", None)
    if opener is None:
        return ConnectionState.DISABLED
    return opener()


def reset_adapters() -> None:
    """Drop the process-wide adapter set (test helper)."""
    global _adapters
    close_adapters()
    _adapters = None
