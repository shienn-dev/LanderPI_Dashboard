"""Smooth arm control: one drag is one move, not twenty clicks.

Why this module exists (operator, 2026-10-29): the first live panel moved 10
pulses per click with 0,8 s behind each press, so repositioning one joint by 200
pulses cost twenty clicks and about twenty seconds of standing in front of the
screen. That is not a hardware limit. The set-position frame already carries a
duration in milliseconds (``SUB_SET_POSITION``), so the board can be handed the
whole move at once and the servo interpolates it.

Where the speeds come from -- not invented:

- The vendor's own action groups (``garbage_pick.d6a``, ``camera_up.d6a``, read
  off the original SD card on 2026-10-28) move joints at 115-220 pulses/s:
  500 -> 720 in 1500 ms, 125 -> 250 in 1000 ms, 165 -> 330 in 1000 ms.
- ``DEFAULT_SPEED_PPS`` sits in that band, so a 200-pulse reposition becomes a
  single 1,3 s frame instead of twenty presses.

What is measured and what is not: the frame layout and the limits are measured;
that the servo follows the requested duration smoothly is the vendor's contract
(``Time`` column of the action groups) and is **not yet observed on this arm**.
The controller therefore never sends a duration below ``MIN_DURATION_S`` and
re-derives the duration on every flush from the last *commanded* pulse, so a
drag that outruns the arm slows the arm instead of asking it to snap.

Nothing here actuates by itself: ``flush()`` only transmits what
``set_target()`` was told by a human dragging a slider, and the gripper (servo
10) is refused at the transport as well as absent from the panel.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from amr_core.robot.arm_bus import ARM_JOINT_IDS, GRIPPER_ID, MIN_DURATION_S
from amr_core.robot.interfaces import CommandOutcome

#: Vendor action groups move joints at 115-220 pulses/s (see module docstring).
DEFAULT_SPEED_PPS = 150.0
MIN_SPEED_PPS = 40.0
MAX_SPEED_PPS = 400.0

#: A whole-range move (900 pulses at 40 pps) is 22 s; cap it rather than
#: silently speeding the arm up past what the operator asked for.
MAX_DURATION_S = 8.0

#: How long a measured pulse stays good enough to plan from.
POSITION_MAX_AGE_S = 2.0

#: The panel paces writes with a timer at this interval (5 Hz). A drag can emit
#: far more events than that; this is what keeps the board from being flooded and
#: still lands the final value within one tick.
FLUSH_INTERVAL_S = 0.2

#: How long a target must stop changing before it is sent. A drag emits events
#: tens of times a second; each one updating a *pending* value costs nothing, but
#: sending a frame per event would re-target the servo several times a second and
#: restart its motion profile every time -- the stutter the operator reported on
#: 2026-10-29. So the board hears a joint only once the handle has been still for
#: this long (or immediately, for the -10/+10 buttons, which are single acts).
SETTLE_S = 0.35


def clamp_speed(speed_pps: float) -> float:
    """Keep the speed in the band the vendor's own action groups use."""
    return max(MIN_SPEED_PPS, min(MAX_SPEED_PPS, float(speed_pps)))


@dataclass(frozen=True)
class MovePlan:
    """One frame's worth of motion: where to go, and how long to take."""

    servo_id: int
    start: int | None
    target: int
    duration_s: float
    changed: bool


@dataclass(frozen=True)
class JogResult:
    """What actually happened to one requested move."""

    plan: MovePlan | None = None
    outcome: CommandOutcome | None = None
    reason: str = ""

    @property
    def sent(self) -> bool:
        return bool(self.outcome is not None and self.outcome.transmitted)


def plan_move(
    servo_id: int,
    start: int | None,
    target: int,
    *,
    limits: dict[int, tuple[int, int]],
    speed_pps: float = DEFAULT_SPEED_PPS,
    min_duration_s: float = MIN_DURATION_S,
) -> MovePlan:
    """Clamp ``target`` to that servo's measured limit and pick a duration.

    ``start`` may be ``None`` when the servo has never answered: the target is
    still clamped, and the duration falls back to the floor rather than dividing
    by an imagined distance.
    """
    if servo_id not in limits:
        known = sorted(limits)
        raise ValueError(f"servo {servo_id} is not a known arm joint {known}")
    low, high = limits[servo_id]
    clamped = max(low, min(high, int(target)))
    if start is None:
        return MovePlan(servo_id, None, clamped, min_duration_s, True)
    delta = abs(clamped - int(start))
    if delta == 0:
        return MovePlan(servo_id, int(start), clamped, min_duration_s, False)
    duration = delta / clamp_speed(speed_pps)
    duration = max(min_duration_s, min(MAX_DURATION_S, duration))
    return MovePlan(servo_id, int(start), clamped, duration, True)


class ArmJogController:
    """Slider -> pending target -> one frame per joint, paced by a UI timer.

    The panel only *records* the value the operator dragged to; ``flush()`` is
    called a few times a second and turns each pending value into a single
    ``set position`` frame. Splitting it this way is what keeps a drag from
    flooding the board: whatever the slider emits, at most one frame per joint
    per flush interval goes out, and it always carries the latest value.
    """

    def __init__(
        self,
        arm,
        *,
        speed_pps: float = DEFAULT_SPEED_PPS,
        limits: dict[int, tuple[int, int]] | None = None,
        settle_s: float = SETTLE_S,
        clock=time.monotonic,
    ) -> None:
        self.arm = arm
        self.limits = dict(limits if limits is not None else arm.limits)
        self.speed_pps = clamp_speed(speed_pps)
        self.settle_s = max(0.0, float(settle_s))
        self._clock = clock
        #: Last pulse a servo answered with, and when.
        self.measured: dict[int, int | None] = {}
        self._measured_at: dict[int, float] = {}
        #: Last pulse we told a servo to go to -- the base for the next duration.
        self.commanded: dict[int, int] = {}
        self._pending: dict[int, int] = {}
        self._changed_at: dict[int, float] = {}
        self.halted = False
        self.frames_sent = 0
        self.last: JogResult | None = None
        self.syncing = False

    # -- readings --------------------------------------------------------
    def position(self, servo_id: int, *, max_age_s: float = POSITION_MAX_AGE_S) -> int | None:
        """The freshest known pulse for one joint, reading the servo if stale."""
        fresh = self._clock() - self._measured_at.get(servo_id, -1e9) <= max_age_s
        if fresh and servo_id in self.measured:
            return self.measured[servo_id]
        return self.refresh((servo_id,)).get(servo_id)

    def refresh(self, ids: tuple[int, ...] | None = None) -> dict[int, int | None]:
        """Read the real positions. Read-only: this cannot move the arm."""
        values = self.arm.read_positions(ids=ids)
        now = self._clock()
        for servo_id, pulse in values.items():
            self.measured[servo_id] = pulse
            self._measured_at[servo_id] = now
            if pulse is not None:
                # The servo just told us where it is; that beats any command we
                # remember, and it is the honest base for the next duration.
                self.commanded.pop(servo_id, None)
        return values

    def start_for(self, servo_id: int) -> int | None:
        """Where the next move starts from: last command, else a fresh read."""
        if servo_id in self.commanded:
            return self.commanded[servo_id]
        return self.position(servo_id)

    # -- intent ----------------------------------------------------------
    def set_speed(self, speed_pps: float) -> float:
        self.speed_pps = clamp_speed(speed_pps)
        return self.speed_pps

    def set_target(
        self, servo_id: int, pulse: float | int | None, *, immediate: bool = False
    ) -> MovePlan:
        """Record what the operator dragged to. Sends nothing yet.

        ``immediate=True`` (the -10/+10 buttons, one deliberate act) lets the
        next flush send it straight away; a drag leaves the normal settle delay,
        so a moving handle never reaches the board.
        """
        if self.syncing:
            raise RuntimeError("slider value applied by refresh(), not by the operator")
        if servo_id == GRIPPER_ID:
            raise ValueError("servo 10 is the gripper and is never commanded")
        if servo_id not in self.limits:
            raise ValueError(f"servo {servo_id} is not a known arm joint {sorted(self.limits)}")
        if pulse is None:
            raise ValueError("no target value")
        plan = plan_move(
            servo_id,
            self.start_for(servo_id),
            int(pulse),
            limits=self.limits,
            speed_pps=self.speed_pps,
        )
        self.halted = False
        self._pending[servo_id] = plan.target
        self._changed_at[servo_id] = (
            float("-inf") if immediate else self._clock()
        )
        return plan

    def settled(self, servo_id: int) -> bool:
        """True when this joint's target has stopped changing long enough."""
        return self._clock() - self._changed_at.get(servo_id, float("-inf")) >= self.settle_s

    def preview(self, servo_id: int) -> MovePlan | None:
        target = self._pending.get(servo_id)
        if target is None:
            return None
        return plan_move(
            servo_id,
            self.start_for(servo_id),
            target,
            limits=self.limits,
            speed_pps=self.speed_pps,
        )

    def plan_for(self, servo_id: int, pulse: float | int) -> MovePlan:
        """What a move to ``pulse`` *would* be -- sends nothing, records nothing.

        Used to show the operator the target and the duration before anything is
        pending (e.g. the value a drag is heading for).
        """
        return plan_move(
            servo_id,
            self.start_for(servo_id),
            int(pulse),
            limits=self.limits,
            speed_pps=self.speed_pps,
        )

    def flush(self) -> list[JogResult]:
        """Send every *settled* pending target as one frame. Never raises."""
        if not self._pending:
            return []
        ready = [sid for sid in sorted(self._pending) if self.settled(sid)]
        if not ready:
            return []
        results: list[JogResult] = []
        for servo_id in ready:
            target = self._pending.pop(servo_id)
            self._changed_at.pop(servo_id, None)
            results.append(self._send(servo_id, target))
        return results

    def _send(self, servo_id: int, target: int) -> JogResult:
        start = self.start_for(servo_id)
        if start is None:
            result = JogResult(
                None,
                None,
                f"servo {servo_id} tidak menjawab - tidak ada perintah yang dikirim",
            )
            self.last = result
            return result
        plan = plan_move(
            servo_id,
            start,
            target,
            limits=self.limits,
            speed_pps=self.speed_pps,
        )
        if not plan.changed:
            result = JogResult(plan, None, f"sendi {servo_id} sudah di {plan.target}")
            self.last = result
            return result
        try:
            outcome = self.arm.move_joints({servo_id: plan.target}, duration_s=plan.duration_s)
        except Exception as exc:  # noqa: BLE001 - a timer callback must never raise
            result = JogResult(plan, None, f"write gagal: {type(exc).__name__}: {exc}")
            self.last = result
            return result
        if outcome.transmitted:
            self.commanded[servo_id] = plan.target
            self.frames_sent += 1
        result = JogResult(
            plan,
            outcome,
            f"sendi {servo_id}: {plan.start} -> {plan.target} dalam {plan.duration_s:.1f} s",
        )
        self.last = result
        return result

    def stop(self) -> JogResult:
        """STOP wins: drop everything pending, then stop the five joints."""
        self._pending.clear()
        self._changed_at.clear()
        self.halted = True
        self.commanded.clear()
        try:
            outcome = self.arm.stop()
        except Exception as exc:  # noqa: BLE001
            result = JogResult(None, None, f"stop gagal: {type(exc).__name__}: {exc}")
            self.last = result
            return result
        result = JogResult(None, outcome, f"STOP: {outcome.reason}")
        self.last = result
        return result

    # -- helpers ---------------------------------------------------------
    @property
    def joint_ids(self) -> tuple[int, ...]:
        return tuple(sid for sid in ARM_JOINT_IDS if sid in self.limits)