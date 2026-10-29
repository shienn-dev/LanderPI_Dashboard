"""Tests for the live depth preview (MJPEG) -- no camera, no HTTP, no hardware.

The stream exists because a picture rebuilt once per page tick looks like a
slide show. These tests pin the parts that make it a *stream* rather than a
fast slideshow:

* a new frame produces exactly one MJPEG part, with a valid JPEG inside,
* the same frame is never sent twice (so the picture cannot be newer than the
  numbers, and a stopped reader cannot look live),
* a stale feed yields nothing at all, and the bounded generator ends instead of
  spinning forever,
* the false-colour scale encodes distance (near warm, far cool) and keeps an
  invalid pixel black -- a depth map is one number per pixel, never a photo.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pytest

from amr_dashboard import camera_feed, camera_stream

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402  (import after the skip guard, deliberately)


def collect(chunks, limit: int = 1) -> list[bytes]:
    """Take at most ``limit`` chunks (the generator is endless by design)."""
    taken: list[bytes] = []
    for chunk in chunks:
        taken.append(chunk)
        if len(taken) >= limit:
            break
    return taken


def test_a_new_frame_becomes_one_mjpeg_part(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "hidup.bin"
    write_feed(path, seq=2, width=4, height=2, frames_total=10, age_ms=5)

    chunks = collect(
        camera_stream.mjpeg_chunks(path, source="depth", max_width=4, max_frames=1), limit=1
    )
    assert len(chunks) == 1
    part = chunks[0]
    assert part.startswith(b"--" + camera_stream.BOUNDARY.encode())
    assert b"Content-Type: image/jpeg" in part
    payload = part.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n")
    assert payload[:3] == b"\xff\xd8\xff"          # JPEG start of image
    assert payload[-2:] == b"\xff\xd9"             # JPEG end of image
    image = Image.open(io.BytesIO(payload))
    assert image.size == (4, 2)


def test_the_same_frame_is_never_sent_twice(tmp_path: Path, write_feed) -> None:
    """One frame, one part: the picture can't drift ahead of the numbers."""
    path = tmp_path / "satu.bin"
    write_feed(path, frames_total=7, age_ms=5)
    # A short window with no new frame must yield exactly one part, then end.
    chunks = collect(
        camera_stream.mjpeg_chunks(path, source="depth", max_width=4, run_for_s=0.25), limit=99
    )
    assert len(chunks) == 1


def test_a_stale_feed_sends_nothing(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "basi.bin"
    write_feed(path, frames_total=3, age_ms=9000)
    assert collect(camera_stream.mjpeg_chunks(path, source="depth", run_for_s=0.2), limit=99) == []
    assert camera_stream.snapshot_jpeg(path, source="depth") is None


def test_a_missing_feed_sends_nothing_and_does_not_raise(tmp_path: Path) -> None:
    missing = tmp_path / "tidak-ada.bin"
    chunks = camera_stream.mjpeg_chunks(missing, source="depth", run_for_s=0.2)
    assert collect(chunks, limit=99) == []


def test_the_frame_cap_bounds_the_stream(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "batas.bin"
    write_feed(path, frames_total=5, age_ms=5)
    chunks = list(camera_stream.mjpeg_chunks(path, source="depth", max_width=4, max_frames=1))
    assert len(chunks) == 1


def test_a_snapshot_is_a_jpeg_of_the_newest_frame(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "jepret.bin"
    write_feed(path, width=4, height=2, age_ms=5)
    data = camera_stream.snapshot_jpeg(path, source="depth", max_width=4)
    assert data is not None
    assert data[:3] == b"\xff\xd8\xff"
    assert Image.open(io.BytesIO(data)).size == (4, 2)


def test_the_colour_scale_encodes_distance(tmp_path: Path, write_feed) -> None:
    """turbo: near is warm (red-ish), far is cool (blue-ish), no data is black."""
    path = tmp_path / "warna.bin"
    write_feed(path, width=3, height=1, pixels=[0, 400, 3000], age_ms=5)
    frame = camera_feed.read_frame(path)
    assert frame is not None

    image = camera_feed.render_image(frame, max_width=3, palette="turbo")
    assert image is not None and image.mode == "RGB"
    near = image.getpixel((1, 0))
    far = image.getpixel((2, 0))
    assert image.getpixel((0, 0)) == (0, 0, 0)      # invalid stays black
    assert near != far
    assert near[0] > near[2]                        # near leans red
    assert far[2] > far[0]                          # far leans blue


def test_the_grey_scale_shows_near_as_bright(tmp_path: Path, write_feed) -> None:
    path = tmp_path / "abu.bin"
    write_feed(path, width=3, height=1, pixels=[0, 400, 3000], age_ms=5)
    frame = camera_feed.read_frame(path)
    assert frame is not None
    image = camera_feed.render_image(frame, max_width=3, palette="grey")
    assert image is not None and image.mode == "L"
    assert image.getpixel((0, 0)) == 0
    assert image.getpixel((1, 0)) > image.getpixel((2, 0))


def test_an_unknown_palette_falls_back_to_grey(tmp_path: Path, write_feed) -> None:
    """No guessing: an unknown scale draws the neutral one, never a random one."""
    path = tmp_path / "skala.bin"
    write_feed(path, width=2, height=1, pixels=[400, 3000], age_ms=5)
    frame = camera_feed.read_frame(path)
    assert frame is not None
    image = camera_feed.render_image(frame, max_width=2, palette="pelangi-palsu")
    assert image is not None and image.mode == "L"


def test_the_preview_keeps_the_frame_aspect_ratio(tmp_path: Path, write_feed) -> None:
    """640x400 at max_width 320 must be 320x200, not 320x199 or 320x201."""
    path = tmp_path / "rasio.bin"
    write_feed(path, width=640, height=400, pixels=[1000] * (640 * 400), age_ms=5)
    frame = camera_feed.read_frame(path)
    assert frame is not None
    image = camera_feed.render_image(frame, max_width=320, palette="turbo")
    assert image is not None
    assert image.size == (320, 200)


def test_rendering_is_fast_enough_for_a_live_preview(tmp_path: Path, write_feed) -> None:
    """15 fps means a 66 ms budget per frame; measure, do not assume.

    The camera's own limit is 15 fps (SDK User Guide 5.2.12), so encoding one
    640x400 frame must stay well inside that or the preview falls behind the
    sensor and looks stuttery again.
    """
    path = tmp_path / "laju.bin"
    write_feed(path, width=640, height=400, pixels=[800] * (640 * 400), age_ms=5)
    frame = camera_feed.read_frame(path)
    assert frame is not None

    started = time.monotonic()
    rounds = 5
    for _ in range(rounds):
        assert camera_feed.render_jpeg(frame, max_width=320, palette="turbo") is not None
    per_frame_ms = (time.monotonic() - started) * 1000 / rounds
    assert per_frame_ms < 66.0, f"{per_frame_ms:.1f} ms per frame is over the 15 fps budget"


# --------------------------------------------------------------------------- #
# Feed warna (AMRC / NV12)
# --------------------------------------------------------------------------- #


def test_a_colour_frame_reads_back_as_its_own_colour(tmp_path: Path, write_rgb_feed) -> None:
    """The stream carries real chroma: a red frame must come out red."""
    path = tmp_path / "warna.bin"
    write_rgb_feed(path, width=8, height=8, colour=(220, 30, 30), age_ms=5)
    frame = camera_feed.read_rgb_frame(path)
    assert frame is not None
    assert (frame.width, frame.height) == (8, 8)
    assert frame.is_nv12
    assert frame.age_ms < 1000

    image = camera_feed.rgb_frame_image(frame, max_width=8)
    assert image is not None
    red, green, blue = image.getpixel((4, 4))
    assert red > 150 and green < 120 and blue < 120, (red, green, blue)
    assert frame.frames_total == 5


def test_a_grey_scene_stays_grey(tmp_path: Path, write_rgb_feed) -> None:
    """Sanity check the other way: no chroma in, no colour out."""
    path = tmp_path / "abu.bin"
    write_rgb_feed(path, width=8, height=8, colour=(128, 128, 128), age_ms=5)
    frame = camera_feed.read_rgb_frame(path)
    assert frame is not None
    image = camera_feed.rgb_frame_image(frame, max_width=8)
    assert image is not None
    red, green, blue = image.getpixel((4, 4))
    assert max(red, green, blue) - min(red, green, blue) <= 6


def test_a_colour_frame_survives_a_restarted_writer(tmp_path: Path, write_rgb_feed) -> None:
    """A foreign magic, a torn frame or a truncated payload must be refused."""
    path = tmp_path / "rusak.bin"
    write_rgb_feed(path, magic_value=0xDEADBEEF)
    assert camera_feed.read_rgb_frame(path) is None

    write_rgb_feed(path, seq=3)                       # odd = writer mid-copy
    assert camera_feed.read_rgb_frame(path) is None

    write_rgb_feed(path, payload=b"\x00\x10")        # too short for its header
    assert camera_feed.read_rgb_frame(path) is None


def test_a_stale_colour_frame_is_not_live(tmp_path: Path, write_rgb_feed) -> None:
    path = tmp_path / "basi.bin"
    write_rgb_feed(path, age_ms=8000)
    assert camera_feed.read_rgb_frame(path) is not None
    assert camera_feed.live_rgb_frame(path) is None


def test_the_colour_stream_yields_jpeg_parts(tmp_path: Path, write_rgb_feed) -> None:
    path = tmp_path / "alir.bin"
    write_rgb_feed(path, width=8, height=8, age_ms=5)
    chunks = collect(
        camera_stream.mjpeg_chunks(path, source="rgb", max_width=8, max_frames=1), limit=1
    )
    assert len(chunks) == 1
    payload = chunks[0].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n")
    assert payload[:3] == b"\xff\xd8\xff"
    image = Image.open(io.BytesIO(payload))
    assert image.mode == "RGB"
    red, green, blue = image.getpixel((4, 4))
    assert red > 150 and green < 120, (red, green, blue)


def test_a_ready_made_jpeg_payload_is_served_untouched(tmp_path: Path) -> None:
    """If the SDK ever hands us a JPEG, re-encoding it would be waste."""
    import struct
    import time

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (10, 200, 30)).save(buffer, format="JPEG", quality=80)
    jpeg = buffer.getvalue()
    header = struct.pack(
        camera_feed.RGB_HEADER_FMT,
        camera_feed.RGB_MAGIC, 1, 2, 16, 16, camera_feed.SDK_FORMAT_JPEG, len(jpeg), 1,
        0, int(time.monotonic() * 1000) - 5, 1, 1, 0, 0,
    )
    path = tmp_path / "jpeg.bin"
    path.write_bytes(header + jpeg)

    frame = camera_feed.read_rgb_frame(path)
    assert frame is not None and frame.is_jpeg
    assert camera_feed.render_rgb_jpeg(frame) == jpeg


def test_the_colour_preview_is_fast_enough(tmp_path: Path, write_rgb_feed) -> None:
    """480x300 colour frames at ~10 fps: the same 100 ms budget applies."""
    path = tmp_path / "laju_warna.bin"
    write_rgb_feed(path, width=480, height=300, age_ms=5)
    frame = camera_feed.read_rgb_frame(path)
    assert frame is not None

    started = time.monotonic()
    rounds = 3
    for _ in range(rounds):
        assert camera_feed.render_rgb_jpeg(frame) is not None
    per_frame_ms = (time.monotonic() - started) * 1000 / rounds
    assert per_frame_ms < 100.0, f"{per_frame_ms:.1f} ms per frame"
