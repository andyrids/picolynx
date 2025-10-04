""""""

import asyncio
import contextvars
import ctypes
import logging
import threading
import sys
from asyncio.windows_events import NULL
from contextvars import ContextVar
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import IntEnum
from functools import lru_cache
from typing import Callable, ClassVar, Optional, TYPE_CHECKING
from xxlimited import new

import win32api
import win32con
import win32ctypes.pywin32
import win32gui
import winerror

from picolynx import __version__
from picolynx.commands import *
from picolynx.components import TUIHeader, TUINavigation
from picolynx.exceptions import USBIPDError, WSLError
from picolynx.utility import LOG_FMT, is_administrator
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
from textual.widgets import DataTable
from textual._path import CSSPathType
from win32ctypes.pywin32 import pywintypes

logging.basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))

LRESULT = ctypes.c_ssize_t
UMSG = ctypes.c_uint
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, UMSG, WPARAM, LPARAM)

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer
    from _win32typing import PyEventLogRecord  # pyright: ignore[reportMissingModuleSource]


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
    connected_devices: list[USBIPDState] = field(default_factory=list)


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
            callback: Callable[[DBCEvent, str], None]
        ) -> None:
        """Initialises the `DeviceNotifier` class.

        Args:
            loop: The running event loop.

            callback: A callback, which will receive the `WM_DEVICECHANGE`
                event message `wparam` & `dbcp_name` of the port device.
        """
        self._loop = loop
        self._callback = callback
        self._thread = threading.Thread(target=self.message_pump, daemon=True)
        self._hwnd_ready = threading.Event()
        self._hwnd = None
        self._log = logging.getLogger(self.__class__.__name__)
        #self._log.addHandler(TextualHandler())
    
    @property
    def callback(self) -> Callable[[DBCEvent, str], None]:
        """Message callback function property."""
        return self._callback

    @property
    def hwnd(self) -> int | None:
        """Window handle property."""
        return self._hwnd
    
    @hwnd.deleter
    def hwnd(self) -> None:
        """Deletes the window handle property."""
        del self._hwnd

    @hwnd.setter
    def hwnd(self, window_handle: int | None) -> None:
        """Sets the window handle property."""
        if window_handle == NULL:
            raise RuntimeError("Window handle (`hwnd`) is NULL")
        self._hwnd = window_handle
        self._hwnd_ready.set()

    @property
    def log(self) -> logging.Logger:
        """Logger property."""
        return self._log

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Running event loop property."""
        return self._loop

    @property
    def thread(self) -> threading.Thread:
        """Message pump thread property."""
        return self._thread

    def call_soon_threadsafe(
            self, callback: Callable[[DBCEvent, str], None], *args
        ) -> None:
        """Schedules a function call on the running event loop.

        Args:
            callback: A callback, which will receive the `wparam` & `lparam`
                from the `WM_DEVICECHANGE` event message.
        """
        self.loop.call_soon_threadsafe(callback, *args)

    def start(self) -> None:
        """Starts the `message_pump` thread.
        
        Raises:
            RuntimeError: On failure to start `win32gui.PumpMessages`.
        """
        # self.log.info("Starting `win32gui.PumpMessages`")
        self.thread.start()
        if not self._hwnd_ready.wait(timeout=5):
            raise RuntimeError("Failed to start `win32gui.PumpMessages`")

    def stop(self) -> None:
        """Stops the `message_pump` thread & initiates cleanup actions.
        
        1. Post `WM_CLOSE` message
        2. on `WM_CLOSE` -> `win32gui.DestroyWindow()`
        2. on `WM_DESTROY` -> `win32gui.PostQuitMessage(0)`
        """
        # self.log.info("Stopping `win32gui.PumpMessages`")
        if self.hwnd is not None:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, NULL, NULL)
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.log.warning("Thread did not exit correctly")
        else:
            self.log.warning("Window handle not set, cannot post `WM_CLOSE`")

    def create_window(self) -> None:
        """Creates a Windows message-only window."""
        wc = win32gui.WNDCLASS()
        hinst = win32api.GetModuleHandle(None)
        setattr(wc, "hInstance", hinst)
        setattr(wc, "lpszClassName", self.__class__.__name__)
        setattr(wc, "lpfnWndProc", WNDPROCTYPE(self.window_proc))
        class_atom = win32gui.RegisterClass(wc)
        # create a new window
        self.hwnd = win32gui.CreateWindow(
            class_atom, # class name
            "Device Change Demo", # window title
            NULL, # style
            NULL, # x
            NULL, # y
            win32con.CW_USEDEFAULT, # width
            win32con.CW_USEDEFAULT, # height
            NULL, # parent
            NULL, # menu
            hinst, # hinstance
            None # reserved
        )

    def message_pump(self) -> None:
        """Runs a message loop for Windows messages."""
        try:
            self.create_window()
            # infinite, blocking loop
            win32gui.PumpMessages()
        except Exception as e:
            self.log.exception(e)
            self._hwnd_ready.set()
        finally:
            self._hwnd = None

    def window_proc(
            self,
            hwnd: int,
            umsg: int,
            wparam: int,
            lparam: int
        ) -> int:
        """Processes Windows messages from the `message_pump`.
        
        Args:
            hwnd: A handle to the window class.

            umsg: The Windows message code.

            wparam: Additional message-specific data.

            lparam: A pointer to a message-specific structure.
        """
        self.log.debug(f"{umsg=:04X}, {wparam=:04X}, {lparam=:04X}")
        try:
            match umsg:
                # on `WM_DEVICECHANGE` without a NULL `lparam`
                case win32con.WM_DEVICECHANGE if lparam:
                    self.process_device_change(umsg, wparam, lparam)
                case win32con.WM_CLOSE | win32con.WM_DESTROY:
                    self.process_cleanup(hwnd, umsg, wparam, lparam)
                case _:
                    pass
        except Exception as e:
            self.log.exception(e)
        finally:
            return win32gui.DefWindowProc(hwnd, umsg, wparam, lparam)

    def process_cleanup(
            self,
            hwnd: int,
            umsg: int,
            wparam: int,
            lparam: int
        ) -> None:
        """Runs cleanup actions on `WM_CLOSE` & `WM_DESTROY` messages.

        Args:
            hwnd: A handle to the window class.

            umsg: The Windows message code.

            wparam: Additional message-specific data.

            lparam: A pointer to a message-specific structure.
        """
        self.log.debug(f"{umsg=:04X}, {wparam=:04X}, {lparam=:04X}")
        match umsg:
            case win32con.WM_CLOSE:
                self.log.info("Closing `win32gui.WNDCLASS`")
                win32gui.DestroyWindow(hwnd)
            case win32con.WM_DESTROY:
                self.log.info("Destroying `win32gui.WNDCLASS`")
                del self.hwnd
                win32gui.PostQuitMessage(0)
            case _:
                self.log.debug("Unexpected `umsg`")

    def process_device_change(
            self,
            umsg: int,
            wparam: int,
            lparam: int
        ) -> None:
        """Processes `WM_DEVICECHANGE` messages.

        Callbacks are scheduled on the main asyncio loop via the
        `call_soon_threadsafe` method of the running event loop.

        Args:
            wparam: Additional message-specific data.

            lparam: A pointer to a message-specific structure.

        Returns:
            Message processing result, which depends on the message.
        """
        try:
            if umsg != win32con.WM_DEVICECHANGE:
                self.log.error(f"Expected `WM_DEVICECHANGE` ({umsg=:04X})")
                return

            self.log.info(f"`WM_DEVICECHANGE` - {wparam=:04X}, {lparam=:04X}")

            def post_devtype_port_message(
                    wparam: DBCEvent, lparam: int
                ) -> None:
                """Calls TUI callback if device type is `DBT_DEVTYP_PORT`."""
                hdr = DEV_BROADCAST_HDR.from_address(lparam)
                if hdr.dbch_devicetype == DBCDeviceType.DBT_DEVTYP_PORT:
                    interface = DEV_BROADCAST_PORT_W.from_address(lparam)
                    dbcp_name = ctypes.wstring_at(
                        ctypes.addressof(interface) +
                        DEV_BROADCAST_PORT_W.dbcp_name.offset
                    )
                    if not callable(self.callback):
                        self.log.error("Callback attribute is not callable")
                        return
                    self.call_soon_threadsafe(
                        self.callback, wparam, dbcp_name
                    )

            match wparam:
                case DBCEvent.DBT_DEVNODES_CHANGED:
                    self.log.info("`DBT_DEVNODES_CHANGED`")
                case DBCEvent.DBT_DEVICEARRIVAL if lparam:
                    post_devtype_port_message(wparam, lparam)
                case DBCEvent.DBT_DEVICEREMOVECOMPLETE if lparam:
                    post_devtype_port_message(wparam, lparam)
                case _:
                    self.log.warning("Unhandled device-change event")
        except Exception as e:
            self.log.exception(e)


class TUI(App):
    """Main `textual` TUI."""

    BINDINGS: ClassVar[list[BindingType]] = [("d", "dark_mode", "Dark mode")]

    CSS_PATH: ClassVar[CSSPathType | None] = "app.tcss"

    TITLE: str | None = "TITLE"

    SUB_TITLE: str | None = "SUBTITLE"

    def __init__(self, log_level: int = logging.INFO) -> None:
        """Initialises TUI App."""
        super().__init__()
        self._connected_devices: set[str] = set()
        self._exit_event: threading.Event = threading.Event()
        self._notifier = None
        self._device_locks: dict[str, threading.Lock] = {}
        self._thread_lock: threading.Lock = threading.Lock()
        self._cached_devices: dict[str, USBIPDDevice] = {}
        self.__log = logging.getLogger(self.__class__.__name__)
        self.__log.setLevel(log_level)

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
    def device_locks(self) -> dict[str, threading.Lock]:
        """Property for device threading lock."""
        return self._device_locks

    @property
    def exit_event(self) -> threading.Event:
        """Property for threading exit `Event`."""
        return self._exit_event

    @property
    def notifier(self) -> DeviceNotifier:
        """Property for `DeviceNotifier` instance.

        Raises:
            AttributeError: On missing `_notifier` attribute.
        """
        if self._notifier is None:
            raise AttributeError(
                "Expected `self._notifier` set to `DeviceNotifier`"
            )
        return self._notifier

    @property
    @lru_cache(1)
    def table_connected(self) -> DataTable:
        """Property for connected devices `DataTable` widget."""
        return self.query_one("#table-connected", DataTable)

    @property
    @lru_cache(1)
    def table_persisted(self) -> DataTable:
        """Property for Windows events `DataTable` widget."""
        return self.query_one("#table-persisted", DataTable)
    
    @property
    def thread_lock(self) -> threading.Lock:
        """Property for threading lock."""
        return self._thread_lock

    def compose(self) -> ComposeResult:
        yield TUIHeader()
        with Container(id="container-main"):
            yield TUINavigation()

    def on_mount(self) -> None:
        """Handles TUI `mount` event."""

        self.register_theme(GALAXY_THEME)
        self.app.theme = "galaxy"

        self.initial_populate_devices()

        running_loop = asyncio.get_running_loop()        
        self._notifier = DeviceNotifier(running_loop, self.handle_wm_events)
        self.notifier.start()

    def initial_populate_devices(self) -> None:
        """"""
        self.table_connected.clear()

        new_cache: dict[str, USBIPDDevice] = {}]
        for device in run_usbipd_state():
            if device.busid:
                new_cache[device.busid] = device
                row = self.parse_device_to_row(device)
                self.table_connected.add_row(row, key=device.busid)
        self._cached_devices = new()


    def on_unmount(self) -> None:
        """Handles TUI `unmount` event."""
        self.notifier.stop()
        self.exit_event.set()

    @on(USBIPDAttachDevice)
    def handle_attach_device(self, message: USBIPDAttachDevice) -> None:
        """forwards `USBIPDAttachDevice` messages to a dedicated worker."""
        if not message.device.isattached:
            self.worker_attach_device(message)
    
    @on(USBIPDDetachDevice)
    def handle_detach_device(self, message: USBIPDDetachDevice) -> None:
        """forwards `USBIPDDetachDevice` messages to a dedicated worker."""
        self.worker_detach_device(message)

    @on(WMDeviceChange)
    def handle_device_change(self, message: WMDeviceChange) -> None:
        """_summary_

        Args:
            message: _description_

        Returns:
            _description_
        """
        self.update_table_devices()

    @work(thread=True)
    def worker_attach_device(self, message: USBIPDAttachDevice) -> None:
        """Handles blocking `usbipd_bind` & `usbipd_attach` calls.

        Args:
            message: Device information message for `usbipd attach` command.
        """
        if not (busid := message.device.busid):
            return
        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not device_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            connected_devices = run_usbipd_state()
            for device in connected_devices:
                match device:
                    # `busid` matches, but device is not bound or attached
                    case USBIPDDevice(busid=busid, isbound=False) if busid:
                        run_usbipd_bind(busid)
                        run_usbipd_attach(busid)
                        break
                    # `busid` matches, but device is bound & not attached
                    case USBIPDDevice(busid=busid, isattached=False) if busid:
                        run_usbipd_attach(busid)
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            device_lock.release()

    @work(thread=True)
    def worker_detach_device(self, message: USBIPDDetachDevice) -> None:
        """Handles blocking `usbipd_detach` calls.

        Args:
            message: Device information message for `usbipd attach` command.
        """
        if not (busid := message.device.busid):
            return

        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            device_lock = self.device_locks.setdefault(busid, threading.Lock())

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not device_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            connected_devices = run_usbipd_state()
            for device in connected_devices:
                match device:
                    # `busid` matches & device is attached
                    case USBIPDDevice(busid=busid, isattached=True) if busid:
                        run_usbipd_detach(busid)
                        break
                    # `busid` matches, but device is not attached
                    case USBIPDDevice(busid=busid, isattached=False) if busid:
                        self.__log.info(f"Missing device @ BUSID {busid}")
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            device_lock.release()

    def parse_usbipd_state(
            self, connected_devices: list[USBIPDDevice]
        ) -> list[list[Text]]:
        """Parses device information in `usbipd state` output.

        Args:
            usbipd_state: Current state of all connected USB devices.

        Returns:
            A list of Text objects for use in a `DataTable` widget.
        """
        parsed_devices = []
        for dev in connected_devices:
            if dev.busid is None:
                if dev.isattached:
                    self.post_message(USBIPDDetachDevice(dev))
                continue

            md = ""
            parsed_devices.append(
                [
                    Text(dev.description, style=md, overflow="ellipsis"),
                    Text(f"{dev.busid}", style=md, justify="center"),
                    Text(f"{dev.vid}:{dev.pid}", style=md, justify="center"),
                    Text(f"{dev.isbound}", style=md, justify="center"),
                    Text(f"{dev.isattached}", style=md, justify="center"),
                ]
            )

        return parsed_devices

    def update_table_devices(
            self, usbipd_state: Optional[list[USBIPDDevice]] = None
        ) -> None:
        """Updates connected USB device information `DataTable`."""

        self.table_connected.clear()
        self.table_connected.add_rows(
            self.parse_usbipd_state(usbipd_state or run_usbipd_state())
        )


    def handle_wm_events(self, wparam: DBCEvent, name: str) -> None:
        """Handles `WM_DEVICECHANGE` messages receipt.

        Args:
            device_event: The device event from a `WM_DEVICECHANGE` message.
        """
        self.__log.info(f"`WM_DEVICECHANGE` message ({wparam=:04X})")
        try:
            self.post_message(WMDeviceChange(wparam))
        except LookupError as e:
            self.__log.exception(e)


if __name__ == "__main__":
    if not is_administrator():
        # any nonzero value is considered 'abnormal termination'
        sys.exit(NULL) if run_as_administrator() else sys.exit(1)
    try:
        app = TUI()
        app.run()
    except KeyboardInterrupt as e:
        pass
    finally:
        run_usbipd_detach()
