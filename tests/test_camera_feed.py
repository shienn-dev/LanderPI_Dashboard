"""Tests for the dashboard's depth-feed reader (no camera, no SDK, no hardware).

The C++ reader (`~/AMRTestLander/tools/camera_reader/camera_depth_stream`) owns
the file format; these tests write the same bytes by hand so the reader's
guarantees can be checked without a camera attached:

* an intact frame decodes, with the header fields the panel displays,
* a mid-write (odd `seq`) frame is refused rather than shown,
* a frame whose `seq` moved between the header read and the payload read is
  refused -- that is the whole point of the seqlock,
* a foreign or truncated file is refused instead of interpreted,
* the statistics and the derived frame rate are correct on known numbers.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from amr_dashboard import camera_feed

HEADER_FMT = "<IIIIIIIIQQIIII"
MAGIC = 0x414D5244
HEADER_BYTES = 64


def test_missing_file_is_not_an_error(tmp_path: Path, write_feed) -> None:
    assert camera_feed.read_frame(tmp_path / "tidak-ada.bin") is None


def test_a_foreign_file_is_refused(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "asing.bin"
    write_feed(path, magic_value=0xDEADBEEF)
    assert camera_feed.read_frame(path) is None


def test_a_truncated_header_is_refused(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "potong.bin"
    path.write_bytes(b"\x44\x52\x4d\x41")
    assert camera_feed.read_frame(path) is None


def test_a_mid_write_frame_is_refused(tmp_path: Path, write_feed) -> None:
    """`seq` odd means the writer is still copying: show nothing, not half a frame."""
    path = tmp_path / "setengah.bin"
    write_feed(path, seq=3)
    assert camera_feed.read_frame(path) is None


def test_an_intact_frame_decodes_with_its_header(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "bagus.bin"
    payload = write_feed(path, seq=8, frames_total=12)
    frame = camera_feed.read_frame(path)
    assert frame is not None
    assert (frame.width, frame.height) == (4, 2)
    assert frame.payload == payload
    assert frame.header.seq == 8
    assert frame.header.frames_total == 12
    assert frame.header.running is True
    assert frame.header.age_ms < 1000          # fresh, not a stale file
    assert frame.pixels()[:4].tolist() == [100, 200, 300, 400]


def test_a_stale_frame_is_not_a_live_frame(tmp_path: Path, write_feed) -> None:
    """A reader that died leaves a valid file: reading it must not mean "live"."""
    path = tmp_path / "fosil.bin"
    write_feed(path, seq=12, age_ms=4000)
    assert camera_feed.read_frame(path) is not None     # the file is intact ...
    assert camera_feed.live_frame(path) is None         # ... but it is not live


def test_a_fresh_frame_is_a_live_frame(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "segar.bin"
    write_feed(path, seq=14, age_ms=5)
    frame = camera_feed.live_frame(path)
    assert frame is not None
    assert frame.header.seq == 14
    assert camera_feed.live_frame(path, max_age_ms=1) is None


def test_a_frame_overwritten_during_the_copy_is_refused(tmp_path: Path, write_feed) -> None:
    """The seqlock guard: header says seq 2, the file now holds seq 4."""
    from amr_core.robot.camera import read_depth_header, read_depth_payload

    path = tmp_path / "ditimpa.bin"
    write_feed(path, seq=2)
    header = read_depth_header(path)
    assert header is not None and header.seq == 2
    write_feed(path, seq=4)                    # writer published while we looked
    assert read_depth_payload(header, path) is None


def test_statistics_match_known_pixels(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "stats.bin"
    write_feed(path, width=4, height=2, pixels=[0, 100, 0, 200, 300, 0, 400, 0])
    frame = camera_feed.read_frame(path)
    assert frame is not None
    stats = camera_feed.depth_stats(frame, stride=1)
    assert stats.total == 8
    assert stats.invalid == 4
    assert stats.invalid_pct == pytest.approx(50.0)
    assert stats.minimum == 100
    assert stats.maximum == 400
    assert stats.median == 250                 # sorted valid: 100,200,300,400


def test_an_all_invalid_frame_says_so_instead_of_zero_metres(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "kosong.bin"
    write_feed(path, width=2, height=2, pixels=[0, 0, 0, 0])
    frame = camera_feed.read_frame(path)
    assert frame is not None
    stats = camera_feed.depth_stats(frame, stride=1)
    assert stats.invalid_pct == pytest.approx(100.0)
    assert stats.median == 0
    assert stats.valid_pct == pytest.approx(0.0)


def test_frame_rate_uses_the_writer_s_own_counters(tmp_path: Path, write_feed) -> None:
    """Rate from (frames_total, host_ms): a restarted writer must not fake a rate."""
    path = tmp_path / "laju.bin"
    write_feed(path, seq=10, frames_total=100, age_ms=10)
    frame = camera_feed.read_frame(path)
    assert frame is not None
    header = frame.header
    assert camera_feed.frame_rate(None, header) is None                     # no baseline
    assert camera_feed.frame_rate((100, header.host_ms), header) is None    # no new frame
    assert camera_feed.frame_rate((95, header.host_ms - 500), header) == pytest.approx(10.0)
    # writer restarted between renders: counters go backwards -> no number
    assert camera_feed.frame_rate((500, header.host_ms - 500), header) is None


def test_the_picture_is_a_png_and_invalid_pixels_are_black(tmp_path: Path, write_feed) -> None:
    pytest.importorskip("PIL")
    path = tmp_path / "gambar.bin"
    write_feed(path, width=2, height=2, pixels=[0, 500, 1000, 2000])
    frame = camera_feed.read_frame(path)
    assert frame is not None

    raw = camera_feed.render_png(frame, max_width=8)
    assert raw is not None
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"

    import io

    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    assert image.size == (2, 2)
    pixels = list(image.tobytes())             # 8-bit greyscale, row-major
    assert pixels[0] == 0                      # invalid (0) stays black
    assert pixels[1] > pixels[3]               # near is brighter than far

    encoded = camera_feed.render_png_base64(frame, max_width=8)
    assert encoded is not None
    assert base64.b64decode(encoded)[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_panel_reports_a_live_feed(tmp_path: Path, monkeypatch, write_feed) -> None:
    """probe_camera + the reader agree on the same file: CONNECTED and frames=True."""
    from amr_core.robot.camera import probe_camera
    from amr_core.robot.interfaces import ConnectionState

    path = tmp_path / "hidup.bin"
    write_feed(path, seq=30, width=4, height=2)
    monkeypatch.setattr(camera_feed, "DEFAULT_FEED_PATH", path)

    status = probe_camera(tmp_path, feed_path=path)
    assert status.state is ConnectionState.CONNECTED
    assert status.frames_available is True
    assert status.kind == "depth"
    assert "4x2" in status.detail

    frame = camera_feed.read_frame(path)
    assert frame is not None
    assert frame.header.seq == 30


def test_the_probe_says_the_reader_stopped_when_the_frame_is_stale(
    tmp_path: Path, write_feed
) -> None:
    from amr_core.robot.camera import probe_camera
    from amr_core.robot.interfaces import ConnectionState

    path = tmp_path / "basi.bin"
    write_feed(path, seq=40, age_ms=5000)      # writer died 5 s ago
    status = probe_camera(tmp_path, feed_path=path)
    assert status.state is ConnectionState.UNAVAILABLE
    assert status.frames_available is False
    assert "berhenti" in status.detail
    assert "camera_depth_live" in status.detail
