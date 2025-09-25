""""""

from ast import literal_eval
import asyncio
import contextvars
import ctypes
import json
import re
import subprocess
import threading
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import IntEnum
from functools import lru_cache
from getpass import getuser
from logging import basicConfig, getLogger
from socket import gethostname
from types import MappingProxyType
from typing import Callable, ClassVar, Optional, TypedDict, TYPE_CHECKING

import win32api
import win32con
import win32event
import win32evtlog
import win32evtlogutil
import win32gui
import winerror

from picolynx import __version__
from picolynx.exceptions import USBIPDError, WSLError
from picolynx.utility import is_administrator
from picolynx.structures import *
from picolynx.themes import GALAXY_THEME

from pywintypes import error as PyWinError
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container, Horizontal
from textual.logging import TextualHandler
from textual.message import Message
from textual.reactive import reactive

from textual.widgets import DataTable, Label
from textual._path import CSSPathType
from win32con import WM_DEVICECHANGE
from win32ctypes.pywin32 import pywintypes


if TYPE_CHECKING:
    from _typeshed import ReadableBuffer
    from _win32typing import PyEventLogRecord  # pyright: ignore[reportMissingModuleSource]
    

LOG_FMT = "%(levelname)-8s | %(funcName)s:%(lineno)d - %(message)s"
basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))
_log = getLogger(__name__)

USBIPD_VID_PID_PTN = "VID_(?P<VID>[A-Z0-9]{4})&PID_(?P<PID>[A-Z0-9]{4})"


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


class USBIPDDevice(TypedDict):
    """Device information structure for `usbipd` state JSON."""

    BusId: str
    ClientIPAddress: Optional[str]
    Description: str
    InstanceId: str
    IsForced: bool
    PersistedGuid: Optional[str]
    StubInstanceId: Optional[str]


class USBIPDState(TypedDict):
    """Top-level structure for `usbipd` state JSON."""

    Devices: list[USBIPDDevice]


@dataclass
class USBIPDAttachDevice(Message):
    """Device information message for `usbipd attach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDDetachDevice(Message):
    """Device information message for `usbipd detach` command."""

    device: USBIPDDevice


@dataclass
class WMDeviceChange(Message):
    """`WM_DEVICECHANGE` message for refreshing connected device state."""

    broadcast_type: int


# @dataclass(frozen=True)
@dataclass
class AppState:
    """Stores the entire application state."""
    connected_devices: USBIPDState = field(default_factory=lambda: {"Devices": []})


APP_STATE: ContextVar[AppState] = ContextVar("app_state", default=AppState())


class DeviceNotifier:
    """Notifies TUI of Windows device changes.
    
    Creates a hidden window, a window procedure, a dedicated thread for the
    message pump, and manages thread-safe communication back to the asyncio
    event loop for the TUI app.
    """

    def __init__(
            self,
            loop: asyncio.AbstractEventLoop,
            callback: Callable
        ) -> None:
        """Initialises the `DeviceNotifier` class.

        Args:
            loop: The running event loop.
            callback: A callback for `WM_DEVICECHANGE`messages.
        """
        self._loop = loop
        self._callback = callback
        self._thread = threading.Thread(target=self.message_pump, daemon=True)
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Running event loop property."""
        return self._loop

    @property
    def callback(self) -> Callable:
        """Message callback function property."""
        return self._callback

    @property
    def thread(self) -> threading.Thread:
        """Message pump thread property."""
        return self._thread

    def start(self) -> None:
        """Starts the `message_pump` thread."""
        self.thread.start()

    def message_pump(self) -> None:
        """Runs a message loop for `WM_DEVICECHANGE` messages."""

        wc = win32gui.WNDCLASS()
        hinst = win32api.GetModuleHandle(None)
        setattr(wc, "hInstance", hinst)
        setattr(wc, "lpszClassName", self.__class__.__name__)
        setattr(wc, "lpfnWndProc", {WM_DEVICECHANGE: self.process_message})
        class_atom = win32gui.RegisterClass(wc)

        # create a new window
        self.hwnd = win32gui.CreateWindow(
            class_atom, # class name
            "Device Change Demo", # window title
            0, # style
            0, # x
            0, # y
            win32con.CW_USEDEFAULT, # width
            win32con.CW_USEDEFAULT, # height
            0, # parent
            0, # menu
            hinst, # hinstance
            None # reserved
        )

        # infinite, blocking loop
        win32gui.PumpMessages()

    def process_message(
            self,
            hwnd: int,
            umsg: int,
            wparam: int,
            lparam: int
        ) -> int:
        """Processes `WM_DEVICECHANGE` messages.

        Callbacks are scheduled on the main asyncio loop via the
        `call_soon_threadsafe` method of the running event loop.

        Args:
            hwnd: A handle to the window class.

            umsg: The `WM_DEVICECHANGE` identifier.

            wparam: The device-change event.

            lparam: A pointer to a structure containing event-specific data.

        Returns:
            Message processing result, which depends on the message.
        """
        _log.info(f"`WM_DEVICECHANGE` - {wparam=:04X}, {lparam=:04X}")

        # avoid reading from a NULL pointer
        if lparam:
            hdr = DEV_BROADCAST_HDR.from_address(lparam)
            match hdr.dbch_devicetype:
                case DBCDeviceType.DBT_DEVTYP_VOLUME:
                    _log.info(f"Device type is `DBT_DEVTYP_VOLUME`")
                case DBCDeviceType.DBT_DEVTYP_PORT:
                    _log.info(f"Device type is `DBT_DEVTYP_PORT`")
                    interface = DEV_BROADCAST_PORT_W.from_address(lparam)
                    address = ctypes.addressof(interface) + DEV_BROADCAST_PORT_W.dbcp_name.offset
                    device_name = ctypes.wstring_at(address)
                    _log.info(f"Device ID is {device_name}")
                case DBCDeviceType.DBT_DEVTYP_DEVICEINTERFACE:
                    _log.info(f"Device type is `DBT_DEVTYP_DEVICEINTERFACE`")
                    interface = DEV_BROADCAST_DEVICEINTERFACE_W.from_address(lparam)
                    name_buffer = (ctypes.c_wchar * len(interface.dbcc_name))
                    deviceid = name_buffer.from_address(ctypes.addressof(interface.dbcc_name)).value
                    _log.info(f"Device ID is {deviceid}")
                case _:
                    _log.info(f"Unhandled `dbch_devicetype` - {hdr.dbch_devicetype}")

        match wparam:
            case DBCEvent.DBT_DEVNODES_CHANGED:
                _log.info(f"`DBT_DEVNODES_CHANGED` ({wparam:04X})")
            case DBCEvent.DBT_DEVICEARRIVAL:
                _log.info(f"`DBT_DEVICEARRIVAL` ({wparam:04X})")
                self.loop.call_soon_threadsafe(self.callback, wparam)
            case DBCEvent.DBT_DEVICEREMOVECOMPLETE:
                _log.info(f"`DBT_DEVICEREMOVECOMPLETE` ({wparam:04X})")
                self.loop.call_soon_threadsafe(self.callback, wparam)
            case _:
                _log.warning(f"Unexpected device-change event ({wparam:04X})")
        return win32gui.DefWindowProc(hwnd, umsg, wparam, lparam)


class TUIHeader(Horizontal):
    """TUI header widget."""

    def compose(self) -> ComposeResult:
        """Generates the TUI header components."""
        version = f"[b]PicoLynx[/] [dim]v{__version__}[/]"
        yield Label(version, id="header-title")
        hostname = Text.from_markup(f"{getuser()}@{gethostname()}")
        yield Label(hostname, id="header-hostname")


class TUI(App):
    """Main `textual` TUI."""

    BINDINGS: ClassVar[list[BindingType]] = [("d", "dark_mode", "Dark mode")]

    CSS_PATH: ClassVar[CSSPathType | None] = "global.tcss"

    TITLE: str | None = "TITLE"

    SUB_TITLE: str | None = "SUBTITLE"

    def __init__(self) -> None:
        """Initialises TUI App."""
        super().__init__()
        self._connected_devices: set[str] = set()
        self._exit_event: threading.Event = threading.Event()
        self._device_locks: dict[str, threading.Lock] = dict()
        self._thread_lock: threading.Lock = threading.Lock()

    @property
    @lru_cache(1)
    def container_devices(self) -> Container:
        """Property for connected devices `Container` widget."""
        return self.query_one("#container-devices", Container)

    @property
    @lru_cache(1)
    def container_events(self) -> Container:
        """Property for Windows events `Container` widget."""
        return self.query_one("#container-events", Container)

    @property
    @lru_cache(1)
    def table_devices(self) -> DataTable:
        """Property for connected devices `DataTable` widget."""
        return self.query_one("#table-devices", DataTable)

    @property
    @lru_cache(1)
    def table_events(self) -> DataTable:
        """Property for Windows events `DataTable` widget."""
        return self.query_one("#table-events", DataTable)
    
    @property
    def device_locks(self) -> dict[str, threading.Lock]:
        """Property for device threading lock."""
        return self._device_locks

    @property
    def exit_event(self) -> threading.Event:
        """Property for threading exit `Event`."""
        return self._exit_event

    @property
    def thread_lock(self) -> threading.Lock:
        """Property for threading lock."""
        return self._thread_lock

    def compose(self) -> ComposeResult:
        yield TUIHeader()
        with Container(id="container-main"):
            with Container(id="container-devices"):
                yield DataTable(
                    show_header=True, cursor_type="none", id="table-devices"
                )
            with Container(id="container-events"):
                yield DataTable(
                    show_header=True, cursor_type="none", id="table-events", zebra_stripes=True
                )

    def on_mount(self) -> None:
        """Handles TUI `mount` event."""

        self.register_theme(GALAXY_THEME)
        self.app.theme = "galaxy"

        # set container widget border titles
        self.container_devices.border_title = "Connected Devices"
        self.container_events.border_title = "Windows PnP Events"

        # setup `DataTable` widget for connected devices
        self.table_devices.add_columns("BUSID", "VID:PID", "DESCRIPTION")
        self.table_devices.add_column("SHARED", key="SHARED")
        self.table_devices.add_column("ATTACHED", key="ATTACHED")

        # setup `DataTable` widget for Windows Security event log
        self.table_events.add_column("#", key="#")
        self.table_events.add_column("TIME", key="TIME")
        self.table_events.add_columns("VID:PID", "DESCRIPTION")

        running_loop = asyncio.get_running_loop()        
        self.notifier = DeviceNotifier(running_loop, self.handle_wm_device_change)
        self.notifier.start()

    def on_unmount(self) -> None:
        """Handles TUI `unmount` event."""
        self.exit_event.set()

    @on(USBIPDAttachDevice)
    def handle_attach_device(self, message: USBIPDAttachDevice) -> None:
        """forwards `USBIPDAttachDevice` messages to a dedicated worker."""
        if not message.device["StubInstanceId"]:
            self.attach_device_worker(message)

    @work(thread=True)
    def attach_device_worker(self, message: USBIPDAttachDevice) -> None:
        """Handles blocking `usbipd_bind` & `usbipd_attach` calls.

        Args:
            message: Device information message for `usbipd attach` command.
        """
        busid = message.device["BusId"]
        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not device_lock.acquire(blocking=False):
            _log.info(f"Attachment of device @ BUSID {busid} in progress")
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            devices = run_usbipd_state()["Devices"]
            device = next((d for d in devices if d["BusId"] == busid), None)

            if not device:
                _log.warning(f"Device @ BUSID {busid} is not found")
                return
            
            if not device["PersistedGuid"]:
                run_usbipd_bind(busid)
                _log.info(f"Registration of device @ BUSID {busid} complete")
            
            if not device["StubInstanceId"] and any(run_wsl_list()):
                run_usbipd_attach(busid)
                _log.info(f"Attachment of device @ BUSID {busid} complete")
        finally:
            device_lock.release()

    @on(USBIPDDetachDevice)
    def handle_detach_device(self, message: USBIPDDetachDevice) -> None:
        """forwards `USBIPDDetachDevice` messages to a dedicated worker."""
        self.detach_device_worker(message)

    @work(thread=True)
    def detach_device_worker(self, message: USBIPDDetachDevice) -> None:
        """Handles blocking `usbipd_detach` calls.

        Args:
            message: Device information message for `usbipd attach` command.
        """
        busid = message.device["BusId"]
        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not device_lock.acquire(blocking=False):
            _log.info(f"Detachment of device @ BUSID {busid} in progress")
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            devices = run_usbipd_state()["Devices"]
            device = next((d for d in devices if d["BusId"] == busid), None)

            # device already detached/disconnected
            if not device:
                _log.info(f"Missing device @ BUSID {busid}")
                return

            # if currently attached
            if device["StubInstanceId"]:
                run_usbipd_detach(busid)
                _log.info(f"Detachment of device @ BUSID {busid} complete")
        finally:
            device_lock.release()

    def parse_usbipd_state(
            self, usbipd_state: USBIPDState
        ) -> list[list[Text]]:
        """Parses device information in `usbipd state` output.

        Args:
            usbipd_state: Current state of all connected USB devices.

        Returns:
            A list of Text objects for use in a `DataTable` widget.
        """
        parsed_devices = []

        for device in usbipd_state["Devices"]:
            if (busid := device["BusId"]) is None:
                # if device["StubInstanceId"]:
                #     self.post_message(USBIPDDetachDevice(device))
                continue
            vid_pid = re.search(USBIPD_VID_PID_PTN, device["InstanceId"])
            VID = vid_pid.group("VID") if vid_pid else "ERROR"
            PID = vid_pid.group("PID") if vid_pid else "ERROR"
            VID_PID = f"{VID}:{PID}"

            style = ""
            if VID == str(USBIF.VID_RPI):
                style += "#00FA9A italic bold"
                self.post_message(USBIPDAttachDevice(device))

            # truncate description text to a max width of 24 characters
            description = Text(device["Description"], style=style)
            description.truncate(max_width=24, overflow="ellipsis")

            parsed_devices.append(
                [
                    Text(busid, style=style),
                    Text(VID_PID, style=style),
                    description,
                    Text(str(bool(device["PersistedGuid"])), style=style),
                    Text(str(bool(device["StubInstanceId"])), style=style),
                ]
            )

        return parsed_devices

    def update_table_devices(
            self, usbipd_state: Optional[USBIPDState] = None
        ) -> None:
        """Updates connected USB device information `DataTable`."""

        self.table_devices.clear()
        self.table_devices.add_rows(self.parse_usbipd_state(usbipd_state or run_usbipd_state()))
        self.table_devices.sort(
            "SHARED",
            "ATTACHED",
            key=lambda x: [getattr(i, "plain", i) for i in x],
            reverse=True,
        )

    def handle_wm_device_change(self, device_event: DBCEvent) -> None:
        """Handles `WM_DEVICECHANGE` messages receipt.

        Args:
            device_event: The device event from a `WM_DEVICECHANGE` message.
        """
        _log.info(f"`WM_DEVICECHANGE` message ({device_event=:04X})")
        try:
            self.post_message(WMDeviceChange(device_event))
        except LookupError as e:
            _log.exception(e, exc_info=True)


def run_as_administrator() -> int:
    """"""
    return ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        " ".join(sys.argv),
        None,
        win32con.SW_SHOWNORMAL,
    )


def run_usbipd_attach(busid: str) -> None:
    """Attaches a USB device to WSL.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd attach` failure.
    """
    try:
        usbipd_attach = subprocess.Popen(
            ["usbipd", "attach", "--busid", busid, "--wsl"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        _log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e


def run_usbipd_bind(busid: str) -> None:
    """Registers a USB device for sharing, enabling attachment to WSL.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd bind` failure.
    """
    try:
        usbipd_attach = subprocess.Popen(
            ["usbipd", "bind", "--busid", busid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        _log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        _log.info(stdout or stderr)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e


def run_usbipd_detach(busid: Optional[str] = None) -> None:
    """Detach a USB device from WSL.

    Will detach all USB devices, if `busid` is not passed.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd detach` failure.
    """
    try:
        options = ("--all",) if busid is None else ("--busid", busid)
        usbipd_detach = subprocess.Popen(
            ["usbipd", "detach", *options],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        _log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_detach.communicate(timeout=5)
        if (msg := stdout or stderr):
            _log.info(msg)
        if usbipd_detach.returncode:
            raise USBIPDError(msg)
    except subprocess.TimeoutExpired as e:
        usbipd_detach.kill()
        raise USBIPDError from e


def run_usbipd_state() -> USBIPDState:
    """Fetches the current state of all USB devices in machine-readable JSON.

    Raises:
       USBIPDError: `usbipd` is not installed.

    Returns:
        Current state of all USB devices.
    """
    try:
        usbipd_state = subprocess.Popen(
            ["usbipd", "state"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        _log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_state.communicate(timeout=5)
        if usbipd_state.returncode:
            raise USBIPDError(stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_state.kill()
        raise USBIPDError from e
    return json.loads(stdout)


def run_wsl_list(running: bool = True) -> tuple[str, ...]:
    """Lists running WSL distributions.

    Returns:
        A list of running WSL distributions.
    """

    args = ["wsl", "--list", "--quiet"]
    if running:
        args.append("--running")
    distros = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        # must specify UTF-16 variant (no Byte Order Mark)
        encoding="UTF-16-LE",
    )

    try:
        stdout, stderr = distros.communicate(timeout=5)
        if stderr:
            raise WSLError(stderr)
    except subprocess.TimeoutExpired as e:
        distros.kill()
        raise WSLError from e

    return tuple(i for i in stdout.strip().splitlines())


if __name__ == "__main__":
    if not is_administrator():
        sys.exit(0) if run_as_administrator() > 32 else sys.exit(1)

    try:
        app = TUI()
        app.run()
    except KeyboardInterrupt as e:
        _log.info("Caught `KeyboardInterrupt` - TUI shutdown")
    finally:
        _log.info("TUI shutdown - detaching connected devices")
        run_usbipd_detach()
