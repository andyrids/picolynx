import asyncio
from contextvars import Context
import logging
from typing import Any, Self
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from textual import events
from textual.widgets.data_table import RowKey
from picolynx.__main__ import (
    DeviceNotifier,
    TUI,
    USBIPDAttach,
    USBIPDBind,
    USBIPDDetach,
    USBIPDUnbind,
)
from picolynx.commands import USBIPDDevice
from picolynx.components import ConnectedTable, PersistedTable

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("picolynx").setLevel(logging.DEBUG)
logging.getLogger("DeviceNotifier").setLevel(logging.DEBUG)
logging.getLogger("TUI").setLevel(logging.DEBUG)

DEVICE_DESC = "USB Serial Device (COM1)"
DEVICE_BUSID = "1-1"

DEVICE_2_DESC = "USB Serial Device (COM2)"
DEVICE_2_BUSID = "2-2"

DEVICE_3_DESC = "USB Serial Device (COM3)"
DEVICE_3_BUSID = "3-3"


@pytest.mark.asyncio
async def test_device_notifier_init() -> None:
    """Tests `DeviceNotifier.__init__`."""
    with pytest.raises(ValueError):
        DeviceNotifier(loop=asyncio.get_running_loop(), callback=None)  # type: ignore


@pytest.mark.asyncio
async def test_device_notifier_start_and_stop(
    event_loop: asyncio.AbstractEventLoop, callback: MagicMock, patch_win32
) -> None:
    """Tests `DeviceNotifier.start` & `DeviceNotifier.stop`."""
    notifier = DeviceNotifier(event_loop, callback)
    patch_start = patch.object(notifier.thread, "start")
    patch_wait = patch.object(notifier._hwnd_ready, "wait", return_value=True)

    with patch_start as mock_start, patch_wait as mock_wait:
        notifier.start()
        mock_start.assert_called_once()
        mock_wait.assert_called_once()

    # valid `hwnd`
    with patch.object(notifier.thread, "join") as mock_join:
        notifier._hwnd = 123
        notifier.stop()
        mock_join.assert_called_once()

    # invalid `hwnd`
    notifier._hwnd = None
    with patch.object(notifier.log, "warning") as mock_warn:
        notifier.stop()
        mock_warn.assert_called_with(
            "Window handle not set, cannot post `WM_CLOSE`"
        )


def test_device_notifier_hwnd_property(
    event_loop: asyncio.AbstractEventLoop, callback: MagicMock
) -> None:
    """Tests `DeviceNotifier.hwnd`."""
    notifier = DeviceNotifier(event_loop, callback)
    # test setter with valid value
    notifier.hwnd = 42
    assert notifier.hwnd == 42
    # test deleter
    del notifier.hwnd
    assert not hasattr(notifier, "_hwnd")
    # test setter with NULL/None
    with pytest.raises(RuntimeError):
        notifier.hwnd = None


def test_device_notifier_call_soon_threadsafe(
    event_loop: asyncio.AbstractEventLoop, callback: MagicMock
) -> None:
    """Tests `DeviceNotifier.call_soon_threadsafe`."""
    notifier = DeviceNotifier(event_loop, callback)
    called = []

    def cb(arg1, arg2) -> None:
        called.append((arg1, arg2))

    def call_soon_threadsafe(
        callback, *args, context: Context | None = None
    ) -> Any:
        return callback(*args)

    event_loop.call_soon_threadsafe = call_soon_threadsafe
    notifier.call_soon_threadsafe(cb, 1, "ABC")
    assert called == [(1, "ABC")]


def test_device_notifier_create_window_sets_hwnd(
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
    patch_win32: None,
) -> None:
    """Tests `DeviceNotifier.create_window`."""
    notifier = DeviceNotifier(event_loop, callback)
    notifier.create_window()

    # patched CreateWindow returns 3
    assert notifier.hwnd == 3


def test_device_notifier_message_pump_success_and_exception(
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
    patch_win32: None,
) -> None:
    """Tests `DeviceNotifier.message_pump`."""
    notifier = DeviceNotifier(event_loop, callback)

    # success path
    notifier.create_window = MagicMock()
    with patch("win32gui.PumpMessages", side_effect=[None]):
        notifier.message_pump()

    # exception path
    notifier.create_window = MagicMock(side_effect=Exception("fail"))
    with patch.object(notifier.log, "exception") as mock_exc:
        notifier.message_pump()
        mock_exc.assert_called()

    assert notifier._hwnd is None


def test_device_notifier_window_proc_branches(
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
    patch_win32: None,
) -> None:
    """Tests `DeviceNotifier.process_device_change` branches."""
    notifier = DeviceNotifier(event_loop, callback)
    notifier._log = MagicMock()
    notifier.process_device_change = MagicMock()
    notifier.process_cleanup = MagicMock()

    # WM_DEVICECHANGE with lparam
    notifier.window_proc(1, 0x0219, 0, 1)
    notifier.process_device_change.assert_called_once()

    # WM_CLOSE
    notifier.process_cleanup.reset_mock()
    notifier.window_proc(1, 0x0010, 0, 0)
    notifier.process_cleanup.assert_called_once()

    # WM_DESTROY
    notifier.process_cleanup.reset_mock()
    notifier.window_proc(1, 0x0002, 0, 0)
    notifier.process_cleanup.assert_called_once()

    # default
    notifier.process_cleanup.reset_mock()
    notifier.process_device_change.reset_mock()
    assert notifier.window_proc(1, 0x9999, 0, 0) == 0

    # Exception in handler
    notifier.process_device_change.side_effect = Exception("fail")
    with patch.object(notifier.log, "exception") as mock_exc:
        notifier.window_proc(1, 0x0219, 0, 1)
        mock_exc.assert_called()


def test_device_notifier_process_cleanup_branches(
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
    patch_win32: None,
) -> None:
    """Tests `DeviceNotifier.process_cleanup`."""
    notifier = DeviceNotifier(event_loop, callback)
    notifier._log = MagicMock()

    # WM_CLOSE
    with patch("win32gui.DestroyWindow") as mock_destroy:
        notifier.process_cleanup(1, 0x0010, 0, 0)
        mock_destroy.assert_called_once()

    # WM_DESTROY
    with patch("win32gui.PostQuitMessage") as mock_postquit:
        notifier.hwnd = 123
        notifier.process_cleanup(1, 0x0002, 0, 0)
        mock_postquit.assert_called_once()

    # default
    notifier.process_cleanup(1, 0x9999, 0, 0)
    notifier._log.debug.assert_called()


def test_device_notifier_process_device_change_branches(
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
    patch_win32: None,
) -> None:
    """Tests `DeviceNotifier.process_device_change`."""

    notifier = DeviceNotifier(event_loop, callback)
    notifier._log = MagicMock()
    notifier.call_soon_threadsafe = MagicMock()

    # not `WM_DEVICECHANGE`
    notifier.process_device_change(0x9999, 0, 0)
    notifier._log.error.assert_called()

    # `DBT_DEVICEARRIVAL`
    notifier._get_devtype_friendly_name = MagicMock(return_value="COM1")
    notifier.process_device_change(0x0219, 0x8000, 1)
    notifier.call_soon_threadsafe.assert_called()
    
    # `DBT_DEVICEREMOVECOMPLETE`
    notifier._get_devtype_friendly_name.return_value = "COM2"
    notifier.process_device_change(0x0219, 0x8004, 1)
    notifier.call_soon_threadsafe.assert_called()

    # unhandled
    notifier._log.reset_mock()
    notifier.process_device_change(0x0219, 0xFFFF, 1)
    notifier._log.warning.assert_called()

    # Exception
    notifier._get_devtype_friendly_name.side_effect = Exception("fail")
    notifier._log.reset_mock()
    notifier.process_device_change(0x0219, 0x8000, 1)
    notifier._log.exception.assert_called()


def test_device_notifier_get_devtype_port_name(
    monkeypatch: pytest.MonkeyPatch,
    event_loop: asyncio.AbstractEventLoop,
    callback: MagicMock,
) -> None:
    """Tests getting a name for a PORT device."""

    from picolynx.__main__ import DeviceNotifier, NULL

    notifier = DeviceNotifier(event_loop, callback)

    # lparam is NULL
    assert notifier._get_devtype_friendly_name(NULL) == "UNK"

    # lparam is not NULL, but not a PORT device
    class DummyHdr:
        dbch_devicetype = 0x1234

        @classmethod
        def from_address(cls, addr) -> Self:
            return cls()

    class DummyPort:
        dbcp_name = type("X", (), {"offset": 0})()

        @classmethod
        def from_address(cls, addr) -> Self:
            return cls()

    monkeypatch.setattr("picolynx.__main__.DEV_BROADCAST_HDR", DummyHdr)
    monkeypatch.setattr("picolynx.__main__.DEV_BROADCAST_PORT_W", DummyPort)
    assert notifier._get_devtype_friendly_name(123) is None

    # lparam is PORT device
    class DummyHdr2:
        # DBCDeviceType.DBT_DEVTYP_PORT
        dbch_devicetype = 0x0003

        @classmethod
        def from_address(cls, addr) -> Self:
            return cls()

    class DummyPort2:
        dbcp_name = type("X", (), {"offset": 0})()

        @classmethod
        def from_address(cls, addr) -> Self:
            return cls()

    monkeypatch.setattr("picolynx.__main__.DEV_BROADCAST_HDR", DummyHdr2)
    monkeypatch.setattr("picolynx.__main__.DEV_BROADCAST_PORT_W", DummyPort2)
    monkeypatch.setattr("ctypes.wstring_at", lambda addr: "COM42")
    monkeypatch.setattr("ctypes.addressof", lambda obj: 0)
    assert notifier._get_devtype_friendly_name(123) == "COM42"


@pytest.mark.asyncio
async def test_app_startup(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Tests main `TUI` app init & composition logic."""
    app = TUI()
    async with app.run_test() as pilot:
        # Check if the main components are present
        assert pilot.app.query_one("#header")
        assert pilot.app.query_one("#container-main")
        assert pilot.app.query_one("#footer")
        assert pilot.app.query_one("TUINavigation")
        assert pilot.app.query_one("#table-connected")
        assert pilot.app.query_one("#table-persisted")

        # Check if the initial data is loaded into the table
        table = pilot.app.query_one("#table-connected", ConnectedTable)
        await pilot.pause()  # allow time for table to populate
        assert table.row_count == 1
        assert table.get_row_at(0)[0].plain == DEVICE_DESC


@pytest.mark.asyncio
async def test_device_from_selected(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Tests retrieving a device from the cache based on the selected row."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = pilot.app.query_one("#table-connected", ConnectedTable)

        assert table.row_count > 0

        # simulate row selection
        device = app.device_from_selected(RowKey(DEVICE_BUSID))

        assert device is not None
        assert device.busid == DEVICE_BUSID
        assert device.description == DEVICE_DESC

        # test with no selection
        assert app.device_from_selected(None) is None


@pytest.mark.asyncio
async def test_incremental_device_update(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Tests `incremental_device_update` logic."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        table_connected = pilot.app.query_one(
            "#table-connected", ConnectedTable
        )
        table_persisted = pilot.app.query_one(
            "#table-persisted", PersistedTable
        )

        # Initial state
        assert table_connected.row_count == 1
        assert table_persisted.row_count == 1
        assert "1-1" in app._connection_cache

        # --- Test Device Removal ---
        with patch("picolynx.__main__.run_usbipd_state", return_value=[]):
            app.incremental_device_update()
            await pilot.pause()
            assert table_connected.row_count == 0
            assert table_persisted.row_count == 0
            assert DEVICE_BUSID not in app._connection_cache

        # --- Test Device Addition ---
        new_device_data = {
            "Description": DEVICE_2_DESC,
            "InstanceId": "USB\\VID_2E8A&PID_0005\\E5DC12345678911",
            "BusId": DEVICE_2_BUSID,
            "IsForced": False,
            "PersistedGuid": "da56d144-cc8e-4103-875e-15af35bf5fbe",
            "StubInstanceId": None,
        }
        new_device = USBIPDDevice(**new_device_data)
        with patch(
            "picolynx.__main__.run_usbipd_state", return_value=[new_device]
        ):
            app.incremental_device_update()
            await pilot.pause()
            assert table_connected.row_count == 1
            assert table_persisted.row_count == 1
            assert (
                table_connected.get_row(DEVICE_2_BUSID)[0].plain
                == DEVICE_2_DESC
            )
            assert DEVICE_2_BUSID in app._connection_cache

        # --- Test Device Modification ---
        modified_device_data = new_device_data.copy()
        modified_device_data["Description"] = DEVICE_3_DESC
        modified_device = USBIPDDevice(**modified_device_data)
        with patch(
            "picolynx.__main__.run_usbipd_state", return_value=[modified_device]
        ):
            app.incremental_device_update()
            await pilot.pause()
            assert table_connected.row_count == 1
            assert table_connected.get_row("2-2")[0].plain == DEVICE_3_DESC
            assert app._connection_cache["2-2"].description == DEVICE_3_DESC


@pytest.mark.asyncio
async def test_key_binding_messages(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Tests for correct events on simulated key binding press."""

    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        messages = []

        def capture_message(message: events.Event) -> None:
            if isinstance(message, events.Key):
                messages.append(message.key)

        with patch.object(app, "post_message", side_effect=capture_message):
            await pilot.press("d")
            assert messages[-1] == "d"

            await pilot.press("u")
            assert messages[-1] == "u"

            await pilot.press("b")
            assert messages[-1] == "b"

            await pilot.press("a")
            assert messages[-1] == "a"


@pytest.mark.asyncio
async def test_tui_action_post_message(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Tests `TUI.post_message` logic based on action method calls."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()

        messages = []

        def capture_message(message: events.Event) -> None:
            messages.append(message)

        with patch.object(app, "post_message", side_effect=capture_message):
            app.action_manual_detach()
            assert messages and isinstance(messages[-1], USBIPDDetach)
            messages.clear()

            app.action_manual_unbind()
            assert messages and isinstance(messages[-1], USBIPDUnbind)
            messages.clear()

            app.action_manual_bind()
            assert messages and isinstance(messages[-1], USBIPDBind)
            messages.clear()

            app.action_manual_attach()
            assert messages and isinstance(messages[-1], USBIPDAttach)
            messages.clear()
