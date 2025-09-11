""""""
from ast import literal_eval
import csv
import ctypes
import getpass
import json
import logging
import pathlib
import re
import socket
import subprocess
import threading
import sys
from dataclasses import dataclass
from enum import IntEnum
import time
from typing import Any, ClassVar, Iterable, Optional, TypedDict, TYPE_CHECKING

import win32con
import win32event
import win32evtlog
import win32evtlogutil
import winerror
from picolynx import __version__
from pywintypes import error as PyWinError
from rich.pretty import pprint
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.color import Color
from textual.containers import Container, Horizontal, HorizontalGroup, ItemGrid
from textual.logging import TextualHandler
from textual.theme import BUILTIN_THEMES, Theme
from textual.widgets import DataTable, Label, Checkbox
from textual._path import CSSPathType
from win32ctypes.pywin32 import pywintypes

if TYPE_CHECKING:
    from _win32typing import PyEventLogRecord # pyright: ignore[reportMissingModuleSource]

logging.basicConfig(level="NOTSET", handlers=(TextualHandler(),))
_logger = logging.getLogger(__name__)

# EVENTLOG_BACKWARDS_READ
# EVENTLOG_FORWARDS_READ
# EVENTLOG_SEQUENTIAL_READ
# EVENTLOG_SEEK_READ

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
    }
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
    VID = 0x2E8A

    def __str__(self) -> str:
        """Formats a value as a zero-padded, 4-digit hex string."""
        return f"{self.value:04X}"


class LogLevel(IntEnum):
    """"""
    UNDEFINED = 0
    CRITICAL = 1
    ERROR = 2
    WARNING = 3
    INFORMATION = 4
    VERBOSE = 5


class EventType(IntEnum):
    """"""
    AUDIT_FAILURE = win32con.EVENTLOG_AUDIT_FAILURE
    AUDIT_SUCCESS = win32con.EVENTLOG_AUDIT_SUCCESS
    INFORMATION_TYPE = win32con.EVENTLOG_INFORMATION_TYPE
    WARNING_TYPE = win32con.EVENTLOG_WARNING_TYPE
    ERROR_TYPE = win32con.EVENTLOG_ERROR_TYPE


# @dataclass
# class PyEventLogRecord:
#     """
#     A type hint for the PyEventLogRecord object returned by win32evtlog.ReadEventLog.
#     """
#     Reserved: int
#     RecordNumber: int
#     TimeGenerated: pywintypes.datetime
#     TimeWritten: pywintypes.datetime
#     EventID: int
#     EventType: int
#     EventCategory: int
#     ReservedFlags: int
#     ClosingRecordNumber: int
#     SourceName: str
#     StringInserts: tuple[str, ...]
#     Sid: Any  # PySID is not a standard type, so we use Any
#     Data: bytes
#     ComputerName: str


@dataclass
class Device:
    description: str
    busid: str
    instance_id: str
    shared: bool
    attached: bool


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


class TUIHeader(Horizontal):
    """TUI header widget."""

    def compose(self) -> ComposeResult:
        """Generates the TUI header components."""
        yield Label(f"[b]PicoLynx[/] [dim]v{__version__}[/]", id="header-title")
        hostname = Text.from_markup(f"{getpass.getuser()}@{socket.gethostname()}")
        yield Label(hostname, id="header-hostname")


class TUI(App):
    """"""
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
        self._device_filters = {"2E8A:000B", "2E8A:0005", "2E8A:000A"}
        self._exit_event = threading.Event()
        self._thread_lock = threading.Lock()

        self._log_handle = win32evtlog.OpenEventLog(None, "Security")
        self._evt_handle = win32event.CreateEvent(None, True, False, None)
        win32evtlog.NotifyChangeEventLog(self._log_handle, self._evt_handle)

    @property
    def device_filters(self) -> set[str]:
        return self._device_filters

    @property
    def exit_event(self) -> threading.Event:
        return self._exit_event

    @property
    def thread_lock(self) -> threading.Lock:
        return self._thread_lock
    
    def compose(self) -> ComposeResult:
        yield TUIHeader()
        with Container(id="container-main"):
            with ItemGrid(id="container-filters"):
                yield Checkbox("2E8A:000B", value=True, tooltip="CircuitPython", compact=True)
                yield Checkbox("2E8A:0005", value=True, tooltip="MicroPython", compact=True)
                yield Checkbox("2E8A:000A", value=True, tooltip="Pico SDK", compact=True)   

            with Container(id="container-events"):
                yield DataTable(show_header=True, cursor_type="none", id="table-events")

            with Container(id="container-distros"):
                yield DataTable(show_header=True, cursor_type="none", id="table-distros")

            with Container(id="container-devices"):
                yield DataTable(show_header=True, cursor_type="none", id="table-devices")

    @work(thread=True)
    def monitor_events(self) -> None:
        """"""
        record_number = 0
        try:
            events = win32evtlog.ReadEventLog(
                self._log_handle, BACKWARDS_SEQUENTIAL_READ, 0
            )

            if events:
                # start reading from the record AFTER the most recent
                record_number = events[0].RecordNumber + 1

            while not self.exit_event.is_set():

                result = win32event.WaitForSingleObject(self._evt_handle, 5000)

                if result == win32con.WAIT_TIMEOUT:
                    continue

                if result == win32con.WAIT_OBJECT_0:
                    time.sleep(0.5)

                    _logger.info(f"GETTING EVENTS - record_number ({record_number})")

                    event_list: list[PyEventLogRecord] = []
                    while True:
                        try:
                            new_events = win32evtlog.ReadEventLog(
                                self._log_handle, FORWARDS_SEEK_READ, record_number
                            )
                            if not new_events:
                                break

                            event_list.extend(new_events)
                            record_number = event_list[-1].RecordNumber + 1

                            _logger.info(new_events)
                            _logger.info(record_number)
                        except PyWinError as e:
                            if e.args[0] == winerror.ERROR_INVALID_PARAMETER:
                                break
                            else:
                                _logger.error("Unexpected `Exception`", exc_info=True)
                                raise e

                    if not event_list:
                        win32event.ResetEvent(self._evt_handle)
                        continue

                    events_table = self.query_one("#table-events", DataTable)
                    for event in filter(is_pnp_event, event_list):
                        vid_pid = re.search(USBIPD_VID_PID_PTN, event.StringInserts[4])
                        VID = vid_pid.group("VID") if vid_pid else None
                        PID = vid_pid.group("PID") if vid_pid else None

                        if VID and PID:
                            events_table.add_row(
                                f"{event.TimeGenerated:%H:%M:%S}",
                                f"{VID}:{PID}",
                                event.StringInserts[5]
                            )
                        else:
                            _logger.info(
                                f"PnP Event (#{event.RecordNumber}) not added"
                            )
                    events_table.sort("TIME", reverse=True)
                    
                win32event.ResetEvent(self._evt_handle)
        except Exception as e:
            _logger.exception(f"Unexpected error in `monitor_events`: {e}")
        finally:
            win32evtlog.CloseEventLog(self._log_handle)
    

    def on_checkbox_changed(self, message: Checkbox.Changed) -> None:
        """"""
        checkbox = message.checkbox
        if checkbox.value:
            self.device_filters.add(checkbox.label.plain)
        else:
            self.device_filters.remove(checkbox.label.plain)
        _logger.info(f"`device_filters` changed: {self.device_filters}")

    def on_mount(self) -> None:
        """"""
        self.register_theme(GALAXY_THEME)
        self.app.theme = "galaxy"

        container_filters = self.query_one("#container-filters", ItemGrid)
        container_filters.border_title = "Filters"

        container_devices = self.query_one("#container-devices", Container)
        container_devices.border_title = "Connected Devices"

        container_distros = self.query_one("#container-distros", Container)
        container_distros.border_title = "WSL Distributions"

        container_events = self.query_one("#container-events", Container)
        container_events.border_title = "Windows PnP Events"

        device_table = self.query_one("#table-devices", DataTable)
        device_table.add_columns("BUSID", "VID:PID", "DESCRIPTION")
        device_table.add_column("SHARED", key="SHARED")
        device_table.add_column("ATTACHED", key="ATTACHED")

        device_state = usbipd_state()
        for device in device_state["Devices"]:
            if device["BusId"] is None:
                continue
            vid_pid = re.search(USBIPD_VID_PID_PTN, device["InstanceId"])
            VID = vid_pid.group("VID") if vid_pid else "ERROR"
            PID = vid_pid.group("PID") if vid_pid else "ERROR"

            text_style = "italic #FF69B4" if VID == str(USBIF.VID) else ""
            device_table.add_row(
                Text(device["BusId"], style=text_style),
                Text(f"{VID}:{PID}", style=text_style),
                Text(device["Description"], style=text_style),
                Text(str(bool(device["PersistedGuid"])), style=text_style),
                Text(str(bool(device["StubInstanceId"])), style=text_style),
            )
        device_table.sort(
            "SHARED", "ATTACHED", key=lambda x: [i.plain for i in x], reverse=True
        )
        
        installed_distros = wsl_distros()
        if installed_distros.fieldnames:
            columns = [*installed_distros.fieldnames, "DEFAULT"]
        else:
            columns = ["NAME", "STATE", "VERSION", "DEFAULT"]

        distro_table = self.query_one("#table-distros", DataTable)
        distro_table.add_columns(*columns)
        for row in installed_distros:
            distro_table.add_row(*[*row.values(), "*" in row["NAME"]])
        
        events_table = self.query_one("#table-events", DataTable)
        events_table.add_column("TIME", key="TIME")
        events_table.add_columns("VID:PID", "DESCRIPTION")
        self.monitor_events()

    def on_unmount(self) -> None:
        """"""
        self.exit_event.set()
        

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
        win32con.SW_SHOWNORMAL
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
        shell=False
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
            "/failure:enable"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False
    )

    try:
        stdout, stderr = pnp_enabled.communicate(timeout=5)
        if not stdout.lower() == "the command was successfully executed.":
            raise EnablePnPAuditError(stderr)
    except subprocess.TimeoutExpired as e:
        pnp_enabled.kill()
        raise EnablePnPAuditError from e


def usbipd_state() -> USBIPDState:
    """"""
    usbipd_state = subprocess.Popen(
        ["usbipd", "state"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False
    )

    try:
        stdout, stderr = usbipd_state.communicate(timeout=5)
        if stderr:
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
        encoding="UTF-16-LE"
    )

    try:
        stdout, stderr = distros.communicate(timeout=5)
        if stderr:
            raise WSLError(stderr)
    except subprocess.TimeoutExpired as e:
        distros.kill()
        raise WSLError from e

    return csv.DictReader(
        [re.sub(r"(?<!\*)\s+", ",", i.strip()) for i in stdout.strip().splitlines()]
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

    # 'ClosingRecordNumber'
    # 'ComputerName'
    # 'Data'
    # 'EventCategory'
    # 'EventID'
    # 'EventType'
    # 'RecordNumber'
    # 'Reserved'
    # 'ReservedFlags'
    # 'Sid'
    # 'SourceName'
    # 'StringInserts'
    # 'TimeGenerated'
    # 'TimeWritten'

    # {
    #     'BusId': '4-8',
    #     'ClientIPAddress': '172.21.104.105',
    #     'Description': 'USB Serial Device (COM6)',
    #     'InstanceId': 'USB\\VID_2E8A&PID_0005\\E5DC06A4AD2257F6',
    #     'IsForced': False,
    #     'PersistedGuid': '464c029c-c14f-4778-a53c-9dcc552070af',
    #     'StubInstanceId': 'USB\\Vid_80EE&Pid_CAFE\\e5dc06a4ad2257f6'
    # }

    if not is_administrator():
        sys.exit(0) if run_as_administrator() > 32 else sys.exit(1)

    if not is_pnp_audit():
        enable_pnp_audit()

    state = usbipd_state()

    device_uid = f"USB\\VID_{USBIF.VID}&PID_{USBIF.PID_PICO_MICROPYTHON}"
    for device in state["Devices"]:
        if device_uid in device["InstanceId"] and device["BusId"]:
            pprint(f"{device_uid} | {device["InstanceId"]}")

    for i in wsl_distros():
        pprint(i)
    try:
        app = TUI()
        app.run()
        pass
    except KeyboardInterrupt as e:
        pass
    finally:
        pass
