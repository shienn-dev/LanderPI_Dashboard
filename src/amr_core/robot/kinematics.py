"""Mecanum inverse kinematics: body-frame velocity -> per-wheel motor commands.

Pure computation. This module never opens a port, never writes a byte and never
commands the robot: it turns a desired body velocity into the four motor
commands the STM32 expects.

Why this module is careful about signs
--------------------------------------
The sign convention on this robot has already been wrong once. Commit
``f8de64e`` corrected it: the earlier mapping (forward = ``1:+,2:+,3:-,4:-``)
was derived by watching the wheels spin **with the robot lifted**, where only
rotation is visible and chassis translation is not. The robot actually drove
backwards. The corrected, verified convention is:

======================  ==========================================
Motor id                Wheel (verified on hardware, sesi 2 §9.5)
======================  ==========================================
1                       front left
2                       rear left
3                       front right
4                       rear right
======================  ==========================================

======================  ==========================================
Motion                   Motor commands (verified)
======================  ==========================================
forward                  ``1:-  2:-  3:+  4:+``
======================  ==========================================

The *lateral* and *yaw* patterns are **not** verified on the floor. They are
derived here from the roller arrangement, so they carry the same kind of risk
the old forward convention carried. :func:`direction_report` prints every
direction in the exact motor-command form so the result can be compared with
what the robot actually does, and the signs are isolated in
:class:`MecanumModel` so a wrong guess is a one-line data change, not a code
change.

Geometry
--------
``L`` (track width, centre to centre) and ``H`` (wheelbase, centre to centre)
are measured on this robot: 145 mm and 135 mm (sesi 3 §10). ``C_eff`` (distance
travelled per wheel revolution) is 20,72 +/- 1,84 cm (sesi 3 §6).

The model
---------
For a mecanum wheel whose rollers sit at 45 deg, the wheel can only roll along
its roller direction, so the wheel's own rolling speed is the projection of the
chassis velocity onto that direction:

.. code-block:: text

    rolling_i = v_x*cos(t_i) + v_y*sin(t_i) - w_z*(x_i*sin(t_i) + y_i*cos(t_i))

The projection factor ``cos(45 deg)`` is then divided out, because the
measured ``C_eff`` is a *forward* distance per revolution: with the projection
kept in, a forward command would come out 1/sqrt(2) = 0,71 times too slow and
would contradict the measured anchor below. The result is the usual mecanum
matrix in the (forward, left, counter-clockwise) frame:

.. code-block:: text

    speed_FL = v_x + v_y - w_z*(a + b)
    speed_RL = -v_x + v_y + w_z*(a + b)
    speed_FR = -v_x + v_y - w_z*(a + b)
    speed_RR = v_x + v_y + w_z*(a + b)

    a = L/2 (half track width)      b = H/2 (half wheelbase)

and the motor command is that speed times the wheel's command sign, divided by
``C_eff``.

Two independent hardware facts come out of this and both are already known:

* **forward** gives ``1:- 2:- 3:+ 4:+`` -- the pattern verified on the floor.
* **turning in place** gives the *same* sign on all four motors -- exactly what
  was observed when a uniform ``+0.3`` to all four was run (sesi 2 §9.5,
  "left forward, right backward", i.e. a spin rather than a drive).

The **lateral** pattern is derived, not measured, and is the one to confirm at
the hardware gate.

Scale
-----
The board takes **rps** (revolutions per second). To make the dashboard slider
mean "metres per second on the floor", the commanded rate is

.. code-block:: text

    u = v / (EFFICIENCY * C_Eff)

with ``EFFICIENCY`` = 0,885, the ground efficiency measured in sesi 3 §7. That
figure is **not** final (the ratio-vs-offset question is still open, and
``C_eff`` has 8,9 % uncertainty), so the scale is a named constant that can be
replaced once session 4 produces better numbers.

Sanity anchors
--------------
* ``u = 1,0`` rps with the forward pattern measured 0,19 m/s on the floor.
  :func:`command_for_speed` therefore returns ~1,036 rps for 0,19 m/s, which
  is the same operating point the hardware has actually been tested at.
* 0,15 rps stalls the motors completely and 0,3 rps drives (sesi 2 §9.7), so
  the useful low end is ~0,3 rps. :func:`is_above_stall_threshold` exists so
  the UI can warn instead of letting the robot buzz without moving.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Measured on this robot (sesi 3 §10). SI units.
TRACK_WIDTH_M = 0.145
WHEELBASE_M = 0.135

#: Half the wheel-to-wheel diagonal, (L + H) / 2. This is the lever arm that
#: turns a yaw rate into a wheel rate, and back.
HALF_DIAGONAL_M = (TRACK_WIDTH_M + WHEELBASE_M) / 2.0

# Distance travelled per wheel revolution (sesi 3 §6): 20,72 +/- 1,84 cm.
C_EFF_M = 0.2072
C_EFF_SD_M = 0.0184

# Ground efficiency measured in sesi 3 §7 (83-92 %, working value 0,885).
# NOT final: the "constant ratio" vs "fixed offset" question is still open.
EFFICIENCY = 0.885

# Motors stall below ~0,2-0,3 rps and drive at 0,3 rps (sesi 2 §9.7).
STALL_THRESHOLD_RPS = 0.3

# Roller projection factor for the standard 45 deg roller: the wheel's own
# rolling speed is cos(45 deg) times the chassis velocity component. It is
# divided out so that the forward case matches the measured rps <-> m/s
# relation (see the module docstring).
PROJECTION_FACTOR = math.cos(math.radians(45.0))

# The highest motor rate ever commanded on this robot: u = 1,0 rps, which
# measured 0,19 m/s on the floor (sesi 3 section 7). The lateral and yaw axes
# never exceed this, whatever the body command asks for.
#
# The cap matters because the *component* limits in safety.py do not bound the
# combined motion: a diagonal command (vx = vy = 0,19) needs 2,07 rps on two
# wheels, i.e. a faster wheel rate than a straight command of the same per-axis
# speed. Scaling the whole command down keeps every wheel inside the range
# that was actually measured.
MAX_TESTED_RPS = 1.0

#: Longitudinal-only wheel-rate cap, higher than the measured envelope.
#:
#: Forward/backward is the one motion on this robot whose sign convention has
#: been verified on the floor. It was reported as too slow twice at full slider,
#: and it is not a bug: at 1,0 rps the m/s mapping gives forward and strafe the
#: *same* wheel rate, so 0,19 m/s capped every axis. Lateral and yaw are left at
#: ``MAX_TESTED_RPS`` because those were reported as correct.
#:
#: 1,80 rps = ~0,33 m/s on the floor (wheel surface 0,373 m/s, ~108 rpm at the
#: wheel). The first step was 1,30; the operator still wanted more, so this is
#: the second. To retune, change this one number and keep ``max_linear_x`` in
#: ``robot_runtime.LIVE_LIMITS`` at or above ``speed_for_rate(MAX_FORWARD_RPS)``
#: or the clamp will quietly undo it.
#:
#: UNVERIFIED above 1,0 rps: no floor measurement exists. If the robot pulls to
#: one side, the wheels scrub, or the battery sags, lower it -- and check with
#: the ruler that the wheels actually reach the commanded rate, because a
#: torque-limited motor will draw more current without going faster.
MAX_FORWARD_RPS = 1.80

# Motor ids in the order the kinematic model uses them.
MOTOR_FIELDS: tuple[str, ...] = ("front_left", "rear_left", "front_right", "rear_right")
MOTOR_IDS: dict[str, int] = {
    "front_left": 1,
    "rear_left": 2,
    "front_right": 3,
    "rear_right": 4,
}

#: Rolling direction of each wheel, in degrees, measured from the robot's
#: forward axis and positive toward the left. This encodes the roller
#: arrangement (ABAB, from the chassis documentation) and is the assumption
#: that the floor verification has to confirm.
ROLLER_DIRECTION_DEG: dict[str, float] = {
    "front_left": 45.0,
    "rear_left": 135.0,
    "front_right": 135.0,
    "rear_right": 45.0,
}

#: Maps a wheel's rolling sense to the motor command sign. The forward column
#: is fixed by the verified pattern above; the other two are derived from the
#: roller arrangement and are the values to check at the hardware gate.
COMMAND_SIGN: dict[str, int] = {
    "front_left": -1,
    "rear_left": 1,
    "front_right": -1,
    "rear_right": 1,
}

#: Sign of the lateral contribution to the wheel speeds.
#:
#: **-1, verified on the floor on 2026-10-21.** The roller arrangement
#: documented as ABAB comes from the chassis PDF and was never checked on this
#: robot. The floor test showed that pressing "left" drove the robot to the
#: right, and "right" drove it left -- the lateral axis of the model was
#: mirrored. Forward was not affected (the forward pattern and the measured
#: 18,0 cm at 0,06 m/s both check out) and neither was the turn, which was
#: observed to be correct in both directions.
#:
#: This constant is the whole fix: the hardware gate exists precisely so that
#: a wrong assumption becomes one number here instead of a code change.
LATERAL_SIGN = -1.0

#: Wheel positions in the robot frame: forward offset and left offset.
WHEEL_POSITION_M: dict[str, tuple[float, float]] = {
    "front_left": (WHEELBASE_M / 2.0, TRACK_WIDTH_M / 2.0),
    "rear_left": (-WHEELBASE_M / 2.0, TRACK_WIDTH_M / 2.0),
    "front_right": (WHEELBASE_M / 2.0, -TRACK_WIDTH_M / 2.0),
    "rear_right": (-WHEELBASE_M / 2.0, -TRACK_WIDTH_M / 2.0),
}


@dataclass(frozen=True)
class MecanumModel:
    """Roller arrangement and motor-sign mapping used by the kinematics.

    The defaults are the values documented above. Changing them is how a
    wrong assumption found during the hardware gate gets corrected -- no code
    change is needed.
    """

    roller_direction_deg: dict[str, float] = None  # type: ignore[assignment]
    command_sign: dict[str, int] = None  # type: ignore[assignment]

    def roller_deg(self, field: str) -> float:
        return (self.roller_direction_deg or ROLLER_DIRECTION_DEG)[field]

    def sign(self, field: str) -> int:
        return (self.command_sign or COMMAND_SIGN)[field]


DEFAULT_MODEL = MecanumModel()


def command_for_speed(speed_mps: float, *, c_eff_m: float = C_EFF_M,
                      efficiency: float = EFFICIENCY) -> float:
    """Return the motor rate (rps) that should produce ``speed_mps`` on the floor.

    ``u = v / (efficiency * C_eff)``. With the session-3 constants, 0,19 m/s
    maps to ~1,036 rps, which is the operating point that was actually measured
    on the floor.
    """
    if c_eff_m <= 0.0:
        raise ValueError("c_eff_m must be positive")
    if efficiency <= 0.0:
        raise ValueError("efficiency must be positive")
    return speed_mps / (efficiency * c_eff_m)


def speed_for_rate(
    rate_rps: float,
    *,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
) -> float:
    """Inverse of :func:`command_for_speed`: the floor speed a rate should give."""
    return rate_rps * efficiency * c_eff_m


def rate_cap_for(
    linear_x: float,
    linear_y: float,
    angular_z: float,
) -> float:
    """Wheel-rate cap that applies to one body command.

    Only a purely longitudinal command may use the higher forward cap. Anything
    with a lateral or yaw component stays inside the measured 1,0 rps envelope,
    because those two axes are still derived from the roller arrangement rather
    than verified on the floor.
    """
    if linear_x != 0.0 and linear_y == 0.0 and angular_z == 0.0:
        return MAX_FORWARD_RPS
    return MAX_TESTED_RPS


def drive_command(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    *,
    model: MecanumModel = DEFAULT_MODEL,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
) -> list[tuple[int, float]]:
    """:func:`command_for_body_velocity` with the per-axis rate cap applied.

    This is the one function that turns a body command into wire values. The
    chassis adapter and the dashboard's status bar both call it, so the number
    the operator reads cannot drift from the number the wheels are told -- that
    drift is what once made a stalled robot look like a moving one.
    """
    return command_for_body_velocity(
        linear_x,
        linear_y,
        angular_z,
        model=model,
        c_eff_m=c_eff_m,
        efficiency=efficiency,
        max_rate_rps=rate_cap_for(linear_x, linear_y, angular_z),
    )


def yaw_rate_for_wheel_rate(
    rate_rps: float,
    *,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
) -> float:
    """Return the yaw rate (rad/s) that drives every wheel at ``rate_rps``.

    The dashboard has one speed slider for all six directions. For the
    translational axes the number means metres per second, which is what the
    operator expects. Using that same number as rad/s for the yaw axis asks for
    a wheel rate about 7x below the stall threshold -- turning would buzz and
    never move. Converting keeps the slider meaning "how hard the wheels are
    driven" on every axis.

    Derived from the yaw term in :func:`wheel_speeds`: a pure yaw rate ``w``
    turns every wheel at ``w * HALF_DIAGONAL_M / c_eff_m`` revolutions per
    second, and :func:`motor_commands` divides the body velocity by
    ``efficiency`` before distributing it, so the inverse is
    ``w = rate_rps * c_eff_m * efficiency / HALF_DIAGONAL_M``.
    """
    if HALF_DIAGONAL_M <= 0.0:
        raise ValueError("geometry must be positive")
    if c_eff_m <= 0.0:
        raise ValueError("c_eff_m must be positive")
    if efficiency <= 0.0:
        raise ValueError("efficiency must be positive")
    return rate_rps * c_eff_m * efficiency / HALF_DIAGONAL_M


def is_above_stall_threshold(
    rate_rps: float,
    *,
    threshold_rps: float = STALL_THRESHOLD_RPS,
) -> bool:
    """True when ``rate_rps`` is high enough for the wheels to actually turn.

    0,15 rps makes the motors buzz without moving; 0,3 rps drives. The UI uses
    this to warn the operator instead of silently doing nothing.
    """
    return abs(rate_rps) >= threshold_rps


def wheel_speeds(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    *,
    model: MecanumModel = DEFAULT_MODEL,
) -> dict[str, float]:
    """Return the forward-axis speed of each wheel (m/s) for a body velocity.

    Body frame: ``linear_x`` forward (m/s), ``linear_y`` to the left (m/s),
    ``angular_z`` counter-clockwise seen from above (rad/s).

    The roller projection is divided by ``cos(45 deg)`` so that a straight
    forward command gives the wheels exactly ``linear_x`` -- that is what ties
    the model to the measured ``C_eff``.
    """
    speeds: dict[str, float] = {}
    for field in MOTOR_FIELDS:
        angle = math.radians(model.roller_deg(field))
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        forward_offset, left_offset = WHEEL_POSITION_M[field]
        rolling = (
            linear_x * cos_a
            + LATERAL_SIGN * linear_y * sin_a
            - angular_z * (forward_offset * sin_a + left_offset * cos_a)
        )
        speeds[field] = rolling / PROJECTION_FACTOR
    return speeds


def motor_commands(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    *,
    model: MecanumModel = DEFAULT_MODEL,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
    max_rate_rps: float = MAX_TESTED_RPS,
) -> dict[str, float]:
    """Return the motor rate (rps) per wheel for a body velocity.

    The body velocity is scaled to the floor speed the operator asked for
    (``efficiency`` compensates the measured ground loss), then distributed over
    the wheels by :func:`wheel_speeds` and converted to rps.
    """
    scaled_x = linear_x / efficiency
    scaled_y = linear_y / efficiency
    scaled_z = angular_z / efficiency
    speeds = wheel_speeds(scaled_x, scaled_y, scaled_z, model=model)
    commands = {
        field: model.sign(field) * speed / c_eff_m
        for field, speed in speeds.items()
    }
    return clamp_to_max_rate(commands, max_rate_rps=max_rate_rps)


def clamp_to_max_rate(
    commands: dict[str, float],
    *,
    max_rate_rps: float = MAX_TESTED_RPS,
) -> dict[str, float]:
    """Scale a whole command set down so no wheel exceeds ``max_rate_rps``.

    Scaling (rather than clipping) keeps the *direction* of the motion intact:
    clipping one wheel would turn a diagonal into a curve.
    """
    if not commands:
        return commands
    peak = max(abs(rate) for rate in commands.values())
    if peak <= max_rate_rps or peak == 0.0:
        return commands
    factor = max_rate_rps / peak
    return {field: rate * factor for field, rate in commands.items()}


def command_for_body_velocity(
    linear_x: float,
    linear_y: float,
    angular_z: float,
    *,
    model: MecanumModel = DEFAULT_MODEL,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
    max_rate_rps: float = MAX_TESTED_RPS,
) -> list[tuple[int, float]]:
    """Return ``(motor_id, rps)`` pairs ready for :func:`build_motor_frame`."""
    commands = motor_commands(
        linear_x, linear_y, angular_z,
        model=model, c_eff_m=c_eff_m, efficiency=efficiency,
        max_rate_rps=max_rate_rps,
    )
    return [(MOTOR_IDS[field], commands[field]) for field in MOTOR_FIELDS]


def direction_report(
    *,
    model: MecanumModel = DEFAULT_MODEL,
    c_eff_m: float = C_EFF_M,
    efficiency: float = EFFICIENCY,
) -> list[str]:
    """Return one line per direction with the exact motor commands it produces.

    This is the table to compare against what the robot actually does at the
    hardware gate: every line is a pattern the operator can read off the
    wheels. The forward line must show ``1:- 2:- 3:+ 4:+`` (verified); the
    lateral and yaw lines are the ones to confirm.
    """
    speed = 0.19
    turn = 1.0
    directions = [
        ("maju (forward)", (speed, 0.0, 0.0)),
        ("mundur (backward)", (-speed, 0.0, 0.0)),
        ("samping kiri (strafe left)", (0.0, speed, 0.0)),
        ("samping kanan (strafe right)", (0.0, -speed, 0.0)),
        ("putar kiri (yaw CCW)", (0.0, 0.0, turn)),
        ("putar kanan (yaw CW)", (0.0, 0.0, -turn)),
        ("diagonal maju-kiri", (speed, speed, 0.0)),
        ("diagonal maju-kanan", (speed, -speed, 0.0)),
    ]
    lines = []
    for label, (vx, vy, wz) in directions:
        pairs = command_for_body_velocity(
            vx, vy, wz, model=model, c_eff_m=c_eff_m, efficiency=efficiency,
        )
        pattern = "  ".join(
            f"{motor_id}:{'+' if rate >= 0 else '-'}" for motor_id, rate in pairs
        )
        rates = "  ".join(f"{motor_id}:{rate:+.3f}" for motor_id, rate in pairs)
        lines.append(f"{label:24s} {pattern}   [{rates} rps]")
    return lines
