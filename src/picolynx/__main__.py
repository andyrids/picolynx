""""""

from ast import literal_eval
import csv
import ctypes
import json
import logging
import pathlib
import re
import subprocess
import threading
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache
from getpass import getuser
from socket import gethostname
from types import MappingProxyType
from typing import ClassVar, Optional, TypedDict, TYPE_CHECKING

import win32con
import win32event
import win32evtlog
import win32evtlogutil
import winerror
from picolynx import __version__
from pywintypes import error as PyWinError
from rich.pretty import pprint
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.color import Color
from textual.containers import Container, Horizontal, ItemGrid
from textual.logging import TextualHandler
from textual.message import Message
from textual.theme import BUILTIN_THEMES, Theme
from textual.widgets import DataTable, Label, Checkbox
from textual.widgets.data_table import RowKey
from textual._path import CSSPathType
from win32ctypes.pywin32 import pywintypes

if TYPE_CHECKING:
    from _win32typing import PyEventLogRecord  # pyright: ignore[reportMissingModuleSource]

logging.basicConfig(level="NOTSET", handlers=(TextualHandler(),))
_logger = logging.getLogger(__name__)

BACKWARDS_SEQUENTIAL_READ: int = (
    win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
)

FORWARDS_SEEK_READ: int = (
    win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEEK_READ
)

USBIPD_VID_PID_PTN = "VID_(?P<VID>[A-Z0-9]{4})&PID_(?P<PID>[A-Z0-9]{4})"

GALAXY_THEME = Theme(
    name="galaxy",
    primary="#C45AFF",
    secondary="#A684E8",
    warning="#FFD700",
    error="#FF4500",
    success="#00FA9A",
    accent="#FF69B4",
    background="#0F0F1F",
    surface="#1E1E3F",
    panel="#2D2B55",
    dark=True,
    variables={
        "input-cursor-background": "#C45AFF",
        "footer-background": "transparent",
    },
)


class EnablePnPAuditError(Exception):
    """"""

    pass


class USBIPDError(Exception):
    """"""

    pass


class WSLError(Exception):
    """"""

    pass


class USBIF(IntEnum):
    """USB-IF Raspberry Pi VID & PID enumerations."""

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


class LogLevel(IntEnum):
    """Event log level enumerations."""

    UNDEFINED = 0
    CRITICAL = 1
    ERROR = 2
    WARNING = 3
    INFORMATION = 4
    VERBOSE = 5


class EventType(IntEnum):
    """Event type enumerations"""

    AUDIT_FAILURE = win32con.EVENTLOG_AUDIT_FAILURE
    AUDIT_SUCCESS = win32con.EVENTLOG_AUDIT_SUCCESS
    INFORMATION_TYPE = win32con.EVENTLOG_INFORMATION_TYPE
    WARNING_TYPE = win32con.EVENTLOG_WARNING_TYPE
    ERROR_TYPE = win32con.EVENTLOG_ERROR_TYPE


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

    def __post_init__(self) -> None:
        """"""
        super().__post_init__()
        self.shared = bool(self.device["PersistedGuid"]) 
        self.attached = bool(self.device["StubInstanceId"])

@dataclass
class USBIPDDetachDevice(Message):
    """Device information message for `usbipd detach` command."""

    device: USBIPDDevice

    def __post_init__(self) -> None:
        """"""
        super().__post_init__()
        self.shared = bool(self.device["PersistedGuid"])
        self.attached = bool(self.device["StubInstanceId"])


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
        """_summary_

        Args:
            connection: _description_
        """
        super().__init__()
        self._device_filters: set[str] = {"2E8A:000B","2E8A:0005","2E8A:000A"}
        self._running_distros: set[str] = set()
        self._exit_event: threading.Event = threading.Event()
        self._device_locks: dict[str, threading.Lock] = dict()
        self._thread_lock: threading.Lock = threading.Lock()
        self._log_handle = win32evtlog.OpenEventLog(None, "Security")
        self._evt_handle = win32event.CreateEvent(None, True, False, None)
        win32evtlog.NotifyChangeEventLog(self._log_handle, self._evt_handle)

    @property
    @lru_cache(1)
    def container_devices(self) -> Container:
        return self.query_one("#container-devices", Container)
    
    @property
    @lru_cache(1)
    def container_distros(self) -> Container:
        return self.query_one("#container-distros", Container)

    @property
    @lru_cache(1)
    def container_events(self) -> Container:
        return self.query_one("#container-events", Container)

    @property
    @lru_cache(1)
    def container_filters(self) -> ItemGrid:
        return self.query_one("#container-filters", ItemGrid)

    @property
    @lru_cache(1)
    def table_devices(self) -> DataTable:
        return self.query_one("#table-devices", DataTable)

    @property
    @lru_cache(1)
    def table_distros(self) -> DataTable:
        return self.query_one("#table-distros", DataTable)

    @property
    @lru_cache(1)
    def table_events(self) -> DataTable:
        return self.query_one("#table-events", DataTable)

    @property
    def device_filters(self) -> set[str]:
        return self._device_filters
    
    @property
    def device_locks(self) -> dict[str, threading.Lock]:
        return self._device_locks

    @property
    def exit_event(self) -> threading.Event:
        return self._exit_event

    @property
    def thread_lock(self) -> threading.Lock:
        return self._thread_lock
    
    @property
    def running_distros(self) -> set[str]:
        return self._running_distros

    def compose(self) -> ComposeResult:
        yield TUIHeader()
        with Container(id="container-main"):
            with ItemGrid(id="container-filters"):
                yield Checkbox(
                    "CircuitPython", value=True, name="2E8A:000B", compact=True
                )
                yield Checkbox(
                    "MicroPython", value=True, name="2E8A:0005", compact=True
                )
                yield Checkbox(
                    "Pico SDK", value=True, name="2E8A:000A", compact=True
                )

            with Container(id="container-events"):
                yield DataTable(
                    show_header=True, cursor_type="none", id="table-events", zebra_stripes=True
                )

            with Container(id="container-distros"):
                yield DataTable(
                    show_header=True, cursor_type="none", id="table-distros"
                )

            with Container(id="container-devices"):
                yield DataTable(
                    show_header=True, cursor_type="none", id="table-devices"
                )

    @work(thread=True)
    def monitor_events(self) -> None:
        """"""
        record_offset = 0
        try:
            events = win32evtlog.ReadEventLog(
                self._log_handle, BACKWARDS_SEQUENTIAL_READ, 0
            )

            if events:
                # start reading from the record AFTER the most recent
                record_offset = events[0].RecordNumber + 1

            while not self.exit_event.is_set():
                result = win32event.WaitForSingleObject(self._evt_handle, 5000)

                if result == win32con.WAIT_TIMEOUT:
                    continue

                if result == win32con.WAIT_OBJECT_0:
                    time.sleep(0.5)

                    _logger.info(f"Fetching events @ record #{record_offset}")

                    event_list: list[PyEventLogRecord] = []
                    while True:
                        try:
                            new_events = win32evtlog.ReadEventLog(
                                self._log_handle,
                                FORWARDS_SEEK_READ,
                                record_offset,
                            )
                            if not new_events:
                                break

                            event_list.extend(new_events)
                            record_offset = event_list[-1].RecordNumber + 1
                        except PyWinError as e:
                            # record_offset > `PyEventLogRecord.RecordNumber`
                            if e.args[0] == winerror.ERROR_INVALID_PARAMETER:
                                break
                            else:
                                _logger.error(
                                    "Unexpected `Exception`", exc_info=True
                                )
                                raise e
                    _logger.info(f"Fetched {len(event_list)} events")
                    if not event_list:
                        win32event.ResetEvent(self._evt_handle)
                        continue

                    # PnP filter (`PyEventLogRecord.EventID` is 6416)
                    for event in filter(is_pnp_event, event_list):
                        vid_pid = re.search(
                            USBIPD_VID_PID_PTN, event.StringInserts[4].upper()
                        )
                        VID = vid_pid.group("VID") if vid_pid else None
                        PID = vid_pid.group("PID") if vid_pid else None

                        if VID and PID:
                            self.table_events.add_row(
                                f"{event.TimeGenerated:%H:%M:%S}",
                                f"{VID}:{PID}",
                                event.StringInserts[5],
                            )
                        else:
                            _logger.info(
                                f"PnP Event (#{event.RecordNumber}) not added"
                            )
                    self.table_events.sort("TIME", reverse=True)
                    self.update_table_devices()

                win32event.ResetEvent(self._evt_handle)
        except Exception as e:
            _logger.exception(f"Unexpected error in `monitor_events`: {e}")
        finally:
            win32evtlog.CloseEventLog(self._log_handle)

    def on_checkbox_changed(self, message: Checkbox.Changed) -> None:
        """Handles `Checkbox` widget value change events.

        Args:
            message: Event message object for checkbox value change.
        """
        checkbox = message.checkbox
        if checkbox.name is None:
            raise ValueError(f"Unexpected `checkbox.name` - {checkbox.name}")
        if checkbox.value:
            self.device_filters.add(checkbox.name)
        else:
            self.device_filters.remove(checkbox.name)
        self.update_table_devices()


    def on_mount(self) -> None:
        """Handles Textual App `mount` event."""
        self.register_theme(GALAXY_THEME)
        self.app.theme = "galaxy"

        # set container widget border titles
        self.container_filters.border_title = "Filters"
        self.container_devices.border_title = "Connected Devices"
        self.container_distros.border_title = "WSL Distributions"
        self.container_events.border_title = "Windows PnP Events"

        # setup `DataTable` widget for connected devices
        self.table_devices.add_columns("BUSID", "VID:PID", "DESCRIPTION")
        self.table_devices.add_column("SHARED", key="SHARED")
        self.table_devices.add_column("ATTACHED", key="ATTACHED")
        self.update_table_devices()

        # setup `DataTable` widget for currently installed WSL distros
        installed_distros = wsl_distros()
        if installed_distros.fieldnames:
            columns = [*installed_distros.fieldnames, "DEFAULT"]
        else:
            columns = ["NAME", "STATE", "VERSION", "DEFAULT"]

        self.table_distros.add_columns(*columns)
        self.update_table_distros()
        # for row in installed_distros:
        #     self.table_distros.add_row(*[*row.values(), "*" in row["NAME"]])

        # setup `DataTable` widget for Windows Security event log
        self.table_events.add_column("TIME", key="TIME")
        self.table_events.add_columns("VID:PID", "DESCRIPTION")
        self.monitor_events()

    def on_unmount(self) -> None:
        """Handles Textual App `unmount` event."""
        self.exit_event.set()
    
    @on(USBIPDAttachDevice)
    def handle_attach_device(self, message: USBIPDAttachDevice) -> None:
        """"""
        self.attach_device_worker(message)

    @work(thread=True)
    def attach_device_worker(self, message: USBIPDAttachDevice) -> None:
        """Handles blocking `usbipd_bind` & `usbipd_attach` calls.

        Args:
            message: _description_
        """
        busid = message.device["BusId"]
        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        with device_lock:
            if not message.shared:
                usbipd_bind(busid)
                _logger.info(f"Registered device @ BUSID {busid}")
            if not message.attached and self.running_distros:
                usbipd_attach(busid)
                _logger.info(f"Attached device @ BUSID {busid}")


    @on(USBIPDDetachDevice)
    def handle_detach_device(self, message: USBIPDDetachDevice) -> None:
        """"""
        self.detach_device_worker(message)
    
    @work(thread=True)
    def detach_device_worker(self, message: USBIPDAttachDevice) -> None:
        """Handles blocking `usbipd_detach` calls.

        Args:
            message: _description_
        """
        busid = message.device["BusId"]
        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # mitigate `usbipd_detach` race condition
        with device_lock:
            if message.attached:
                usbipd_detach(busid)
                _logger.info(f"Detached device @ BUSID {busid}")

    def parse_device_state(
            self, device_state: USBIPDState
        ) -> list[list[Text]]:
        """_summary_

        Args:
            device_state: _description_

        Returns:
            _description_
        """
        parsed_devices = []

        for device in device_state["Devices"]:
            if device["BusId"] is None:
                continue
            vid_pid = re.search(USBIPD_VID_PID_PTN, device["InstanceId"])
            VID = vid_pid.group("VID") if vid_pid else "ERROR"
            PID = vid_pid.group("PID") if vid_pid else "ERROR"
            VID_PID = f"{VID}:{PID}"

            style = ""
            if VID == str(USBIF.VID_RPI):
                if VID_PID in self.device_filters:
                    style += "#FF69B4 italic bold"
                    self.post_message(USBIPDAttachDevice(device))
                else:
                    style += "#FF69B4 italic bold strike"
                    self.post_message(USBIPDDetachDevice(device))

            parsed_devices.append(
                [
                    Text(device["BusId"], style=style),
                    Text(VID_PID, style=style),
                    Text(device["Description"], style=style),
                    Text(str(bool(device["PersistedGuid"])), style=style),
                    Text(str(bool(device["StubInstanceId"])), style=style),
                ]
            )

        return parsed_devices

    def update_table_devices(self) -> None:
        """Updates connected USB device information `DataTable`."""
        device_state = usbipd_state()
        new_rows = self.parse_device_state(device_state)
        self.table_devices.clear()
        row_keys = self.table_devices.add_rows(new_rows)
        self.table_devices.sort(
            "SHARED",
            "ATTACHED",
            key=lambda x: [i.plain for i in x],
            reverse=True,
        )
    
    def update_table_distros(self) -> None:
        """Updates installed WSL distro status `DataTable`."""
        distros = wsl_distros()
        for row in distros:
            name, state, version = row.values()
            default, name = tuple(*re.findall(r"(\*)?\s?([A-Za-z]+)", name))

            if state.lower() == "running":
                self.running_distros.add(name)
            else:
                self.running_distros.discard(name)
            self.table_distros.add_row(*[name, state, version, bool(default)])


    def update_table(
            self,
            table: DataTable,
            rows: list[list[Text]],
            clear: bool = False
        ) -> None:
        if clear:
            table.clear()
        table.add_rows(rows)



def is_administrator() -> bool:
    """Indicates whether shell user is administrator."""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


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


def is_pnp_audit() -> bool:
    """Indicates `auditpol` PnP event auditing status.

    Raises:
        EnablePnPAuditError: On `auditpol` process error.

    Returns:
        True if policy inclusion setting is success & failure, else False.
    """
    pnp_status = subprocess.Popen(
        ["auditpol", "/get", "/subcategory:Plug and Play Events", "/r"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )

    try:
        stdout, stderr = pnp_status.communicate(timeout=5)
        if stderr:
            raise EnablePnPAuditError(stderr)
    except subprocess.TimeoutExpired as e:
        pnp_status.kill()
        raise EnablePnPAuditError from e

    if pnp_status.returncode == 0 and stdout:
        policy = next(csv.DictReader(stdout.lower().strip().splitlines()))
        return policy.get("inclusion setting") == "success and failure"
    return False


def is_pnp_event(event: "PyEventLogRecord") -> bool:
    """Indicates if an event is a PnP event.

    Args:
        event: An event log record.

    Returns:
        True if `event.EventID` is 6416 (PnP), else False.
    """
    return winerror.HRESULT_CODE(event.EventID) == 6416


def enable_pnp_audit() -> None:
    """Enables PnP auditing with `auditpol`.

    Raises:
        EnablePnPAuditError: On `auditpol` process error.
        EnablePnPAuditError: On failure to enable PnP auditing.
    """
    pnp_enabled = subprocess.Popen(
        [
            "auditpol",
            "/set",
            "/subcategory:Plug and Play Events",
            "/success:enable",
            "/failure:enable",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )

    try:
        stdout, stderr = pnp_enabled.communicate(timeout=5)
        if not stdout.lower() == "the command was successfully executed.":
            raise EnablePnPAuditError(stderr)
    except subprocess.TimeoutExpired as e:
        pnp_enabled.kill()
        raise EnablePnPAuditError from e


def usbipd_attach(busid: str) -> None:
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
        _logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e


def usbipd_bind(busid: str) -> None:
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
        _logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        _logger.info(stdout or stderr)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e

def usbipd_detach(busid: Optional[str] = None) -> None:
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
        _logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_detach.communicate(timeout=5)
        if (msg := stdout or stderr):
            _logger.info(msg)
        if usbipd_detach.returncode:
            raise USBIPDError(msg)
    except subprocess.TimeoutExpired as e:
        usbipd_detach.kill()
        raise USBIPDError from e


def usbipd_state() -> USBIPDState:
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
        _logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_state.communicate(timeout=5)
        if usbipd_state.returncode:
            raise USBIPDError(stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_state.kill()
        raise USBIPDError from e
    return json.loads(stdout)


def wsl_distros() -> csv.DictReader[str]:
    """"""
    distros = subprocess.Popen(
        ["wsl", "--list", "--verbose"],
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

    return csv.DictReader(
        [
            re.sub(r"(?<!\*)\s+", ",", i.strip())
            for i in stdout.strip().splitlines()
        ]
    )

# def _windows_kill_process(pid):
#     import ctypes
#     PROCESS_TERMINATE = 1
#     handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
#     ctypes.windll.kernel32.TerminateProcess(handle, -1)
#     ctypes.windll.kernel32.CloseHandle(handle)

if __name__ == "__main__":
    # Windows event 6416 logs are located in the Security log
    # C:\Windows\System32\winevt\Logs in the .evtx format

    if not is_administrator():
        sys.exit(0) if run_as_administrator() > 32 else sys.exit(1)

    if not is_pnp_audit():
        enable_pnp_audit()

    try:
        app = TUI()
        app.run()
        pass
    except KeyboardInterrupt as e:
        _logger.info("Caught `KeyboardInterrupt` - TUI shutdown")
    finally:
        _logger.info("TUI shutdown - detaching connected devices")
        usbipd_detach()
