"""Opening the arm's port (pyserial lives in the dashboard layer, not in core).

The arm hangs on the **same** STM32 board as the chassis, so it is opened with
the same opener -- identical baud (1 Mbaud), identical DTR/RTS handling (lowered
before ``open()`` because the default line states can reboot the controller),
and the same holder check that refuses to start when another process already
holds the device. There is no second serial stack here on purpose: two writers
on one port is how a robot does something nobody asked for.

``amr_core.robot.arm_bus`` stays free of pyserial (guard test:
``tests/test_robot_no_actuation.py``) and receives the opened handle.
"""

from __future__ import annotations

from amr_dashboard.chassis_transport import DEFAULT_BAUD, open_serial_port

#: The board ignores frames for ~2,36 s after every open (measured), so a caller
#: that wants to move something immediately must wait this out.
BOOT_WINDOW_S = 2.5


def open_arm_port(port: str = "/dev/ttyACM0", baud: int = DEFAULT_BAUD):
    """Open the arm board's serial port, ready to carry bus-servo frames."""
    return open_serial_port(port, baud)
