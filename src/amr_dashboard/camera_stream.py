"""Live preview of the depth feed: an MJPEG stream the browser shows continuously.

Why a stream instead of "a picture per page refresh": the panel used to rebuild an
``<img>`` with a fresh PNG once per second, which looked like a slide show --
capture, transfer, decode, one second of nothing, repeat. The camera produces
~15 frames/s, so the honest thing is to hand the browser a stream and let it draw
whatever arrives. ``multipart/x-mixed-replace`` is the sixty-year-old trick that
does this with no JavaScript: one HTTP response, many images, the browser keeps
the last one on screen.

Two things this module is careful about, both learned by measuring:

* **One encode per frame, not one per viewer.** Every viewer used to encode its
  own JPEG of the same frame; with a browser tab *and* a probe open, the Pi spent
  a full core on duplicate work and both viewers dropped to ~5 fps. The newest
  encoded picture is cached and shared, so adding a viewer costs a copy, not a
  JPEG.
* **Pace to a deadline, not "sleep after the work".** Sleeping a fixed 1/15 s
  after each encode caps the stream at 1/(encode + 1/15) -- about 11 fps for a
  15 fps camera. The pacer now sends the next frame when it is actually due.

Nothing here is invented: only *new* frames are sent (deduped on the writer's own
frame counter), a stale feed sends nothing at all rather than repeating an old
picture, and if Pillow is missing the stream refuses to start instead of showing
a placeholder.

A depth frame is one distance per pixel, so the "colour" is a false-colour scale,
never a real photo -- see :mod:`amr_dashboard.camera_feed`.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from amr_dashboard import camera_feed

__all__ = [
    "BOUNDARY",
    "DEFAULT_SOURCE",
    "DEFAULT_FPS_CAP",
    "DEFAULT_MAX_WIDTH",
    "DEFAULT_QUALITY",
    "DEFAULT_PALETTE",
    "encode_jpeg",
    "encode_rgb_jpeg",
    "mjpeg_chunks",
    "pillow_available",
    "snapshot_jpeg",
    "SOURCES",
]

#: Multipart boundary string. Kept ASCII and free of regex metacharacters.
BOUNDARY = "amrdepthframe"

DEFAULT_PALETTE = "turbo"
#: Which feed the preview shows. ``rgb`` is the camera's ordinary colour image;
#: ``depth`` is the distance map with a false-colour scale. Both can be live at
#: once -- one reader process publishes both files.
DEFAULT_SOURCE = "rgb"
SOURCES = ("rgb", "depth")
DEFAULT_MAX_WIDTH = 320
#: The colour sensor delivers 480x300; sending it larger only costs bandwidth.
DEFAULT_RGB_MAX_WIDTH = 640
DEFAULT_RGB_QUALITY = 72
DEFAULT_QUALITY = 70
#: The camera supports 15 fps at most (SDK User Guide 5.2.12); asking the stream
#: for more would only duplicate work.
DEFAULT_FPS_CAP = 15.0
#: How long to wait between checks when no new frame has arrived.
IDLE_POLL_S = 0.02

#: The last picture we encoded, keyed by *which* frame and how it was drawn.
#: One entry is enough: every viewer asks for the newest frame, and an older one
#: is never wanted twice. ``host_ms`` is part of the key so a restarted reader
#: (which resets its frame counter) can never hit a stale entry.
_ENCODE_LOCK = threading.Lock()
_ENCODE_CACHE: dict[tuple[int, int, str, int, int], bytes] = {}


def pillow_available() -> bool:
    """True when Pillow can be imported (it is only needed to draw)."""
    return importlib.util.find_spec("PIL") is not None


def encode_jpeg(
    frame: camera_feed.DepthFrame,
    *,
    max_width: int = DEFAULT_MAX_WIDTH,
    palette: str = DEFAULT_PALETTE,
    quality: int = DEFAULT_QUALITY,
) -> bytes | None:
    """JPEG of ``frame``, shared between viewers (None when Pillow is missing).

    The cache is what keeps a second viewer from doubling the CPU: the picture of
    a given frame is identical for everyone asking for the same scale.
    """
    key = (frame.header.host_ms, frame.header.frames_total, palette, max_width, quality)
    with _ENCODE_LOCK:
        cached = _ENCODE_CACHE.get(key)
    if cached is not None:
        return cached

    encoded = camera_feed.render_jpeg(frame, max_width=max_width, palette=palette, quality=quality)
    if encoded is not None:
        with _ENCODE_LOCK:
            _ENCODE_CACHE.clear()  # only the newest frame is ever asked for again
            _ENCODE_CACHE[key] = encoded
    return encoded


def encode_rgb_jpeg(
    frame: camera_feed.RgbFrame,
    *,
    max_width: int = DEFAULT_RGB_MAX_WIDTH,
    quality: int = DEFAULT_RGB_QUALITY,
) -> bytes | None:
    """JPEG of a colour frame, shared between viewers (None without Pillow)."""
    key = (frame.host_ms, frame.frames_total, "rgb", max_width, quality)
    with _ENCODE_LOCK:
        cached = _ENCODE_CACHE.get(key)
    if cached is not None:
        return cached

    encoded = camera_feed.render_rgb_jpeg(frame, max_width=max_width, quality=quality)
    if encoded is not None:
        with _ENCODE_LOCK:
            _ENCODE_CACHE.clear()
            _ENCODE_CACHE[key] = encoded
    return encoded


def snapshot_jpeg(
    path: str | Path | None = None,
    *,
    source: str = DEFAULT_SOURCE,
    max_width: int | None = None,
    palette: str = DEFAULT_PALETTE,
    quality: int | None = None,
) -> bytes | None:
    """One JPEG of the newest fresh frame of ``source``, or None.

    ``source="rgb"`` is the ordinary camera image, ``source="depth"`` the distance
    map. ``path`` overrides where the feed is read from (tests use it).
    """
    if source == "rgb":
        frame = camera_feed.live_rgb_frame(path or camera_feed.DEFAULT_RGB_PATH)
        if frame is None:
            return None
        return encode_rgb_jpeg(
            frame,
            max_width=max_width or DEFAULT_RGB_MAX_WIDTH,
            quality=quality or DEFAULT_RGB_QUALITY,
        )
    depth_frame = camera_feed.live_frame(path or camera_feed.DEFAULT_FEED_PATH)
    if depth_frame is None:
        return None
    return encode_jpeg(
        depth_frame,
        max_width=max_width or DEFAULT_MAX_WIDTH,
        palette=palette,
        quality=quality or DEFAULT_QUALITY,
    )


def _next_picture(
    source: str,
    path: str | Path | None,
    last_key: int | None,
    *,
    max_width: int | None,
    palette: str,
    quality: int | None,
) -> tuple[int, bytes] | None:
    """The newest not-yet-sent picture of ``source``, or None if there is none."""
    if source == "rgb":
        frame = camera_feed.live_rgb_frame(path or camera_feed.DEFAULT_RGB_PATH)
        if frame is None or frame.frames_total == last_key:
            return None
        jpeg = encode_rgb_jpeg(
            frame,
            max_width=max_width or DEFAULT_RGB_MAX_WIDTH,
            quality=quality or DEFAULT_RGB_QUALITY,
        )
        return None if jpeg is None else (frame.frames_total, jpeg)

    depth = camera_feed.live_frame(path or camera_feed.DEFAULT_FEED_PATH)
    if depth is None or depth.header.frames_total == last_key:
        return None
    jpeg = encode_jpeg(
        depth,
        max_width=max_width or DEFAULT_MAX_WIDTH,
        palette=palette,
        quality=quality or DEFAULT_QUALITY,
    )
    return None if jpeg is None else (depth.header.frames_total, jpeg)


def mjpeg_chunks(
    path: str | Path | None = None,
    *,
    source: str = DEFAULT_SOURCE,
    max_width: int | None = None,
    palette: str = DEFAULT_PALETTE,
    quality: int | None = None,
    fps_cap: float = DEFAULT_FPS_CAP,
    idle_poll_s: float = IDLE_POLL_S,
    run_for_s: float | None = None,
    max_frames: int | None = None,
) -> Iterator[bytes]:
    """Yield MJPEG parts, one per new frame of ``source``, forever or bounded.

    ``source="rgb"`` streams the camera's ordinary colour image; ``"depth"`` the
    distance map. ``run_for_s`` and ``max_frames`` bound the generator so it can
    be tested and so a caller can ask for a short burst; in normal use both are
    None and the generator ends when the client disconnects.

    A frame is resent only when its writer's counter moved, so the picture can
    never be newer than the numbers beside it, and a stopped reader shows a
    frozen last frame instead of a stream that pretends to be live.
    """
    if not pillow_available():
        return
    interval = 1.0 / fps_cap if fps_cap > 0 else 0.0
    deadline = None if run_for_s is None else time.monotonic() + run_for_s
    sent = 0
    last_key: int | None = None
    next_at = time.monotonic()

    while True:
        if deadline is not None and time.monotonic() >= deadline:
            return
        if max_frames is not None and sent >= max_frames:
            return

        picture = _next_picture(
            source,
            path,
            last_key,
            max_width=max_width,
            palette=palette,
            quality=quality,
        )
        if picture is None:
            time.sleep(idle_poll_s)
            continue

        last_key, jpeg = picture
        sent += 1
        yield (
            b"--" + BOUNDARY.encode("ascii") + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
            + jpeg
            + b"\r\n"
        )
        if interval:
            # Pace against a deadline so the encode time comes out of the
            # interval instead of being added to it.
            next_at = max(next_at + interval, time.monotonic())
            delay = next_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
