"""Camera availability probe, and a stdlib-only reader for the depth feed.

The robot's camera is a **Deptrum Aurora 930 depth camera** (USB ``3251:1930``,
structured light). It has **no kernel driver bound** and exposes **no**
``/dev/video`` node, so it is not a UVC camera and standard Linux video tooling
cannot read it: frames come from the vendor's Deptrum SDK.

Since 2026-10-29 the SDK is installed and working, and frames are produced by a
small C++ helper (``~/AMRTestLander/tools/camera_reader/camera_depth_stream``,
built against the vendor SDK) which keeps the newest depth frame in a
**seqlock file** -- by default ``/dev/shm/amr_camera_depth.bin``, i.e. RAM, so
frames never wear the SD card. This module knows that file's layout:

    offset 0   64-byte header:
               magic u32 ("AMRD"), version u32, seq u32, width u32,
               height u32, bytes_per_pixel u32, payload_bytes u32, frame_index u32,
               timestamp_ms u64 (device), host_ms u64 (receiver steady clock),
               frames_total u32, flags u32 (bit0 = writer running), reserved 2*u32
    offset 64  payload, width*height*bytes_per_pixel

The writer makes ``seq`` odd while copying and even again when the payload is
complete, so a reader that sees the same even ``seq`` before and after its own
copy knows the frame is intact (this module does the cheap version: it reads the
header, then the payload, then the header again).

Everything here is **read-only over a file**: no device is opened, no SDK is
linked, and no frame is ever fabricated. This module stays stdlib-only, so
``amr_core`` keeps importing without Pillow; rendering a picture is the
dashboard's job (:mod:`amr_dashboard.camera_feed`).
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from pathlib import Path

from amr_core.robot.interfaces import CameraStatus, ConnectionState

AURORA930_VID = "3251"
AURORA930_PID = "1930"

#: Where the depth reader publishes frames (see the module docstring).
DEFAULT_FEED_PATH = "/dev/shm/amr_camera_depth.bin"

#: A frame older than this is not a live feed any more.
FRESH_MS = 1500

#: Pi-internal video nodes that are NOT cameras (ISP backend / H.264 codec).
_NON_CAMERA_NODE_PREFIXES = ("pispbe", "rpivid")

_MAGIC = 0x414D5244  # "AMRD"
_HEADER_BYTES = 64
_HEADER_FMT = "<IIIIIIIIQQIIII"
_MAX_W, _MAX_H = 640, 400


@dataclass(frozen=True)
class DepthHeader:
    """The header of one published depth frame (no payload)."""

    seq: int
    width: int
    height: int
    bytes_per_pixel: int
    payload_bytes: int
    frame_index: int
    timestamp_ms: int
    host_ms: int
    frames_total: int
    running: bool

    @property
    def age_ms(self) -> int:
        """How long ago the writer published this frame, in ms."""
        return max(0, _now_ms() - self.host_ms)


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def read_depth_header(
    path: str | Path = DEFAULT_FEED_PATH, attempts: int = 3
) -> DepthHeader | None:
    """Header of the newest intact frame, or None (no file, empty, mid-write)."""
    feed = Path(path)
    try:
        with feed.open("rb") as handle:
            for _ in range(max(1, attempts)):
                handle.seek(0)
                raw = handle.read(_HEADER_BYTES)
                if len(raw) < _HEADER_BYTES:
                    return None
                (magic, _version, seq, width, height, bpp, payload,
                 index, ts, host_ms, total, flags, _r0, _r1) = struct.unpack(_HEADER_FMT, raw)
                if magic != _MAGIC or seq == 0:
                    return None
                if seq % 2 == 1:            # writer is mid-copy: retry
                    continue
                if not (0 < width <= _MAX_W and 0 < height <= _MAX_H and payload > 0):
                    return None
                handle.seek(0)
                again = handle.read(_HEADER_BYTES)
                if len(again) < _HEADER_BYTES:
                    return None
                if struct.unpack(_HEADER_FMT, again)[2] != seq:   # torn: retry
                    continue
                return DepthHeader(
                    seq=seq, width=width, height=height, bytes_per_pixel=bpp,
                    payload_bytes=payload, frame_index=index, timestamp_ms=ts,
                    host_ms=host_ms, frames_total=total, running=bool(flags & 1),
                )
    except OSError:
        return None
    return None


def read_depth_payload(header: DepthHeader, path: str | Path = DEFAULT_FEED_PATH) -> bytes | None:
    """The raw depth payload for ``header``, re-checking ``seq`` afterwards.

    Returns None when the writer overwrote the slot while we were copying --
    callers should simply try again on the next tick instead of showing a torn
    frame.
    """
    feed = Path(path)
    try:
        with feed.open("rb") as handle:
            handle.seek(0)
            before = handle.read(_HEADER_BYTES)
            if len(before) < _HEADER_BYTES:
                return None
            payload = handle.read(header.payload_bytes)
            handle.seek(0)
            after = handle.read(_HEADER_BYTES)
    except OSError:
        return None
    if len(payload) != header.payload_bytes:
        return None
    if struct.unpack(_HEADER_FMT, before)[2] != header.seq:
        return None
    if struct.unpack(_HEADER_FMT, after)[2] != header.seq:
        return None
    return payload


def _uvc_nodes(sysfs: Path) -> list[str]:
    """Return non-internal ``/dev/video*`` nodes (candidate UVC cameras)."""
    base = sysfs / "class" / "video4linux"
    found: list[str] = []
    if not base.is_dir():
        return found
    for node in sorted(base.iterdir()):
        try:
            name = (node / "name").read_text().strip()
        except OSError:
            continue
        if any(name.startswith(prefix) for prefix in _NON_CAMERA_NODE_PREFIXES):
            continue
        found.append(f"/dev/{node.name} ({name})")
    return found


def _usb_present(sysfs: Path, vid: str, pid: str) -> bool:
    """True if a USB device with the given vendor/product id is present."""
    base = sysfs / "bus" / "usb" / "devices"
    if not base.is_dir():
        return False
    for device in base.iterdir():
        vendor_file = device / "idVendor"
        product_file = device / "idProduct"
        try:
            if vendor_file.read_text().strip() == vid and product_file.read_text().strip() == pid:
                return True
        except OSError:
            continue
    return False


def probe_camera(
    sysfs: Path | str = "/sys",
    feed_path: str | Path = DEFAULT_FEED_PATH,
) -> CameraStatus:
    """Read-only camera availability probe. Never opens a device, never guesses.

    Order matters: a *live* depth feed is the only state that may claim frames.
    A camera on USB with no reader running is reported as unavailable and the
    detail names the launcher, because "the hardware is there" is not "you can
    see a picture".
    """
    sysfs = Path(sysfs)
    header = read_depth_header(feed_path)

    if header is not None and header.age_ms <= FRESH_MS:
        return CameraStatus(
            state=ConnectionState.CONNECTED,
            kind="depth",
            device=f"usb {AURORA930_VID}:{AURORA930_PID} (Aurora 930)",
            detail=(
                f"depth {header.width}x{header.height} uint16 mm, frame terakhir "
                f"{header.age_ms} ms lalu, {header.frames_total} frame sejak pembaca jalan "
                f"({feed_path})"
            ),
            frames_available=True,
        )

    if header is not None:
        return CameraStatus(
            state=ConnectionState.UNAVAILABLE,
            kind="depth",
            device=f"usb {AURORA930_VID}:{AURORA930_PID} (Aurora 930)",
            detail=(
                f"pembaca frame berhenti: frame terakhir {header.age_ms} ms lalu "
                f"(seq {header.seq}, {header.frames_total} frame total). "
                f"Jalankan ulang: ~/camera_depth_live.sh"
            ),
            frames_available=False,
        )

    uvc = _uvc_nodes(sysfs)
    if uvc:
        return CameraStatus(
            state=ConnectionState.UNAVAILABLE,
            kind="usb",
            device=uvc[0],
            detail=(
                f"UVC video node(s) present ({', '.join(uvc)}), but no streaming backend "
                "is wired up in this phase."
            ),
            frames_available=False,
        )

    if _usb_present(sysfs, AURORA930_VID, AURORA930_PID):
        return CameraStatus(
            state=ConnectionState.UNAVAILABLE,
            kind="depth",
            device=f"usb {AURORA930_VID}:{AURORA930_PID}",
            detail=(
                "Deptrum Aurora 930 terdeteksi di USB (SDK vendor sudah terpasang, "
                f"aturan udev terpasang), tetapi belum ada frame di {feed_path}: "
                "pembaca frame belum dijalankan. Jalankan ~/camera_depth_live.sh — "
                "lihat docs/sesi_8.md §11-§12."
            ),
            frames_available=False,
        )

    return CameraStatus(
        state=ConnectionState.UNAVAILABLE,
        kind="none",
        device="-",
        detail=(
            "No camera detected: no UVC /dev/video node and no known depth camera "
            "on USB."
        ),
        frames_available=False,
    )
