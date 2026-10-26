"""Yaw integration for the board's IMU (func 7) -- measured on this robot.

Everything in here is a *measured* fact about the school board, not a guess from
documentation (the SDK documents no IMU units at all):

* **`gz` is the yaw axis.** A hand rotation of the chassis moves `gz` and
  nothing else; `gx`/`gy` only react when the robot is tipped.
* **The gyro unit is degrees per second.** A hand rotation of +-90 deg
  integrated to |integral of gz| = 96,8 deg*s -- a ratio of 1,075 to the 90 deg
  that was asked for, which is what hand rotation and a 0,5 s sampling grid
  explain. In rad/s the integral would have been 1,5708 (60x smaller); in raw
  LSB the ratio would be arbitrary.
* **`+gz` = turning left** (counter-clockwise seen from above), confirmed by the
  operator during that same measurement.
* At rest `gz` sits at 0,00 +- 0,03 deg/s, so a deadband of
  ``DEFAULT_DEADBAND_DPS`` costs nothing and removes most of the leftover drift.
* The accel axis is in **g** (`az` about 1,024 at rest), and the first frames
  after the port opens carry a startup transient on `gx` (up to ~5), which is
  why integration ignores an implausible first step.

The heading produced here is therefore **relative**: it counts degrees turned
since :meth:`YawIntegrator.reset`. It drifts (a gyro always does), so the UI must
say so and offer a reset, and nobody may present it as a compass.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from amr_core.robot.stm32_protocol import ImuReading

#: Gyro rates below this count as noise, not rotation. Measured at-rest spread on
#: ``gz`` is +-0,03 deg/s, so this is a safety factor of ~1,7 without being so
#: large that a slow deliberate turn is ignored (the slowest turn a hand can make
#: is well above 1 deg/s).
DEFAULT_DEADBAND_DPS = 0.05

#: A gap larger than this between two IMU samples is not integrated: the board
#: was silent (it stays deaf for ~2,3 s after the port opens, and the stream can
#: stop), and integrating across a hole would invent an angle.
MAX_STEP_S = 0.5


class YawIntegrator:
    """Accumulates ``gz`` into a relative heading, in degrees, turning left positive."""

    def __init__(
        self,
        *,
        deadband_dps: float = DEFAULT_DEADBAND_DPS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._deadband_dps = deadband_dps
        self._clock = clock
        self.reset()

    # --- state -------------------------------------------------------------- #

    def reset(self) -> None:
        """Forget the accumulated angle: the current facing becomes 0 deg."""
        self._heading_deg = 0.0
        self._last_stamp: float | None = None
        self._samples = 0
        self._skipped_steps = 0
        self._seconds_integrated = 0.0

    @property
    def heading_deg(self) -> float:
        """Degrees turned since :meth:`reset`; left (CCW) is positive."""
        return self._heading_deg

    @property
    def samples(self) -> int:
        return self._samples

    @property
    def seconds_integrated(self) -> float:
        return self._seconds_integrated

    @property
    def skipped_steps(self) -> int:
        """Steps dropped because the board had been silent for too long."""
        return self._skipped_steps

    @property
    def available(self) -> bool:
        """True once at least one IMU sample has been integrated."""
        return self._samples > 0

    # --- integration -------------------------------------------------------- #

    def update(self, reading: ImuReading, *, now: float | None = None) -> float:
        """Fold one IMU sample in and return the new heading in degrees."""
        stamp = self._clock() if now is None else now
        rate = reading.gz
        if abs(rate) < self._deadband_dps:
            rate = 0.0

        if self._last_stamp is not None:
            step = stamp - self._last_stamp
            if 0.0 < step <= MAX_STEP_S:
                self._heading_deg += rate * step
                self._seconds_integrated += step
            elif step > MAX_STEP_S:
                # The board went quiet; that gap is not a rotation.
                self._skipped_steps += 1

        self._last_stamp = stamp
        self._samples += 1
        return self._heading_deg