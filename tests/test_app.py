from os import name
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from textual.events import Key
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey
from rich.pretty import pprint
from picolynx.__main__ import (
    TUI,
    USBIPDAttach,
    USBIPDBind,
    USBIPDDetach,
    USBIPDUnbind,
)
from picolynx.commands import USBIPDDevice
from picolynx.components import ConnectedTable, PersistedTable

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


DEVICE_DESC = "USB Serial Device (COM1)"
DEVICE_BUSID = "1-1"

DEVICE_2_DESC = "USB Serial Device (COM2)"
DEVICE_2_BUSID = "2-2"

DEVICE_3_DESC = "USB Serial Device (COM3)"
DEVICE_3_BUSID = "3-3"

async def test_app_startup(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
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
        table = pilot.app.query_one("#table-connected", ConnectedTable)
        await pilot.pause()  # allow time for table to populate
        assert table.row_count == 1
        assert table.get_row_at(0)[0].plain == DEVICE_DESC


async def test_device_from_selected(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Test retrieving a device from the cache based on the selected row."""
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


# async def test_manual_actions_post_messages(
#     mock_run_usbipd_state: MagicMock | AsyncMock,
# ) -> None:
#     """Test that manual actions (key presses) post the correct messages."""
#     app = TUI()
#     async with app.run_test() as pilot:
#         # Wait for the table to be populated and select the first row
#         await pilot.pause()
#         table = pilot.app.query_one("#table-connected", ConnectedTable)

#         index = table.get_row_index(DEVICE_BUSID)
#         table.move_cursor(row=index)
#         table.action_select_cursor()

#         messages = []
#         # Patch post_message to capture messages instead of processing them
#         with patch.object(app, "post_message", messages.append):
#             await pilot.press("a")  # attach
#             assert Key(key="a", character="a") in messages
#             # assert isinstance(messages[0], USBIPDAttach)
#             # assert messages[0].device.busid == DEVICE_BUSID

#             await pilot.press("b")  # bind
#             assert len(messages) == 4
#             # assert isinstance(messages[1], USBIPDBind)
#             # assert messages[1].device.busid == DEVICE_BUSID

#             # await pilot.press("d")  # detach
#             # assert len(messages) == 3
#             # assert isinstance(messages[2], USBIPDDetach)
#             # assert messages[2].device.busid == DEVICE_BUSID

#             # await pilot.press("u")  # unbind
#             # assert len(messages) == 4
#             # assert isinstance(messages[3], USBIPDUnbind)
#             # assert messages[3].device.busid == DEVICE_BUSID


async def test_incremental_device_update(
    mock_run_usbipd_state: MagicMock | AsyncMock,
) -> None:
    """Test the logic for incrementally updating device tables."""
    app = TUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        table_connected = pilot.app.query_one("#table-connected", ConnectedTable)
        table_persisted = pilot.app.query_one("#table-persisted", PersistedTable)

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
            assert table_connected.get_row(DEVICE_2_BUSID)[0].plain == DEVICE_2_DESC
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
