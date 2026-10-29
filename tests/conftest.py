"""Shared pytest fixtures.

The dashboard uses a process-wide :class:`RobotRuntime` singleton (Opsi A: the
server owns the runtime, independent of any browser). Tests must not leak state
between each other, so this fixture resets the singleton around every test that
touches the dashboard runtime.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from amr_dashboard import robot_runtime as robot_runtime_module
from amr_dashboard import runtime as runtime_module


@pytest.fixture(autouse=True)
def _reset_dashboard_runtime() -> Iterator[None]:
    """Give every test a fresh, isolated robot runtime and adapter set."""
    runtime_module.reset_runtime()
    robot_runtime_module.reset_adapters()
    yield
    runtime_module.reset_runtime()
    robot_runtime_module.reset_adapters()


@pytest.fixture
def write_feed():
    """Write a depth feed file in the exact format the C++ reader publishes.

    Lives here (not in one test module) so the camera tests and the camera-panel
    tests cannot drift apart on a binary layout: the writer is part of the
    contract, and duplicating it in two files is how a format silently forks.
    Returns a callable ``write(path, **fields) -> payload bytes``.
    """
    import struct
    import time
    from pathlib import Path

    header_fmt = "<IIIIIIIIQQIIII"
    magic = 0x414D5244  # "AMRD"

    def _write(
        path: Path,
        *,
        seq: int = 2,
        width: int = 4,
        height: int = 2,
        pixels: list[int] | None = None,
        age_ms: int = 10,
        frames_total: int = 7,
        magic_value: int = magic,
        running: bool = True,
    ) -> bytes:
        values = pixels if pixels is not None else [100, 200, 300, 400, 0, 0, 500, 600]
        payload = b"".join(struct.pack("<H", v) for v in values)
        host_ms = int(time.monotonic() * 1000) - age_ms
        header = struct.pack(
            header_fmt,
            magic_value, 1, seq, width, height, 2, len(payload), 42,
            1793250000000, host_ms, frames_total, 1 if running else 0, 0, 0,
        )
        assert len(header) == 64
        path.write_bytes(header + payload)
        return payload

    return _write


@pytest.fixture
def write_rgb_feed():
    """Write a colour feed file in the AMRC/NV12 format the C++ reader publishes.

    The payload is built from a real BT.601 YUV conversion of one solid RGB
    colour, so a test can assert that the reader's pixels come out the colour
    they were put in -- and that a grey frame really is grey.
    """
    import struct
    import time
    from pathlib import Path

    header_fmt = "<IIIIIIIIQQIIII"
    magic = 0x43524D41  # "AMRC"

    def _write(
        path: Path,
        *,
        seq: int = 2,
        width: int = 4,
        height: int = 4,
        colour: tuple[int, int, int] = (220, 40, 40),
        age_ms: int = 10,
        frames_total: int = 5,
        magic_value: int = magic,
        payload: bytes | None = None,
    ) -> bytes:
        red, green, blue = colour
        luma = int(0.299 * red + 0.587 * green + 0.114 * blue)
        u = int(-0.169 * red - 0.331 * green + 0.500 * blue + 128)
        v = int(0.500 * red - 0.419 * green - 0.081 * blue + 128)
        u = max(0, min(255, u))
        v = max(0, min(255, v))
        if payload is None:
            y_plane = bytes([luma]) * (width * height)
            chroma = bytearray()
            for _ in range((width // 2) * (height // 2)):
                chroma += bytes([u, v])
            payload = y_plane + bytes(chroma)
        host_ms = int(time.monotonic() * 1000) - age_ms
        header = struct.pack(
            header_fmt,
            magic_value, 1, seq, width, height, 0, len(payload), 3,
            1793250000000, host_ms, frames_total, 1, 0, 0,
        )
        assert len(header) == 64
        path.write_bytes(header + payload)
        return payload

    return _write
