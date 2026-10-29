"""The dashboard's view of the depth feed: statistics and a picture, no SDK.

The camera side lives in ``amr_core.robot.camera`` (stdlib-only, reads the
seqlock header and payload that the C++ reader publishes in
``/dev/shm/amr_camera_depth.bin``). This module turns one frame into something a
panel can show:

* :func:`depth_stats` -- invalid share plus the depth percentiles, in millimetres
  (the SDK's own unit: "depth is measured in mm", SDK User Guide),
* :func:`render_png` / :func:`render_jpeg` -- a picture where near is bright
  (grey palette) or warm (``turbo`` palette) and an invalid pixel (0) is black,
* :func:`frame_rate` -- the frame rate from the writer's own counters, so a
  stalled feed can be told apart from a slow one.

A depth frame is *not* a photograph: every pixel is a distance in millimetres,
so there is exactly one number per pixel and no colour information to recover
(this unit has no colour sensor at all -- ``rgb_pid:0x0`` in the SDK's own device
info). "Colour" here can only be a **false-colour scale** that encodes distance,
which is what the ``turbo`` palette is for. Claiming a colour photo would be a
lie with a picture attached.

Pillow is optional on purpose: without it the panel still shows every number and
says plainly that it cannot draw (never a fake image). No SDK, no device, no
threads -- reading a file cannot move the robot.
"""

from __future__ import annotations

import base64
import io
import struct
import sys
import time
from array import array
from dataclasses import dataclass
from pathlib import Path

from amr_core.robot.camera import (
    DEFAULT_FEED_PATH,
    FRESH_MS,
    DepthHeader,
    read_depth_header,
    read_depth_payload,
)

__all__ = [
    "DEFAULT_RGB_PATH",
    "PALETTES",
    "RgbFrame",
    "DepthFrame",
    "DepthStats",
    "depth_range",
    "depth_stats",
    "frame_rate",
    "rate_from_counters",
    "live_frame",
    "live_rgb_frame",
    "read_rgb_frame",
    "render_rgb_jpeg",
    "rgb_frame_image",
    "read_frame",
    "render_jpeg",
    "render_png",
    "render_png_base64",
]

#: Available scales. ``grey`` shows distance as brightness, ``turbo`` as a warm
#: (near) to cool (far) ramp -- a false-colour scale, not real colour.
PALETTES = ("grey", "turbo")

#: Turbo-like control points: (position, (r, g, b)). Position 0 = far, 1 = near,
#: so warm/red means close and cool/blue means far, which is the reading an
#: operator expects from a depth display.
_TURBO_POINTS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (48, 18, 59)),
    (0.25, (70, 134, 251)),
    (0.50, (27, 229, 181)),
    (0.75, (238, 234, 99)),
    (1.00, (122, 4, 3)),
)


def _turbo_ramp() -> list[tuple[int, int, int]]:
    """The 256 colour steps of the turbo-like ramp (index 0 stays black)."""
    ramp: list[tuple[int, int, int]] = [(0, 0, 0)]  # 0 = invalid pixel
    for index in range(1, 256):
        position = (index - 1) / 254.0
        lower = _TURBO_POINTS[0]
        upper = _TURBO_POINTS[-1]
        for point in _TURBO_POINTS:
            if point[0] <= position:
                lower = point
            if point[0] >= position:
                upper = point
                break
        if upper[0] == lower[0]:
            colour = upper[1]
        else:
            share = (position - lower[0]) / (upper[0] - lower[0])
            colour = tuple(
                int(round(lower[1][channel] + share * (upper[1][channel] - lower[1][channel])))
                for channel in range(3)
            )
        ramp.append(colour)  # type: ignore[arg-type]
    return ramp


@dataclass(frozen=True)
class DepthFrame:
    """One intact depth frame: its header plus the raw little-endian payload."""

    header: DepthHeader
    payload: bytes

    @property
    def width(self) -> int:
        return self.header.width

    @property
    def height(self) -> int:
        return self.header.height

    def pixels(self) -> array:
        """The frame as native-endian uint16 samples."""
        values = array("H")
        values.frombytes(self.payload)
        if sys.byteorder != "little":
            values.byteswap()
        return values


@dataclass(frozen=True)
class DepthStats:
    """What the depth numbers look like, in millimetres."""

    total: int
    invalid: int
    minimum: int
    p10: int
    median: int
    p90: int
    maximum: int

    @property
    def invalid_pct(self) -> float:
        return 100.0 * self.invalid / self.total if self.total else 0.0

    @property
    def valid_pct(self) -> float:
        return 100.0 - self.invalid_pct


def read_frame(path: str | Path = DEFAULT_FEED_PATH) -> DepthFrame | None:
    """The newest intact frame, or None (nothing published, or torn mid-read)."""
    header = read_depth_header(path)
    if header is None:
        return None
    payload = read_depth_payload(header, path)
    if payload is None:
        return None
    return DepthFrame(header=header, payload=payload)


def live_frame(
    path: str | Path = DEFAULT_FEED_PATH,
    max_age_ms: int = FRESH_MS,
) -> DepthFrame | None:
    """A frame only if it is *fresh*: the difference between a feed and a fossil.

    The panel must never draw an old frame under a "live" badge, and the camera
    is a file rather than a port an adapter owns, so freshness has to be checked
    at render time -- a reader that died 40 s ago leaves a perfectly valid file
    behind, with a perfectly valid (and useless) picture in it.
    """
    frame = read_frame(path)
    if frame is None:
        return None
    return frame if frame.header.age_ms <= max_age_ms else None


def depth_stats(frame: DepthFrame, stride: int = 4) -> DepthStats:
    """Percentiles over a strided sample (cheap enough for a 1 Hz refresh).

    ``stride`` counts samples, so the default uses a quarter of the pixels.
    """
    values = frame.pixels()
    step = max(1, stride)
    sample = values[::step]
    valid = sorted(v for v in sample if v)
    total = len(sample)
    if not valid:
        return DepthStats(total=total, invalid=total, minimum=0, p10=0, median=0, p90=0, maximum=0)
    count = len(valid)
    middle = count // 2
    # A true median: with an even count, average the two middle samples. Taking
    # the upper one instead would be a different statistic wearing the same name.
    median = valid[middle] if count % 2 else (valid[middle - 1] + valid[middle]) // 2
    return DepthStats(
        total=total,
        invalid=total - count,
        minimum=valid[0],
        p10=valid[count // 10],
        median=median,
        p90=valid[count * 9 // 10],
        maximum=valid[-1],
    )


def depth_range(frame: DepthFrame, max_samples: int = 4000) -> tuple[int, int]:
    """A robust ``(low, high)`` window in mm for the picture: 5th to 95th pct.

    Percentiles rather than min/max, because one stray pixel at 30 mm would
    otherwise flatten the entire picture into a single shade. The sample size is
    a *count* (not a stride) so a small frame is still sampled properly instead
    of being judged from one pixel.
    """
    values = frame.pixels()
    step = max(1, len(values) // max_samples)
    sample = sorted(v for v in values[::step] if v)
    if not sample:
        return (0, 1)
    low = sample[len(sample) // 20]
    high = sample[len(sample) * 19 // 20]
    return (low, max(high, low + 1))




# --------------------------------------------------------------------------- #
# Colour feed (magic "AMRC", written by tools/camera_reader/camera_rgb_stream)
# --------------------------------------------------------------------------- #

#: Where the colour reader publishes. One process can serve both feeds (kRgb +
#: kDepth) because the camera can only be held once.
DEFAULT_RGB_PATH = "/dev/shm/amr_camera_rgb.bin"
RGB_MAGIC = 0x43524D41  # "AMRC"
RGB_HEADER_FMT = "<IIIIIIIIQQIIII"
RGB_HEADER_BYTES = 64
#: ImageFormat::kJpeg from the SDK. The payload is then already a JPEG and must
#: be served as-is -- re-encoding it would cost CPU and lose quality for nothing.
SDK_FORMAT_JPEG = 9


@dataclass(frozen=True)
class RgbFrame:
    """One intact colour frame: NV12 (nearly always) or a ready-made JPEG."""

    width: int
    height: int
    format: int
    host_ms: int
    frames_total: int
    payload: bytes

    @property
    def age_ms(self) -> int:
        return int(time.monotonic() * 1000) - self.host_ms

    @property
    def is_jpeg(self) -> bool:
        return self.format == SDK_FORMAT_JPEG or self.payload[:2] == b"\xff\xd8"

    @property
    def is_nv12(self) -> bool:
        return len(self.payload) == self.width * self.height * 3 // 2


def read_rgb_frame(path: str | Path = DEFAULT_RGB_PATH) -> RgbFrame | None:
    """The newest intact colour frame, or None (missing, torn, or not ours)."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(RGB_HEADER_BYTES)
            if len(header) < RGB_HEADER_BYTES:
                return None
            fields = struct.unpack(RGB_HEADER_FMT, header)
            magic, _version, seq = fields[0], fields[1], fields[2]
            width, height, fmt, payload_bytes = fields[3], fields[4], fields[5], fields[6]
            host_ms, frames_total = fields[9], fields[10]
            if magic != RGB_MAGIC or seq % 2:
                return None
            if payload_bytes == 0 or payload_bytes > 16 * 1024 * 1024:
                return None
            payload = handle.read(payload_bytes)
            if len(payload) != payload_bytes:
                return None
            # Seqlock: the writer may have started again while we copied.
            handle.seek(8)
            if struct.unpack("<I", handle.read(4))[0] != seq:
                return None
    except OSError:
        return None
    frame = RgbFrame(
        width=width,
        height=height,
        format=fmt,
        host_ms=host_ms,
        frames_total=frames_total,
        payload=payload,
    )
    # Only the two layouts we can actually interpret are accepted. A payload that
    # is neither NV12 nor a JPEG is left alone rather than guessed at -- drawing
    # an unknown layout is how a camera "works" while showing nonsense.
    if not (frame.is_nv12 or frame.is_jpeg):
        return None
    return frame


def live_rgb_frame(
    path: str | Path = DEFAULT_RGB_PATH,
    max_age_ms: int = FRESH_MS,
) -> RgbFrame | None:
    """A colour frame only if it is fresh (same rule as the depth feed)."""
    frame = read_rgb_frame(path)
    if frame is None:
        return None
    return frame if frame.age_ms <= max_age_ms else None


def rgb_frame_image(frame: RgbFrame, max_width: int = 480):
    """A Pillow RGB image of the colour frame, or None (no Pillow / unknown layout).

    NV12 is the layout the vendor's own viewer uses (``COLOR_YUV2BGR_NV12`` when
    ``rows*cols*1.5 == size``): a full-resolution luma plane followed by
    half-resolution interleaved U/V. Pillow has no NV12 decoder, so the chroma is
    de-interleaved by slicing and upsampled -- all C-level, no per-pixel Python.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    if frame.is_jpeg:
        try:
            image = Image.open(io.BytesIO(frame.payload))
            image.load()
            return image.convert("RGB")
        except OSError:
            return None

    if not frame.is_nv12 or frame.width % 2 or frame.height % 2:
        return None

    width, height = frame.width, frame.height
    luma = Image.frombytes("L", (width, height), frame.payload[: width * height])
    chroma = frame.payload[width * height :]
    half = (width // 2, height // 2)
    cb = Image.frombytes("L", half, chroma[0::2]).resize((width, height), Image.BILINEAR)
    cr = Image.frombytes("L", half, chroma[1::2]).resize((width, height), Image.BILINEAR)
    image = Image.merge("YCbCr", (luma, cb, cr)).convert("RGB")

    out_w = min(width, max_width)
    if out_w < width:
        image = image.resize((out_w, max(1, round(height * out_w / width))), Image.BILINEAR)
    return image


def render_rgb_jpeg(frame: RgbFrame, max_width: int = 480, quality: int = 72) -> bytes | None:
    """JPEG of the colour frame, or None without Pillow."""
    if frame.is_jpeg and frame.width <= max_width:
        return frame.payload
    image = rgb_frame_image(frame, max_width=max_width)
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def rate_from_counters(
    previous: tuple[int, int] | None,
    frames_total: int,
    host_ms: int,
) -> float | None:
    """Frames/s from a writer's counters, shared by both feeds (see frame_rate)."""
    if previous is None:
        return None
    prev_frames, prev_host_ms = previous
    frame_delta = frames_total - prev_frames
    time_delta = host_ms - prev_host_ms
    if frame_delta <= 0 or time_delta <= 0:
        return None
    return frame_delta * 1000.0 / time_delta


def frame_rate(
    previous: tuple[int, int] | None,
    header: DepthHeader,
) -> float | None:
    """Frames/s from the writer's own counters, or None without a usable baseline.

    ``previous`` is ``(frames_total, host_ms)`` as captured by the caller on its
    last render. Two reasons it must not use the sequence number: the writer
    restarts ``seq`` from zero every run (so a restarted reader looks like a wild
    negative delta), and the render interval is not the frame interval. The
    writer's ``frames_total`` and the receiver-clock stamp it publishes give the
    real rate.

    A stalled feed, or a writer that restarted between the two renders, returns
    None rather than a made-up number.
    """
    return rate_from_counters(previous, header.frames_total, header.host_ms)


def _luts(low: int, high: int, palette: str) -> tuple[list[int], list[list[int]] | None]:
    """Colour look-up tables for a frame: (index lut, per-channel luts or None).

    The depth values are 16-bit, so the LUT has 65536 entries and Pillow applies
    it in C -- a per-pixel Python loop would not keep up with a live preview.
    The index LUT quantises depth into 0..255 (0 reserved for "no data").
    """
    span = max(1, high - low)
    # Only the window that is actually visible needs computing: everything above
    # `high + span` clamps to the darkest step anyway. A live preview builds this
    # table 15 times a second, so the work is kept to ~2*span entries instead of
    # the full 65536.
    ceiling = min(65536, high + span + 1)
    index_lut = (
        [0] * min(low, 65536)
        + [max(1, 255 - (254 * (value - low)) // span) for value in range(low, ceiling)]
        + [1] * max(0, 65536 - ceiling)
    )
    if palette == "grey":  # brightness: index IS the colour
        return index_lut, None

    ramp = _turbo_ramp()
    channels = [[ramp[index][channel] for index in range(256)] for channel in range(3)]
    return index_lut, channels


def render_image(
    frame: DepthFrame,
    max_width: int = 320,
    palette: str = "grey",
):
    """A Pillow image of the frame, or None when Pillow is not installed.

    Downscaling uses ``resize(NEAREST)`` on the full frame, so the picture keeps
    the sensor's aspect ratio instead of drifting when the stride does not divide
    the width. Nothing here invents data: an invalid pixel stays black, and a
    palette that is not known falls back to grey rather than guessing.
    """
    try:
        from PIL import Image
    except ImportError:  # Pillow is an optional extra for this dashboard
        return None

    width, height = frame.width, frame.height
    if width <= 0 or height <= 0 or len(frame.payload) < width * height * 2:
        return None
    if sys.byteorder != "little":  # Pillow reads the buffer as little-endian
        payload = array("H", frame.pixels())
        payload.byteswap()
        raw = payload.tobytes()
    else:
        raw = frame.payload

    low, high = depth_range(frame)
    index_lut, channels = _luts(low, high, palette if palette in PALETTES else "grey")

    # Pillow will not apply a 65536-entry table to an "I;16" image directly
    # ("wrong number of lut entries"); "I" is the mode it does accept.
    depth = Image.frombytes("I;16", (width, height), raw).convert("I")

    # Shrink before the colour work: the table and the channel merge then run on
    # a quarter of the pixels, which is what keeps a live preview cheap.
    out_w = min(width, max_width)
    out_h = max(1, round(height * out_w / width))
    if (out_w, out_h) != (width, height):
        depth = depth.resize((out_w, out_h), Image.NEAREST)

    index = depth.point(index_lut, "L")
    if channels is None:
        return index
    return Image.merge(
        "RGB",
        tuple(index.point(channel_lut, "L") for channel_lut in channels),
    )


def render_png(frame: DepthFrame, max_width: int = 320, palette: str = "grey") -> bytes | None:
    """A PNG of the frame, or None without Pillow."""
    image = render_image(frame, max_width=max_width, palette=palette)
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_jpeg(
    frame: DepthFrame,
    max_width: int = 320,
    palette: str = "turbo",
    quality: int = 70,
) -> bytes | None:
    """A JPEG of the frame, or None without Pillow.

    JPEG because a live preview sends 10-15 of these per second: a PNG of the
    same picture costs several times the bytes, and the wire is the bottleneck on
    a shared USB/Wi-Fi link.
    """
    image = render_image(frame, max_width=max_width, palette=palette)
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def render_png_base64(frame: DepthFrame, max_width: int = 320, palette: str = "grey") -> str | None:
    """The same PNG as a data-URI body, for a NiceGUI/HTML ``<img>``."""
    raw = render_png(frame, max_width, palette)
    if raw is None:
        return None
    return base64.b64encode(raw).decode("ascii")
