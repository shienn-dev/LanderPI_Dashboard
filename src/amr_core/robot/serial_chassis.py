"""Serial chassis adapter: drives the STM32 board over ``/dev/ttyACM0``.

This is the transport that the dashboard has been missing. It replaces the
placeholder that refused to transmit. What it does, and why each part is
there:

* **It owns the port in a background thread.** Exactly one writer, so two
  commands can never interleave bytes on the wire.
* **It streams, it does not blip.** The board's firmware stops the motors when
  the command stream stops (verified on hardware, sesi 2 §9.3: one frame
  produced only a twitch). So the adapter keeps sending the current command at
  ``rate_hz`` (50 Hz, the rate that was measured to be smooth) and the
  :class:`~amr_core.robot.motion_guard.MotionGuard` decides *what* to send.
* **It always sends a stop frame.** On ``stop()``, on close and in a
  ``finally`` block, so the robot is never left with a live command.
* **It reads the board's own telemetry on the same handle.** The board streams
  IMU frames (func 7) continuously; a second handle on the same device would
  stall it for another 2,36 s and split the stream between two readers, so the
  one handle is drained in the stream thread and the decoded readings are handed
  to an optional ``imu_listener``. Without a listener the read path stays off and
  the timing of the motor stream is exactly what it was.
* **It reports its state honestly.** ``CONNECTED`` only while the port is
  really open and the stream thread is alive.
* **It never exceeds the tested envelope.** The body command is clamped by
  :mod:`amr_core.robot.safety` and then converted to wheel rates by
  :mod:`amr_core.robot.kinematics`, which caps the rate at the highest value
  ever measured on this robot.

Safety
------
The adapter is only useful with a human next to the robot. The physical
E-stop remains the primary stop; the software guard only decides what the
stream contains.

No device imports
------------------
This module does not import pyserial, and it is not allowed to: the
``amr_core.robot`` package stays free of device code (there is a guard test
for it). The port is opened by whoever constructs the adapter, through the
``port_factory`` argument -- the dashboard passes
:func:`amr_dashboard.chassis_transport.open_serial_port`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from amr_core.robot.interfaces import ChassisCommand, CommandOutcome, ConnectionState
from amr_core.robot.kinematics import (
    DEFAULT_MODEL,
    MecanumModel,
    drive_command,
)
from amr_core.robot.motion_guard import MotionGuard
from amr_core.robot.safety import SpeedLimits, validate_chassis_command
from amr_core.robot.stm32_protocol import (
    FrameDecoder,
    ImuReading,
    Stm32Function,
    build_motor_frame,
    decode_imu,
)

DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_BAUD = 1_000_000
DEFAULT_RATE_HZ = 50.0
#: Seconds to wait after opening the port before the first frame. The board
#: needs a moment after a USB CDC open.
DEFAULT_SETTLE_S = 0.3

#: How many stop frames are sent when a command ends, before the stream goes
#: quiet. A burst makes the stop explicit; after that the board's watchdog
#: holds the motors off, so the robot does not hum while idle.
STOP_FRAME_BURST = 3


class SerialPort(Protocol):
    """The small part of ``serial.Serial`` this adapter needs."""

    def write(self, data: bytes, /) -> int | None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


@dataclass
class SerialChassisStats:
    """Counters for the dashboard's state panel."""

    frames_sent: int = 0
    frames_failed: int = 0
    last_error: str = ""
    last_frame_at: float = 0.0
    port_opened_at: float = 0.0
    #: Measured frame rate over the last second. The board's watchdog stops the
    #: motors when the frames stop arriving, so a rate below the target is a
    #: direct suspect for the stuttering.
    measured_rate_hz: float = 0.0
    #: Largest gap between two frames since the port was opened, in seconds.
    #: This is the number that matters for the board's watchdog.
    max_gap_s: float = 0.0


class SerialChassisAdapter:
    """Drives the chassis over a serial port. One writer, one stream."""

    name = "serial"

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        limits: SpeedLimits | None = None,
        *,
        baud: int = DEFAULT_BAUD,
        rate_hz: float = DEFAULT_RATE_HZ,
        settle_s: float = DEFAULT_SETTLE_S,
        guard: MotionGuard | None = None,
        model: MecanumModel = DEFAULT_MODEL,
        port_factory: Callable[[str, int], SerialPort] | None = None,
        imu_listener: Callable[[ImuReading], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.port = port
        self.baud = baud
        self.rate_hz = rate_hz
        self.settle_s = settle_s
        self.limits = limits if limits is not None else SpeedLimits()
        self.guard = guard if guard is not None else MotionGuard()
        self.model = model
        self._port_factory = port_factory
        self._imu_listener = imu_listener
        self._imu_decoder = FrameDecoder()
        self._imu_frames = 0
        self._clock = clock
        self._port: SerialPort | None = None
        self._thread: threading.Thread | None = None
        self._closing = threading.Event()
        self._lock = threading.Lock()
        self._state = ConnectionState.DISABLED
        self._last: ChassisCommand | None = None
        self.stats = SerialChassisStats()
        self._frames_in_sample = 0
        self._sample_started_at = self._clock()

    # --- lifecycle --------------------------------------------------------- #

    def open(self) -> ConnectionState:
        """Open the port and start the streaming thread."""
        with self._lock:
            if self._state == ConnectionState.CONNECTED:
                return self._state
            if self._port_factory is None:
                self._state = ConnectionState.UNAVAILABLE
                self.stats.last_error = "no port factory was given"
                return self._state
            try:
                self._port = self._port_factory(self.port, self.baud)
            except Exception as exc:  # noqa: BLE001 - report the real cause
                self._state = ConnectionState.UNAVAILABLE
                self.stats.last_error = f"{type(exc).__name__}: {exc}"
                return self._state
            self.stats.port_opened_at = self._clock()
            self._state = ConnectionState.CONNECTED
            # A command left over from a previous session must never start the
            # robot moving by itself.
            self.guard.reset_motion()
            self._closing.clear()
            self._thread = threading.Thread(
                target=self._stream_loop, name="chassis-stream", daemon=True
            )
            self._thread.start()
        return self._state

    def close(self) -> None:
        """Stop the stream, send a final stop frame and close the port."""
        self._closing.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._thread = None
            port = self._port
            self._port = None
            self._state = ConnectionState.DISABLED
        if port is not None:
            try:
                port.write(self._stop_frame())
                port.flush()
            except Exception as exc:  # noqa: BLE001
                self.stats.last_error = f"stop frame failed: {exc}"
            finally:
                try:
                    port.close()
                except Exception as exc:  # noqa: BLE001
                    self.stats.last_error = f"close failed: {exc}"

    # --- adapter interface -------------------------------------------------- #

    def state(self) -> ConnectionState:
        return self._state

    def last_command(self) -> ChassisCommand | None:
        return self._last

    def submit(self, command: ChassisCommand, *, session_id: str | None = None) -> CommandOutcome:
        """Validate, clamp and start streaming ``command``.

        When ``session_id`` is given, the motion guard has to agree first: the
        guard owns the lease, the heartbeat and the software E-stop, so it is
        the only thing allowed to decide that the robot may move.
        """
        clamped, reason = validate_chassis_command(command, self.limits)
        if clamped is None:
            return CommandOutcome(accepted=False, transmitted=False, reason=reason)
        self._last = clamped
        if session_id is not None:
            if not self.guard.request_motion(session_id, clamped):
                return CommandOutcome(
                    accepted=False,
                    transmitted=False,
                    reason=self.guard.stopped_reason or "motion refused by the guard",
                )
        if self._state != ConnectionState.CONNECTED:
            return CommandOutcome(
                accepted=True,
                transmitted=False,
                reason="validated; the chassis port is not connected",
            )
        return CommandOutcome(
            accepted=True,
            transmitted=True,
            reason=f"streaming {self._describe(clamped)}",
        )

    def stop(self) -> CommandOutcome:
        """Stop the robot now."""
        self._last = ChassisCommand()
        self.guard.release_motion(self.guard.lease_owner or "")
        if self._state != ConnectionState.CONNECTED:
            return CommandOutcome(
                accepted=True,
                transmitted=False,
                reason="stop requested; the chassis port is not connected",
            )
        self._write(self._stop_frame())
        return CommandOutcome(accepted=True, transmitted=True, reason="stop frame sent")

    # --- internals ---------------------------------------------------------- #

    def _describe(self, command: ChassisCommand) -> str:
        return (
            f"vx={command.linear_x:.3f} m/s, vy={command.linear_y:.3f} m/s, "
            f"wz={command.angular_z:.3f} rad/s"
        )

    def _stop_frame(self) -> bytes:
        return build_motor_frame([(motor_id, 0.0) for motor_id in (1, 2, 3, 4)])

    def _frame_for(self, command: ChassisCommand) -> bytes:
        # Clamp again on the way to the wire: the guard may hold a command the
        # safety limits would refuse, and the limits are the last word.
        clamped, _ = validate_chassis_command(command, self.limits)
        effective = clamped if clamped is not None else ChassisCommand()
        pairs = drive_command(
            effective.linear_x,
            effective.linear_y,
            effective.angular_z,
            model=self.model,
        )
        return build_motor_frame(pairs)

    @property
    def imu_frames(self) -> int:
        """How many IMU frames have been decoded on this port."""
        return self._imu_frames

    def _drain_input(self) -> None:
        """Forward the board's own telemetry (IMU frames) to the listener.

        Non-blocking by construction: only bytes that are *already* waiting are
        read, so this can never delay a motor frame. With no listener attached
        the port is never read at all, which keeps the motor timing exactly what
        it was before this existed.

        A second handle on the same device is not an option: opening it stalls
        the board for another 2,36 s and splits the stream between two readers,
        so the board's telemetry has to be read on the handle that already owns
        the port -- this one, in the stream thread.
        """
        listener = self._imu_listener
        port = self._port
        if listener is None or port is None:
            return
        waiting = getattr(port, "in_waiting", 0) or 0
        if waiting <= 0:
            return
        reader = getattr(port, "read", None)
        if reader is None:
            # A port that cannot be read (some test fakes) simply has no
            # telemetry; motor streaming must not care.
            return
        try:
            data = reader(waiting)
        except Exception as exc:  # noqa: BLE001 - report the real cause
            self.stats.last_error = f"imu read failed: {type(exc).__name__}: {exc}"
            return
        if not data:
            return
        for frame in self._imu_decoder.feed(data):
            if frame.function != Stm32Function.IMU:
                continue
            reading = decode_imu(frame.payload)
            if reading is None:
                continue
            self._imu_frames += 1
            listener(reading)

    def _write(self, frame: bytes) -> bool:
        port = self._port
        if port is None:
            return False
        try:
            port.write(frame)
        except Exception as exc:  # noqa: BLE001 - the port died, say so
            self.stats.frames_failed += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"
            self._state = ConnectionState.DISCONNECTED
            return False
        now = self._clock()
        if self.stats.last_frame_at:
            gap = now - self.stats.last_frame_at
            if gap > self.stats.max_gap_s:
                self.stats.max_gap_s = gap
        self.stats.frames_sent += 1
        self.stats.last_frame_at = now
        self._frames_in_sample += 1
        if now - self._sample_started_at >= 1.0:
            span = now - self._sample_started_at
            self.stats.measured_rate_hz = self._frames_in_sample / span
            self._frames_in_sample = 0
            self._sample_started_at = now
        return True

    def _stream_loop(self) -> None:
        """Send the current command at the frame rate; go quiet when idle.

        While a command is active the frames are streamed continuously, because
        the board's firmware stops the motors when the command stream stops
        (verified on hardware, sesi 2 §9.3).

        When the command ends, a short burst of stop frames is sent and then the
        stream **stops**. The board's watchdog then holds the motors off. This
        matters: continuously streaming zero-speed frames keeps the motor
        driver energised, so the robot hums after every stop -- it was observed
        on the floor, and it is also the behaviour that makes the robot hard to
        push around while the dashboard is open.
        """
        period = 1.0 / self.rate_hz
        next_send = self._clock() + self.settle_s
        stop_frames_left = 0
        while not self._closing.is_set():
            # Drain the board's own telemetry first: it costs nothing when no
            # listener is attached, and it must never delay a motor frame, so it
            # only ever reads bytes that are already waiting.
            self._drain_input()
            now = self._clock()
            if now < next_send:
                time.sleep(min(next_send - now, period))
                continue
            next_send += period
            command = self.guard.poll()
            if command is None:
                if stop_frames_left > 0:
                    if not self._write(self._stop_frame()):
                        break
                    stop_frames_left -= 1
                else:
                    # Idle: send nothing and let the board's watchdog hold the
                    # motors off.
                    time.sleep(period)
                continue
            stop_frames_left = STOP_FRAME_BURST
            if not self._write(self._frame_for(command)):
                break
        # The stream ended: make sure the board is not left with a live command.
        self._write(self._stop_frame())
