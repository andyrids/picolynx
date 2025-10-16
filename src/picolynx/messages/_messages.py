"""Contains custom `Message` classes for USBIPD-related commands.

Classes:
    USBIPDAttach: Device information message for `usbipd attach` command.
    USBIPDBind: Device information message for `usbipd attach` command.
    USBIPDDetach: Device information message for `usbipd detach` command.
    USBIPDUnbind: Device information message for `usbipd unbind` command.
    WMDeviceChange: `WM_DEVICECHANGE` message for refreshing device state.
"""

from dataclasses import dataclass
from picolynx.commands import USBIPDDevice
from textual.message import Message


@dataclass
class USBIPDAttach(Message):
    """Device information message for `usbipd attach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDBind(Message):
    """Device information message for `usbipd attach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDDetach(Message):
    """Device information message for `usbipd detach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDUnbind(Message):
    """Device information message for `usbipd unbind` command."""

    device: USBIPDDevice


@dataclass
class WMDeviceChange(Message):
    """`WM_DEVICECHANGE` message for refreshing connected device state."""

    broadcast_type: int
    broadcast_port: str
