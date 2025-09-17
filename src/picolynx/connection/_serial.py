import os
import struct
import time
from ast import literal_eval
from enum import Enum, IntEnum
from itertools import chain
from functools import wraps
from pathlib import Path
from typing import Callable, Concatenate, Optional, ParamSpec, TypeVar

from rich.pretty import pprint
from rich.style import Style
from rich.table import Table
from serial import Serial
from serial.tools import list_ports
from serial.tools.list_ports_common import ListPortInfo
from serial.tools.list_ports_linux import SysFS
from textual.widgets import Tree
from textual.widgets.tree import TreeNode


DEVICE_LS_R = """
from os import ilistdir
from gc import collect
def iter_dir(dir_path):
    collect()
    base_path = dir_path if dir_path[-1] == "/" else f"{dir_path}/"
    try:
        items = ilistdir(dir_path)
    except OSError:
        return
    for item in items:
        idir = f"{base_path}{item[0]}"
        if item[1] == 0x8000:
            yield idir, True, item[3]
        else:
            yield from iter_dir(idir)
            yield idir, False, 0
for item in iter_dir("/"):
    print(item, end=",")
"""

DEVICE_MKFS = """
import os, machine, rp2
os.umount("/")
bdev = rp2.Flash()
os.VfsLfs2.mkfs(bdev, progsize=256)
vfs = os.VfsLfs2(bdev, progsize=256)
os.mount(vfs, "/")
machine.reset()
"""

DEVICE_HARD_RESET = """from machine import reset; reset()"""

DEVICE_UNAME = """from os import uname; print(eval(f"dict{uname()}"), end="")"""

DEVICE_STATVFS = """
from os import statvfs
from gc import collect
collect()
def h(b):
    if b < 1024: return f"{b} B"
    if b < 1024**2: return f"{b/1024:.1f} KB"
    if b < 1024**3: return f"{b/1024**2:.1f} MB"
    return "N/A"
info = {}
try:
    s = statvfs('/')
    total = s[1] * s[2]
    free = s[1] * s[4]
    used = total - free
    info["Size"] = h(total)
    info["Used"] = f"{h(used)} ({used/total:.1%})"
    info["Free"] = f"{h(free)} ({free/total:.1%})"
except OSError:
    info["Size"] = "N/A"
    info["Used"] = "N/A"
    info["Free"] = "N/A"
print(info, end="")
"""

S = ParamSpec("S")
R = TypeVar("R")

TransportMethod = Callable[Concatenate["Transport", S], R]


def ensure_raw_repl(func: TransportMethod) -> TransportMethod:
    """Wraps any `Transport` method requiring an active raw REPL."""

    @wraps(func)
    def wrapper(
        self: "Transport", *args: S.args, **kwargs: S.kwargs
    ) -> TransportMethod:
        """Wraps `func` method & enters raw REPL if required."""
        self.enter_raw_repl(soft_reset=False)
        self.serial.reset_input_buffer()
        return func(self, *args, **kwargs)

    return wrapper


class TransportError(Exception):
    """Raised on serial-related exceptions."""

    pass


class REPL(Enum):
    """REPL commands & banner enumerations."""

    CTRL_A = b"\x01"
    CTRL_B = b"\x02"
    CTRL_C = b"\x03"
    CTRL_D = b"\x04"
    CTRL_E = b"\x05"
    CTRL_X = b"\x18"
    PROMPT = b">>> "
    RAW_PROMPT = b">"
    RAW_PASTE = b"\x05A\x01"
    RAW_PASTE_OK = b"R\x01"
    RAW_REPL_BANNER = b"raw REPL; CTRL-B to exit\r\n"
    REBOOT_BANNER = b"soft reboot\r\n"


class USBIF(IntEnum):
    """USB-IF Raspberry Pi VID & PID enumerations."""

    VID = 0x2E8A
    PID = 0x0005


class Transport:
    """Manages device serial connections & command execution."""

    def __init__(self, name: str) -> None:
        """Initialises a connection to a RPi device running MicroPython.

        If `name` is not passed, connection to the first available device
        will be attempted.

        Args:
            name: Device name e.g. `/dev/ttyACM0` or 'COM3'.
        """
        self._serial = Serial(name, baudrate=115200, exclusive=True)
        if os.name == "nt":
            self._serial.open()
        self.enter_raw_repl(soft_reset=True)

    @property
    def serial(self) -> Serial:
        """Active `Serial` connection to a device."""
        return self._serial

    @ensure_raw_repl
    def exec(
        self,
        command: bytes | str,
        data_consumer: Callable[[bytes | bytearray], None],
    ) -> bytes | None:
        """Executes commands on a connected device.

        Args:
            command: A command or script to run on the device.
            data_consumer: A callback function which handles output data.

        Raises:
            TransportError: On unexpected data during raw-paste mode.
            TransportError: On failure to complete REPL raw-paste.
            TransportError: On executed command output EOT timeout.
            TransportError: On executed command exception EOT timeout.
            TransportError: On executed command exception.

        Returns:
            A bytes object containing command execution output, if
            `data_consumer` is None.
        """
        if isinstance(command, str):
            command = bytes(command, encoding="utf8")

        # raw-paste mode enquiry - Ctrl-E (ENQ) then 'A' then Ctrl-A (SOH)
        self.serial.write(REPL.RAW_PASTE.value)

        # read 2 bytes to determine if the device entered raw-paste
        if self.serial.read(2) == REPL.RAW_PASTE_OK.value:
            # read 2 bytes - flow control
            header = self.serial.read(2)
            # window-size-increment & remaining-window-size (in bytes)
            bytes_increment = bytes_remaining = struct.unpack("<H", header)[0]

            i = 0
            send_terminated = False
            while i < len(command):
                while bytes_remaining == 0 or self.serial.in_waiting:
                    data = self.serial.read(1)
                    match data:
                        # new data window
                        case REPL.CTRL_A.value:
                            bytes_remaining += bytes_increment
                        # EOF terminates
                        case REPL.CTRL_D.value:
                            self.serial.write(REPL.CTRL_D.value)
                            send_terminated = True
                            break
                        case _:
                            raise TransportError(f"Unexpected data - {data}")
                if send_terminated:
                    break
                bytes_ = command[i : min(i + bytes_remaining, len(command))]
                self.serial.write(bytes_)
                bytes_remaining -= len(bytes_)
                i += len(bytes_)

            # indicate end-of-data with EOT
            if not send_terminated:
                self.serial.write(REPL.CTRL_D.value)

            # device has received & compiled `command`
            data = self.read_until(REPL.CTRL_D.value)
            if not data.endswith(REPL.CTRL_D.value):
                raise TransportError(f"Could not complete REPL raw paste")

            # executed command output
            data = self.read_until(REPL.CTRL_D.value, data_consumer)
            if not data.endswith(REPL.CTRL_D.value):
                raise TransportError(f"Timeout waiting for first EOF reception")
            command_output = data.replace(REPL.CTRL_D.value, b"")

            # executed command exceptions
            data = self.read_until(REPL.CTRL_D.value)
            if not data.endswith(REPL.CTRL_D.value):
                raise TransportError(f"Timeout waiting for first EOF reception")
            command_error = data.replace(REPL.CTRL_D.value, b"")

            if command_error:
                raise TransportError(command_error.decode())

            if data_consumer is None:
                return command_output

    def read_until(
        self,
        expected: bytes,
        data_consumer: Optional[Callable[[bytes | bytearray], None]] = None,
        timeout: int = 10,
    ) -> bytearray:
        """"""
        init_time = time.monotonic()
        data = bytearray()
        while True:
            if data.endswith(expected):
                break
            elif self.serial.in_waiting > 0:
                new_data = self.serial.read()
                if data_consumer:
                    data_consumer(new_data)
                    data.clear()
                    data.extend(new_data)
                else:
                    data.extend(new_data)
                init_time = time.monotonic()
            if time.monotonic() >= init_time + timeout:
                break
            time.sleep(0.01)
        return data

    def enter_raw_repl(self, soft_reset: bool = True) -> None:
        """"""
        # interrupt current execution via Ctrl-C (ETX)
        self.serial.write(REPL.CTRL_C.value)

        # flush input
        nbytes = self.serial.in_waiting
        while nbytes > 0:
            self.serial.read(nbytes)
            nbytes = self.serial.in_waiting

        # enter raw REPL via Ctrl-A (SOH)
        self.serial.write(REPL.CTRL_A.value)

        if soft_reset:
            data = self.read_until(REPL.RAW_REPL_BANNER.value)
            if not data.endswith(REPL.RAW_REPL_BANNER.value):
                raise TransportError("Could not enter raw REPL")

            # soft-reset via Ctrl-D (EOT)
            self.serial.write(REPL.CTRL_D.value)
            data = self.read_until(REPL.REBOOT_BANNER.value)
            if not data.endswith(REPL.REBOOT_BANNER.value):
                raise TransportError(f"Soft-reset failed - {data}")

        data = self.read_until(REPL.RAW_REPL_BANNER.value)
        if not data.endswith(REPL.RAW_REPL_BANNER.value):
            raise TransportError(f"Could not enter raw REPL")


class Device:
    """A Transport wrapper for a connected device running MicroPython."""

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialises a connection to the specified device.

        Args:
            name: Device name e.g. `/dev/ttyACM0` or 'COM3'.
        """
        self.transport = self._connect(name)

    @classmethod
    def _connect(cls, name: Optional[str] = None) -> Transport:
        """Factory method to find & connect to a supported device.

        Args:
            name: Device name e.g. `/dev/ttyACM0` or 'COM3'.

        Returns:
            An active SerialTransport instance.

        Raises:
            TransportError: On unsupported or unavailable device.
            TransportError: On failed connection to device.
            TransportError: On failed auto-discovery & connection.
        """
        comports = {p.device: p for p in list_ports.comports()}
        if name:
            if name not in comports or not cls._supported(comports[name]):
                raise TransportError(
                    f"`{name}` is not supported or unavailable"
                )
            try:
                return Transport(name)
            except TransportError as e:
                raise TransportError(f"`{name}` connection failed") from e

        for name, comport in comports.items():
            if cls._supported(comport):
                try:
                    return Transport(name)
                except TransportError:
                    continue
        raise TransportError("Auto-discovery and connection failed")

    @staticmethod
    def _supported(comport: ListPortInfo | SysFS) -> bool:
        """Checks serial devices for supported device VID & PID."""
        return comport.vid == USBIF.VID and comport.pid == USBIF.PID

    def listdir(self) -> tuple[dict[Path, int], dict[Path, int]]:
        """Lists directories and files on the device.

        Returns:
            A tuple of dict objects for directories and files on the device.
        """
        buffer, data_consumer = buffer_factory()
        self.transport.exec(DEVICE_LS_R, data_consumer=data_consumer)

        directories: dict[Path, int] = {}
        files: dict[Path, int] = {}
        for full_path, is_file, size in literal_eval(f"[{buffer.decode()}]"):
            if is_file:
                files[Path(full_path)] = size
            else:
                directories[Path(full_path)] = size
        return directories, files

    def rmdir(self, path: Path | str) -> bool:
        """Removes the directory `path` on the device.

        Args:
            path: The path to remove.

        Returns:
            True if operation was successful, else False.
        """
        try:
            command = f"import os; os.rmdir('{path}');"
            self.transport.exec(command)
        except TransportError:
            return False
        return True

    def rmfile(self, path: Path | str) -> bool:
        """Removes the file `path` on the device.

        Args:
            path: The path to remove.

        Returns:
            True if operation was successful, else False.
        """
        try:
            command = f"import os; os.remove('{path}');"
            self.transport.exec(command)
        except TransportError:
            return False
        return True

    def statvfs(self) -> dict[str, int]:
        """Returns device filesystem status information.

        Returns:
            Device filesystem information `dict` with the keys; `fs_size` &
            `fs_free`.
        """
        buffer, data_consumer = buffer_factory()
        self.transport.exec(DEVICE_STATVFS, data_consumer=data_consumer)
        return literal_eval(buffer.decode())

    def tree(self) -> Tree:
        """Creates a directory tree for the device.

        Returns:
            A `Tree` object representing device content.
        """
        directories, files = self.listdir()
        paths = sorted(chain(directories, files))

        tree: Tree[str] = Tree("📁")
        tree_nodes: dict[Path, TreeNode] = {Path("/"): tree.root}

        for path in paths:
            if path.name == "/":
                continue

            parent_node = tree_nodes[path.parent]
            if path in files:
                label = f"📄 {path.name}  [dim]({files[path]} B)[/dim]"
                parent_node.add_leaf(label)
            else:
                label = f"📁 {path.name}"
                tree_nodes[path] = parent_node.add(label, allow_expand=False)

        tree.root.expand_all()
        tree.guide_depth = 3
        return tree

    def uname(self) -> dict[str, str]:
        """Returns information `dict` about the device and OS.

        Returns:
            Device information `dict` with the keys; `sysname`, `nodename`,
            `release`, `version` & `machine`.
        """
        buffer, data_consumer = buffer_factory()
        self.transport.exec(DEVICE_UNAME, data_consumer=data_consumer)
        return literal_eval(buffer.decode())

    def information(self) -> Table:
        info_table = Table(
            show_header=False,
            box=None,
            title="Device Information",
            title_style=Style(color="#bbc8e8", bold=True),
        )

        info_table.add_column()
        info_table.add_column(min_width=25, max_width=35)
        for label, value in self.uname():
            info_table.add_row(f"[label]{label.capitalize()}", value)

        return info_table


def buffer_factory() -> tuple[bytearray, Callable[[bytes | bytearray], None]]:
    """Creates a `bytearray` buffer and a consumer function to populate it.

    Returns:
        A tuple containing the `bytearray` buffer and the consumer function.
    """
    buffer = bytearray()

    def data_consumer(data: bytes | bytearray) -> None:
        """Populates a `bytearray` with data."""
        nonlocal buffer
        # remove End of Transmission (EOT) control character (ASCII 0x04)
        buffer.extend(data.replace(b"\x04", b""))

    return buffer, data_consumer
