import asyncio
import threading
import textual
import textual.events
import win32con
import win32api
import win32gui

from enum import IntEnum
from logging import basicConfig, getLogger
from textual.app import App
from textual.events import Event
from textual.logging import TextualHandler
from win32con import WM_DEVICECHANGE

LOG_FMT = "%(levelname)-8s | %(funcName)s:%(lineno)d - %(message)s"
basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))
log = getLogger(__name__)


class DBT(IntEnum):
    """Device Broadcast Type enumerations."""
    DEVICE_ARRIVAL = 0x8000
    DEVICE_QUERY_REMOVE = 0x8001
    DEVICE_QUERY_REMOVE_FAILED = 0x8002
    DEVICE_REMOVE_PENDING = 0x8003
    DEVICE_REMOVE_COMPLETE = 0x8004
    DEVICE_TYPE_SPECIFIC = 0x8004

class DeviceNotifier:
    def __init__(self, loop: asyncio.AbstractEventLoop, callback) -> None:
        self._loop = loop
        self._callback = callback
        self._thread = threading.Thread(target=self.message_pump, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def message_pump(self) -> None:

        wc = win32gui.WNDCLASS()
        hinst = win32api.GetModuleHandle(None)
        setattr(wc, "hInstance", hinst)
        setattr(wc, "lpszClassName", self.__class__.__name__)
        setattr(wc, "lpfnWndProc", {WM_DEVICECHANGE: self.process_message})
        class_atom = win32gui.RegisterClass(wc)

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
        
        win32gui.PumpMessages()

    def process_message(self, hwnd, msg, wparam, lparam) -> int:
        """"""
        log.info(msg)
        match wparam:
            case DBT.DEVICE_ARRIVAL:
                # Schedule the callback on the main asyncio loop
                self._loop.call_soon_threadsafe(self._callback, "connected")
            case DBT.DEVICE_REMOVE_COMPLETE:
                self._loop.call_soon_threadsafe(self._callback, "disconnected")
            case _:
                log.info(f"Unrecognised device-change event - {msg}")
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

# In the Textual App:
class MyApp(App):
    def on_test_event(self, event: Event) -> None:
        # This is where the callback from the notifier would be handled
        # to update the application state.
        pass
        
    def on_mount(self) -> None:
        loop = asyncio.get_running_loop()
        def device_change_handler(status: str):
            # This function runs in the main thread
            log.info(f"Device event received: {status}")
            # Here, you would update the application state
            # which would then trigger a UI refresh.
        self.notifier = DeviceNotifier(loop, device_change_handler)
        self.notifier.start()


if __name__=='__main__':
    try:
        app = MyApp()
        app.run()
    except KeyboardInterrupt as e:
        log.info("Caught `KeyboardInterrupt` - TUI shutdown")

