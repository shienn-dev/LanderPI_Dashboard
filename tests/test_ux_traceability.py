"""Regression tests for Phase 1.4 — BOOT lifecycle (F7), interface
traceability (F6), and reduced dashboard rebuilds (F9).

These are unit tests over ``amr_core`` and the ``amr_dashboard.app`` helper
functions. They are not browser/end-to-end tests: no web page is rendered and no
click is simulated.
"""

from __future__ import annotations

from amr_core.interfaces import (
    CONTRACT_ROW_BY_CONSTANT,
    IMPLEMENTED_NAMES,
    INTERFACE_CONTRACT,
    InterfaceStatus,
    documented_status,
    status_of,
)
from amr_core.simulation import SimulationEngine
from amr_core.states import RobotState
from amr_dashboard import app as dash

# --------------------------------------------------------------------------- #
# F7 — BOOT lifecycle
# --------------------------------------------------------------------------- #

def test_default_construction_completes_health_check() -> None:
    # Backward-compatible default: the constructor finishes the check.
    engine = SimulationEngine()
    assert engine.state is RobotState.READY


def test_auto_check_false_stays_in_boot() -> None:
    engine = SimulationEngine(auto_check=False)
    assert engine.state is RobotState.BOOT
    assert engine._boot_completed is False
    # Health map is initialized even though the check has not run.
    assert engine.health  # non-empty
    assert all(item.ok for item in engine.health.values())


def test_boot_is_observable_and_then_health_pass_moves_to_ready() -> None:
    engine = SimulationEngine(auto_check=False)
    assert engine.state is RobotState.BOOT  # observable before the check

    result = engine.run_health_check()

    assert result.allowed
    assert engine.state is RobotState.READY


def test_boot_is_observable_and_then_health_failure_moves_to_fault() -> None:
    engine = SimulationEngine(auto_check=False)
    assert engine.state is RobotState.BOOT

    engine.apply_health("lidar", False)  # critical component fails during boot
    result = engine.run_health_check()

    assert result.allowed
    assert engine.state is RobotState.FAULT
    assert "LiDAR" in engine.last_reason


def test_run_health_check_is_idempotent() -> None:
    engine = SimulationEngine(auto_check=False)
    first = engine.run_health_check()
    assert engine.state is RobotState.READY

    second = engine.run_health_check()  # must not transition again
    assert not second.changed
    assert engine.state is RobotState.READY
    assert first.allowed and second.allowed


def test_boot_failure_does_not_auto_recover_on_second_check() -> None:
    engine = SimulationEngine(auto_check=False)
    engine.apply_health("camera", False)
    engine.run_health_check()
    assert engine.state is RobotState.FAULT

    # Recovering the component alone does not leave FAULT (needs RESET).
    engine.apply_health("camera", True)
    assert engine.state is RobotState.FAULT
    engine.run_health_check()  # idempotent no-op, still FAULT
    assert engine.state is RobotState.FAULT


def test_boot_state_allows_mission_editing_and_blocks_start() -> None:
    engine = SimulationEngine(auto_check=False)
    assert engine.state is RobotState.BOOT
    assert engine.can_edit_mission()
    assert not engine.can_start().allowed  # START not allowed from BOOT


def test_dashboard_engine_starts_in_boot() -> None:
    state = dash.DashboardState()
    assert state.engine.state is RobotState.BOOT
    # Completing the boot check (as the first tick does) reaches READY.
    state.engine.run_health_check()
    assert state.engine.state is RobotState.READY


# --------------------------------------------------------------------------- #
# F6 — interface traceability
# --------------------------------------------------------------------------- #

def test_every_implemented_name_maps_to_a_contract_row() -> None:
    rows = {spec.name for spec in INTERFACE_CONTRACT}
    for constant in IMPLEMENTED_NAMES:
        assert constant in CONTRACT_ROW_BY_CONSTANT
        assert CONTRACT_ROW_BY_CONSTANT[constant] in rows


def test_implemented_names_are_all_rancangan() -> None:
    for name in IMPLEMENTED_NAMES:
        assert status_of(name) is InterfaceStatus.RANCANGAN


def test_documented_verified_names_are_marked_terverifikasi() -> None:
    statuses = {spec.name: spec.status for spec in INTERFACE_CONTRACT}
    assert statuses["/scan"] is InterfaceStatus.TERVERIFIKASI
    assert statuses["/odom + TF odom -> base_footprint"] is InterfaceStatus.TERVERIFIKASI
    assert statuses["Frame map -> odom -> base_footprint"] is InterfaceStatus.TERVERIFIKASI


def test_status_of_helper_matches_contract() -> None:
    assert status_of("/amr/mission_state") is InterfaceStatus.RANCANGAN
    assert status_of("/not/real") is None
    # Documented-only rows use the direct row lookup.
    assert documented_status("/scan") is InterfaceStatus.TERVERIFIKASI
    assert documented_status("/not/real") is None


def test_verified_note_is_qualified_to_upstream_repo() -> None:
    # "Terverifikasi di LanderPi" is upstream-only, not the school robot.
    scan = next(s for s in INTERFACE_CONTRACT if s.name == "/scan")
    assert "upstream" in scan.note.lower()
    frame = next(
        s for s in INTERFACE_CONTRACT if s.name == "Frame map -> odom -> base_footprint"
    )
    assert "upstream" in frame.note.lower()


def test_contract_has_no_duplicate_names() -> None:
    names = [spec.name for spec in INTERFACE_CONTRACT]
    assert len(names) == len(set(names))


# --------------------------------------------------------------------------- #
# F9 — reduced rebuilds
# --------------------------------------------------------------------------- #

def test_layout_signature_is_stable_for_same_mode() -> None:
    state = dash.DashboardState()
    assert dash.layout_signature(state) == dash.layout_signature(state)


def test_layout_signature_changes_only_with_mode_or_live_state() -> None:
    state = dash.DashboardState()
    before = dash.layout_signature(state)

    # Simulated engine progress must NOT change the layout signature.
    state.engine.run_health_check()
    state.engine.start_mission()
    state.engine.tick(2.0)
    assert dash.layout_signature(state) == before

    # Switching mode DOES change it.
    state.mode = "development"
    assert dash.layout_signature(state) != before


def test_layout_signature_is_hashable_and_small() -> None:
    sig = dash.layout_signature(dash.DashboardState())
    assert isinstance(sig, tuple)
    assert hash(sig) is not None  # usable for equality comparison
    # Two entries: the mode, and the chassis live/offline state. The second one
    # is what makes the panel rebuild itself after the ONLINE button opens the
    # port -- see tests/test_dashboard_chassis_online.py.
    assert sig == ("competition", "offline")


# --------------------------------------------------------------------------- #
# Regression: event log not duplicated, draft isolation, START/RESET/lock
# --------------------------------------------------------------------------- #

class _RecordingLog:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def push(self, text: str) -> None:  # noqa: D401 - test double
        self.lines.append(text)


def test_refresh_does_not_duplicate_events() -> None:
    from amr_dashboard import panels

    state = dash.DashboardState()
    state.engine.run_health_check()
    log = _RecordingLog()

    cursor = panels.append_events(log, state.engine, state.log_cursor)  # type: ignore[arg-type]
    count = len(log.lines)

    # Re-rendering (as each tick does) must not duplicate existing entries.
    cursor = panels.append_events(log, state.engine, cursor)  # type: ignore[arg-type]
    assert len(log.lines) == count

    state.engine.log("one more")
    cursor = panels.append_events(log, state.engine, cursor)  # type: ignore[arg-type]
    assert len(log.lines) == count + 1


def test_draft_stays_isolated_from_active_mission() -> None:
    state = dash.DashboardState()
    state.engine.run_health_check()
    assert state.draft is not state.engine.mission
    active = state.engine.mission
    assert active is not None
    active_before = active.time_limit_s
    dash._set_field(state, "time_limit_s", 123)
    assert active.time_limit_s == active_before


def test_boot_completion_preserves_start_lock_and_reset_rules() -> None:
    state = dash.DashboardState()
    state.engine.run_health_check()
    assert state.engine.state is RobotState.READY

    # START allowed in READY with a valid mission.
    assert state.engine.can_start().allowed
    state.engine.start_mission()
    assert state.engine.state is RobotState.RUNNING
    assert not state.engine.can_edit_mission()  # locked while RUNNING

    # RESET is refused while RUNNING (only DONE/FAILED/STOPPED/FAULT).
    assert not state.engine.reset().allowed
    assert state.engine.state is RobotState.RUNNING
