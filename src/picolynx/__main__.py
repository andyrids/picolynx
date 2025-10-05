""""""

import asyncio
import contextvars
import ctypes
import logging
import threading
import sys
from asyncio.windows_events import NULL
from collections import defaultdict
from contextvars import ContextVar
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import IntEnum
from functools import lru_cache
from threading import Lock
from typing import Callable, ClassVar, Optional, TYPE_CHECKING, TypeAlias

import win32api
import win32con
import win32ctypes.pywin32
import win32gui
import winerror

from picolynx import __version__
from picolynx.commands import *
from picolynx.components import (
    ConnectedTable, PersistedTable, TUIFooter, TUIHeader, TUINavigation
)
from picolynx.exceptions import USBIPDError, WSLError
from picolynx.utility import LOG_FMT, is_administrator
from picolynx.structures import *
from picolynx.themes import GALAXY_THEME

from pywintypes import error as PyWinError
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Container
from textual.widgets.data_table import RowKey
from textual.logging import TextualHandler
from textual.message import Message
from textual.reactive import reactive
from textual._path import CSSPathType
from win32ctypes.pywin32 import pywintypes

logging.basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))

LockCache: TypeAlias = defaultdict[str, threading.Lock]

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
class USBIPDBindDevice(Message):
    """Device information message for `usbipd attach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDDetachDevice(Message):
    """Device information message for `usbipd detach` command."""

    device: USBIPDDevice


@dataclass
class USBIPDUnbindDevice(Message):
    """Device information message for `usbipd unbind` command."""

    device: USBIPDDevice


@dataclass
class WMDeviceChange(Message):
    """`WM_DEVICECHANGE` message for refreshing connected device state."""

    broadcast_type: int
    broadcast_port: str


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
    """Main application TUI."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("a", "manual_attach", "attach"),
        ("b", "manual_bind", "bind"),
        ("d", "manual_detach", "detach"),
        ("u", "manual_unbind", "unbind"),
    ]

    CSS_PATH: ClassVar[CSSPathType | None] = "app.tcss"

    def __init__(self, log_level: int = logging.INFO) -> None:
        """Initialises TUI App."""
        super().__init__()
        self._connection_cache: dict[str, USBIPDDevice] = {}
        self._usbipd_lock_map: LockCache = defaultdict(threading.Lock)
        self._thread_lock: threading.Lock = threading.Lock()
        self._thread_exit: threading.Event = threading.Event()
        self.__log = logging.getLogger(self.__class__.__name__)
        self.__log.setLevel(log_level)

    @property
    def usbipd_lock_map(self) -> LockCache:
        """Property for device threading lock."""
        return self._usbipd_lock_map

    @property
    def thread_exit(self) -> threading.Event:
        """Property for threading exit `Event`."""
        return self._thread_exit

    @property
    @lru_cache(1)
    def table_connected(self) -> ConnectedTable:
        """Property for connected devices `DataTable` widget."""
        return self.query_one("#table-connected", ConnectedTable)

    @property
    @lru_cache(1)
    def table_persisted(self) -> PersistedTable:
        """Property for Windows events `DataTable` widget."""
        return self.query_one("#table-persisted", PersistedTable)
    
    @property
    def thread_lock(self) -> threading.Lock:
        """Property for threading lock."""
        return self._thread_lock

    def device_from_selected(
            self, row_key: RowKey | None
        ) -> USBIPDDevice | None:
        """Retrieves device from the cache using selected row busid key.

        Args:
            row_key: The `RowKey` for the selected `DataTable` row, which is
                set to the Bus ID of a device.

        Returns:
            A `USBIPDDevice`, if busid was in the cache or `None`.
        """
        if row_key and isinstance(row_key.value, str):
                return self._connection_cache.get(row_key.value)
        return None

    def action_manual_attach(self) -> None:
        """"""
        selected_row_key = self.table_connected.row_selected_key
        if device := self.device_from_selected(selected_row_key):
            self.__log.info(f"Manual attach @ BUSID {device.busid}")
            self.post_message(USBIPDAttachDevice(device))

    def action_manual_bind(self) -> None:
        """"""
        selected_row_key = self.table_connected.row_selected_key
        if device := self.device_from_selected(selected_row_key):
            self.__log.info(f"Manual bind @ BUSID {device.busid}")
            self.post_message(USBIPDBindDevice(device))
    
    def action_manual_detach(self) -> None:
        selected_row_key = self.table_connected.row_selected_key
        if device := self.device_from_selected(selected_row_key):
            self.__log.info(f"Manual detach @ BUSID {device.busid}")
            self.post_message(USBIPDDetachDevice(device))

    def action_manual_unbind(self) -> None:
        """"""
        selected_row_key = self.table_connected.row_selected_key
        if device := self.device_from_selected(selected_row_key):
            self.__log.info(f"Manual unbind @ BUSID {device.busid}")
            self.post_message(USBIPDUnbindDevice(device))

    def compose(self) -> ComposeResult:
        yield TUIHeader(id="header")
        with Container(id="container-main"):
            yield TUINavigation()
        yield TUIFooter(id="footer")

    def on_mount(self) -> None:
        """Handles TUI `mount` event."""
        self.register_theme(GALAXY_THEME)
        self.app.theme = "galaxy"

        self.initial_populate_devices()

        running_loop = asyncio.get_running_loop()        
        self._notifier = DeviceNotifier(running_loop, self.handle_wm_events)
        self._notifier.start()

    def get_connected_row(self, device: USBIPDDevice) -> list[Text]:
        """"""
        md = ""
        return [
            Text(device.description, style=md, overflow="ellipsis"),
            Text(f"{device.busid}", style=md, justify="center"),
            Text(f"{device.vid}:{device.pid}", style=md, justify="center"),
            Text(f"{device.isbound}", style=md, justify="center"),
            Text(f"{device.isattached}", style=md, justify="center"),
        ]

    def get_persisted_row(self, device: USBIPDDevice) -> list[Text]:
        """"""
        md = ""
        return [
            Text(device.description, style=md, overflow="ellipsis"),
            Text(f"{device.persistedguid}", style=md, justify="center"),
        ]

    @on(USBIPDAttachDevice)
    def handle_attach_device(self, msg: USBIPDAttachDevice) -> None:
        """Forwards `USBIPDAttachDevice` messages to a dedicated worker.
        
        Args:
            msg: A `USBIPDAttachDevice` message.
        """
        if not msg.device.isattached:
            self.worker_attach_device(msg)

    @on(USBIPDBindDevice)
    def handle_bind_device(self, msg: USBIPDBindDevice) -> None:
        """Forwards `USBIPDAttachDevice` messages to a dedicated worker.
        
        Args:
            msg: A `USBIPDAttachDevice` message.
        """
        if not msg.device.isattached:
            self.worker_bind_device(msg)
    
    @on(USBIPDDetachDevice)
    def handle_detach_device(self, msg: USBIPDDetachDevice) -> None:
        """forwards messages to a dedicated worker.

        Args:
            msg: A `USBIPDDetachDevice` message.
        """
        self.worker_detach_device(msg)

    @on(USBIPDUnbindDevice)
    def handle_unbind_device(self, msg: USBIPDUnbindDevice) -> None:
        """forwards messages to a dedicated worker.

        Args:
            msg: A `USBIPDUnbindDevice` message.
        """
        self.worker_unbind_device(msg)

    @on(WMDeviceChange)
    def handle_device_change(self, message: WMDeviceChange) -> None:
        """_summary_

        Args:
            message: _description_

        Returns:
            _description_
        """
        self.__log.info("Triggering incremental device update")
        self.incremental_device_update()

    def handle_wm_events(self, wparam: DBCEvent, name: str) -> None:
        """Handles Windows messages from `DeviceNotifier`.

        Args:
            device_event: A device broadcast message code.
        """

        event_name = next(filter(lambda x: x == wparam, DBCEvent)).name
        self.__log.info(f"`{event_name}` ({wparam:04X}) - {name}")
        try:
            self.post_message(WMDeviceChange(wparam, name))
        except LookupError as e:
            self.__log.exception(e)

    def incremental_device_update(self) -> None:
        """"""
        self.__log.info("Incremental `DataTable` update")

        current_connections = {
            dev.busid: dev for dev in run_usbipd_state() if dev.busid
        }

        new_busids  = set(current_connections.keys())
        old_busids = set(self._connection_cache.keys())

        updated_busids = set()
        for busid in old_busids.intersection(new_busids):
            # pydantic model comparison
            if self._connection_cache[busid] != current_connections[busid]:
                updated_busids.add(busid)
                self.__log.info(f"Detected device update @ {busid=}")

        # removed devices
        for busid in old_busids.difference(new_busids):
            try:
                self.table_connected.remove_row(busid)
                if self.table_persisted.rows.get(RowKey(busid)):
                    self.table_persisted.remove_row(busid)
                self.__log.info(f"Removed row @ {busid=}")
            except KeyError as e:
                self.__log.warning(f"Missing row @ {busid=}", exc_info=True)

        # added devices
        for busid in new_busids.difference(old_busids):
            new_device = current_connections[busid]
            con_row = self.get_connected_row(new_device)
            self.table_connected.add_row(*con_row, key=busid)
            per_row = self.get_persisted_row(new_device)
            self.table_persisted.add_row(*per_row, key=busid)
            self.__log.info(f"Added row @ {busid=}")

        # updated devices
        for busid in updated_busids:
            row = self.get_connected_row(current_connections[busid])
            for key, value in enumerate(row, start=1):
                self.table_connected.update_cell(busid, str(key), value)
            self.__log.info(f"Updated row @ {busid=}")
        self._connection_cache = current_connections
    
    def initial_populate_devices(self) -> None:
        """"""
        self.table_connected.clear()

        new_cache = {d.busid: d for d in run_usbipd_state() if d.busid}
        for busid, device in new_cache.items():
            con_row = self.get_connected_row(device)
            self.table_connected.add_row(*con_row, key=busid)
            if device.isbound:
                per_row = self.get_persisted_row(device)
                self.table_persisted.add_row(*per_row, key=busid)
        self._connection_cache = new_cache

    def on_unmount(self) -> None:
        """Handles TUI `unmount` event."""
        self._notifier.stop()
        self.thread_exit.set()

    @work(thread=True)
    def worker_attach_device(self, msg: USBIPDAttachDevice) -> None:
        """Handles blocking `run_usbipd_bind` & `run_usbipd_attach` calls.

        Args:
            msg: Device information message for `usbipd` commands.
        """
        device = msg.device
        if not device.busid:
            return
 
        # mitigate `usbipd_lock_map` race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            usbipd_lock = self.usbipd_lock_map[device.busid]

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not usbipd_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            for connected_device in run_usbipd_state():
                match connected_device:
                    # `busid` matches, but device is not bound or attached
                    case USBIPDDevice(busid=device.busid, isbound=False):
                        run_usbipd_bind(device.busid)
                        run_usbipd_attach(device.busid)
                        break
                    # `busid` matches, but device is bound & not attached
                    case USBIPDDevice(busid=device.busid, isattached=False):
                        run_usbipd_attach(device.busid)
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            usbipd_lock.release()
            self.incremental_device_update()
    
    @work(thread=True)
    def worker_bind_device(self, msg: USBIPDBindDevice) -> None:
        """Handles blocking `run_usbipd_bind` calls.

        Args:
            msg: Device information message for `usbipd` commands.
        """
        device = msg.device
        if not device.busid:
            return
 
        # mitigate `usbipd_lock_map` race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            usbipd_lock = self.usbipd_lock_map[device.busid]

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not usbipd_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            for connected_device in run_usbipd_state():
                match connected_device:
                    # `busid` matches, but device is not bound or attached
                    case USBIPDDevice(busid=device.busid, isbound=False):
                        run_usbipd_bind(device.busid)
                        run_usbipd_attach(device.busid)
                        break
                    # `busid` matches, but device is bound & not attached
                    case USBIPDDevice(busid=device.busid, isattached=False):
                        self.__log.info("Device already bound & attached")
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            usbipd_lock.release()
            self.incremental_device_update()

    @work(thread=True)
    def worker_detach_device(self, msg: USBIPDDetachDevice) -> None:
        """Handles blocking `run_usbipd_detach` calls.

        Args:
            msg: Device information message for `usbipd` commands.
        """
        device = msg.device
        if not device.busid:
            return

        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            usbipd_lock = self.usbipd_lock_map[device.busid]

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not usbipd_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            for connected_device in run_usbipd_state():
                match connected_device:
                    # `busid` matches & device is attached
                    case USBIPDDevice(busid=device.busid, isattached=True):
                        run_usbipd_detach(device.busid)
                        break
                    # `busid` matches, but device is not attached
                    case USBIPDDevice(busid=device.busid, isattached=False):
                        self.__log.info(f"Missing device @ BUSID {device.busid}")
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            usbipd_lock.release()

    @work(thread=True)
    def worker_unbind_device(self, msg: USBIPDUnbindDevice) -> None:
        """Handles blocking `run_usbipd_unbind` calls"""

        device = msg.device
        if not device.busid:
            return

        # mitigate `device_locks` dict race condition
        with self.thread_lock:
            # dict CRUD is now atomic
            usbipd_lock = self.usbipd_lock_map.setdefault(
                device.busid, threading.Lock()
            )

        # lock mitigates `usbipd_bind` & `usbipd_attach` race conditions
        if not usbipd_lock.acquire(blocking=False):
            # return early if lock is already held
            return

        # mitigate `usbipd_bind` & `usbipd_attach` race conditions
        try:
            for connected_device in run_usbipd_state():
                match connected_device:
                    # `busid` matches, but device is bound & attached
                    case USBIPDDevice(busid=device.busid, isattached=True):
                        run_usbipd_detach(device.busid)
                        run_usbipd_unbind(device.busid)
                        break
                    # `busid` matches, & device is bound
                    case USBIPDDevice(busid=device.busid, isbound=True):
                        run_usbipd_unbind(device.busid)
                        break
                    # `busid` matches, but device is not bound
                    case USBIPDDevice(busid=device.busid, isbound=False):
                        self.__log.info(f"Missing device @ BUSID {device.busid}")
                        break
                    case _:
                        continue
        except USBIPDError as e:
            self.__log.exception(e)
        finally:
            usbipd_lock.release()
            self.incremental_device_update()


if __name__ == "__main__":
    if not is_administrator():
        # a nonzero value is considered 'abnormal' termination
        sys.exit(NULL) if run_as_administrator() else sys.exit(1)
    try:
        app = TUI()
        app.run()
    except KeyboardInterrupt as e:
        pass
    finally:
        pass
        # run_usbipd_detach()
