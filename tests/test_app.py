from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import DataTable

from picolynx.__main__ import TUI, USBIPDAttach, USBIPDBind, USBIPDDetach, USBIPDUnbind
from picolynx.commands import USBIPDDevice

OLD_DEVICE_DESC = "USB Serial Device (COM1)"
NEW_DEVICE_DESC = "USB Serial Device (COM2)"
MOD_DEVICE_DESC = "USB Serial Device (COM3)"

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_run_usbipd_state() -> Generator[MagicMock | AsyncMock, Any, None]:
    """Fixture to mock run_usbipd_state."""
    device_data = {
        "Description": OLD_DEVICE_DESC,
        "InstanceId": "USB\\VID_2E8A&PID_0005\\E5DC12345678910",
        "BusId": "1-1",
        "IsForced": False,
        "PersistedGuid": "da56d144-cc8e-4103-875e-15af35bf5fbf",
        "StubInstanceId": "USB\\Vid_80EE&Pid_CAFE\\E5DC12345678910",
    }
    mock_device = USBIPDDevice(**device_data)
    with patch("picolynx.__main__.run_usbipd_state", return_value=[mock_device]) as mock:
        yield mock

async def test_app_startup(mock_run_usbipd_state: MagicMock | AsyncMock) -> None:
    """Test if the main TUI app starts up and composes its layout correctly."""
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
        table = pilot.app.query_one("#table-connected", DataTable)
        await pilot.pause() # allow time for table to populate
        assert table.row_count == 1
        assert table.get_row_at(0)[0].plain == "Test Device"


async def test_device_from_selected(mock_run_usbipd_state: MagicMock | AsyncMock) -> None:
    """Test retrieving a device from the cache based on the selected row."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = pilot.app.query_one("#table-connected", DataTable)

        # Simulate row selection
        table.cursor_row = 0 # type: ignore
        selected_key = table.row_keys[table.cursor_row] # type: ignore

        device = app.device_from_selected(selected_key)
        assert device is not None
        assert device.busid == "1-1"
        assert device.description == "Test Device"

        # Test with no selection
        assert app.device_from_selected(None) is None


async def test_manual_actions_post_messages(mock_run_usbipd_state: MagicMock | AsyncMock) -> None:
    """Test that manual actions (key presses) post the correct messages."""
    app = TUI()
    async with app.run_test() as pilot:
        # Wait for the table to be populated and select the first row
        await pilot.pause()
        table = pilot.app.query_one("#table-connected", DataTable)
        table.cursor_row = 0 # type: ignore

        messages = []
        # Patch post_message to capture messages instead of processing them
        with patch.object(app, "post_message", messages.append):
            await pilot.press("a")  # attach
            assert len(messages) == 1
            assert isinstance(messages[0], USBIPDAttach)
            assert messages[0].device.busid == "1-1"

            await pilot.press("b")  # bind
            assert len(messages) == 2
            assert isinstance(messages[1], USBIPDBind)
            assert messages[1].device.busid == "1-1"

            await pilot.press("d")  # detach
            assert len(messages) == 3
            assert isinstance(messages[2], USBIPDDetach)
            assert messages[2].device.busid == "1-1"

            await pilot.press("u")  # unbind
            assert len(messages) == 4
            assert isinstance(messages[3], USBIPDUnbind)
            assert messages[3].device.busid == "1-1"

async def test_incremental_device_update(mock_run_usbipd_state: MagicMock | AsyncMock) -> None:
    """Test the logic for incrementally updating device tables."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        table_connected = pilot.app.query_one("#table-connected", DataTable)
        table_persisted = pilot.app.query_one("#table-persisted", DataTable)

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
            assert "1-1" not in app._connection_cache

        # --- Test Device Addition ---
        new_device_data = {
            "Description": "USB Serial Device (COM2)",
            "InstanceId": "USB\\VID_2E8A&PID_0005\\E5DC12345678911",
            "BusId": "2-2",
            "IsForced": False,
            "PersistedGuid": "da56d144-cc8e-4103-875e-15af35bf5fbe",
            "StubInstanceId": None
        }
        new_device = USBIPDDevice(**new_device_data)
        with patch("picolynx.__main__.run_usbipd_state", return_value=[new_device]):
            app.incremental_device_update()
            await pilot.pause()
            assert table_connected.row_count == 1
            assert table_persisted.row_count == 1
            assert table_connected.get_row("2-2")[0].plain == NEW_DEVICE_DESC
            assert "2-2" in app._connection_cache

        # --- Test Device Modification ---
        modified_device_data = new_device_data.copy()
        modified_device_data["Description"] = MOD_DEVICE_DESC
        modified_device = USBIPDDevice(**modified_device_data)
        with patch("picolynx.__main__.run_usbipd_state", return_value=[modified_device]):
            app.incremental_device_update()
            await pilot.pause()
            assert table_connected.row_count == 1
            assert table_connected.get_row("2-2")[0].plain == MOD_DEVICE_DESC
            assert app._connection_cache["2-2"].description == MOD_DEVICE_DESC
