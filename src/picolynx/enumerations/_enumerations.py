"""Contains enumeratons for USB-IF VID & PID values.

Enumerations:
    USBIF: USB-IF VID & PID enumerations.
"""

from enum import IntEnum


class USBIF(IntEnum):
    """USB-IF VID & PID enumerations."""

    PID_PICO_BOOT = 0x0003
    PID_PICO_PROBE = 0x0004
    PID_PICO_MICROPYTHON = 0x0005
    PID_PICO_SDK = 0x000A
    PID_PICO_CIRCUITPYTHON = 0x000B
    PID_PICO2_BOOT = 0x000F
    PID_USBIPD = 0xCAFE
    VID_RPI = 0x2E8A
    VID_USBIPD = 0x80EE

    def __str__(self) -> str:
        """Formats a value as a zero-padded, 4-digit hex string."""
        return f"{self.value:04X}"
