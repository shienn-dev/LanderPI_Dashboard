"""Camera probe tests using a fake sysfs tree (no real device is touched)."""

from __future__ import annotations

from pathlib import Path

from amr_core.robot.camera import probe_camera
from amr_core.robot.interfaces import ConnectionState


def _make_sysfs(tmp_path: Path) -> Path:
    (tmp_path / "class" / "video4linux").mkdir(parents=True)
    (tmp_path / "bus" / "usb" / "devices").mkdir(parents=True)
    return tmp_path


def _add_video_node(sysfs: Path, node: str, name: str) -> None:
    directory = sysfs / "class" / "video4linux" / node
    directory.mkdir(parents=True)
    (directory / "name").write_text(name)


def _add_usb(sysfs: Path, dev: str, vid: str, pid: str) -> None:
    directory = sysfs / "bus" / "usb" / "devices" / dev
    directory.mkdir(parents=True)
    (directory / "idVendor").write_text(vid)
    (directory / "idProduct").write_text(pid)


def test_no_camera(tmp_path: Path) -> None:
    status = probe_camera(_make_sysfs(tmp_path), feed_path=tmp_path / "tidak-ada.bin")
    assert status.kind == "none"
    assert status.frames_available is False
    assert status.state is ConnectionState.UNAVAILABLE


def test_depth_camera_present_but_unavailable(tmp_path: Path) -> None:
    sysfs = _make_sysfs(tmp_path)
    _add_usb(sysfs, "2-2", "3251", "1930")
    status = probe_camera(sysfs, feed_path=tmp_path / "belum-jalan.bin")
    assert status.kind == "depth"
    assert status.frames_available is False
    assert "Aurora 930" in status.detail
    # The SDK is installed and frames are possible, so the detail must point at
    # the reader that is not running instead of telling the operator to install
    # something that is already there.
    assert "camera_depth_live" in status.detail


def test_a_live_feed_makes_the_camera_connected(tmp_path: Path, write_feed) -> None:
    sysfs = _make_sysfs(tmp_path)
    _add_usb(sysfs, "4-2", "3251", "1930")
    feed = tmp_path / "hidup.bin"
    write_feed(feed, seq=20, width=4, height=2, frames_total=3)
    status = probe_camera(sysfs, feed_path=feed)
    assert status.state is ConnectionState.CONNECTED
    assert status.frames_available is True
    assert status.kind == "depth"
    assert "4x2" in status.detail


def test_a_stale_feed_is_not_a_live_feed(tmp_path: Path, write_feed) -> None:
    sysfs = _make_sysfs(tmp_path)
    _add_usb(sysfs, "4-2", "3251", "1930")
    feed = tmp_path / "basi.bin"
    write_feed(feed, seq=22, age_ms=9000)      # published 9 s ago
    status = probe_camera(sysfs, feed_path=feed)
    assert status.state is ConnectionState.UNAVAILABLE
    assert status.frames_available is False
    assert "berhenti" in status.detail


def test_uvc_node_detected(tmp_path: Path) -> None:
    sysfs = _make_sysfs(tmp_path)
    _add_video_node(sysfs, "video0", "USB Camera: HD")
    status = probe_camera(sysfs, feed_path=tmp_path / "kosong.bin")
    assert status.kind == "usb"
    assert status.frames_available is False


def test_pi_internal_nodes_are_not_cameras(tmp_path: Path) -> None:
    sysfs = _make_sysfs(tmp_path)
    _add_video_node(sysfs, "video19", "rpivid")
    _add_video_node(sysfs, "video20", "pispbe-input")
    status = probe_camera(sysfs, feed_path=tmp_path / "kosong.bin")
    assert status.kind == "none"
