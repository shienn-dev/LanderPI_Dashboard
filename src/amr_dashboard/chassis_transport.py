"""Opening the STM32 chassis port (the only place that touches pyserial).

``amr_core.robot`` is deliberately free of device imports -- there is a guard
test for it (``tests/test_robot_no_actuation.py``) and the reason is sound:
the safety-critical robot package must be importable, testable and auditable
without a serial stack. The device therefore lives here, in the layer that
owns the process lifecycle.

The details that matter and are easy to get wrong:

* **DTR and RTS are lowered before ``open()``.** That was shown not to reset
  the STM32 on this board (sesi 2 §9.1). Opening with the default line states
  can reboot the controller.
* **The baud rate is 1 Mbaud**, the value the stock Hiwonder SDK uses even
  though the device is USB CDC-ACM. Keeping it identical to the SDK avoids
  introducing a second variable.
* **The import is late.** Importing this module never imports pyserial, so the
  dashboard still starts on a machine without it.
"""

from __future__ import annotations

import os
from pathlib import Path

from amr_core.robot.serial_chassis import SerialPort

DEFAULT_BAUD = 1_000_000


def is_pty(port: str) -> bool:
    """True for a pseudo-terminal path -- which is never the robot's board.

    The holder check below exists because two writers on one USB CDC device
    interleave motor frames. A PTY is different by construction: its master is
    held by whoever answers the frames, so the check would always fire on the
    fake-board harness (``tools/fake_board_pty.py``) whose entire purpose is to
    answer without touching hardware. Exempting /dev/pts keeps the guard exactly
    as strict as it was for real devices.
    """
    return os.path.realpath(port).startswith("/dev/pts/")


def other_processes_holding(port: str) -> list[int]:
    """Return the PIDs that already have ``port`` open.

    A USB CDC device does not enforce exclusive access, so two processes can
    both open ``/dev/ttyACM0`` and then interleave motor frames on the wire.
    That is how a robot ends up doing something nobody asked for, so the
    dashboard refuses to start when somebody else already holds the port.

    Best effort: it reads ``/proc`` and needs permission to look at the other
    processes' file descriptors.
    """
    target = os.path.realpath(port)
    if is_pty(port):
        return []
    holders: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return holders
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        try:
            for descriptor in (entry / "fd").iterdir():
                if os.path.realpath(descriptor) == target:
                    holders.append(pid)
                    break
        except (OSError, PermissionError):
            continue
    return holders


def open_serial_port(port: str, baud: int = DEFAULT_BAUD) -> SerialPort:
    """Open the board's serial port, ready to accept motor frames."""
    # Check the port before importing pyserial: if somebody else holds it, we
    # refuse without touching the device stack at all.
    holders = other_processes_holding(port)
    if holders:
        pids = ", ".join(str(pid) for pid in holders)
        raise OSError(
            f"{port} is already open in another process (pid {pids}). "
            "Stop that process first: two writers on the same port would "
            "interleave motor frames."
        )

    import serial  # late import: this module must import cleanly without pyserial

    handle = serial.Serial()
    handle.port = port
    handle.baudrate = baud
    handle.timeout = 0.2
    handle.dtr = False
    handle.rts = False
    handle.open()
    return handle
