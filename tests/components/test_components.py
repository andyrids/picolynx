"""Unit tests for custom `picolynx.components`."""

import pytest
from unittest.mock import MagicMock, patch
from picolynx.components._components import *
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Label
from textual.widgets.data_table import ColumnKey


DYNAMIC_COLUMN = "DYNAMIC"
STATIC_COLUMN_A = "STATIC A"
STATIC_COLUMN_B = "STATIC B"
STATIC_COLUMN_C = "STATIC C"
STATIC_COLUMN_D = "STATIC D"

DYNAMIC_COLUMN_KEY = ColumnKey("1")
STATIC_COLUMN_A_KEY = ColumnKey("2")
STATIC_COLUMN_B_KEY = ColumnKey("3")
STATIC_COLUMN_C_KEY = ColumnKey("4")
STATIC_COLUMN_D_KEY = ColumnKey("5")

# --- DynamicWidthTable Tests ---


def test_dynamic_width_table_init() -> None:
    """Tests the initialisation of the `DynamicWidthTable`."""
    table = DynamicWidthTable(
        dynamic_label=DYNAMIC_COLUMN,
        dynamic_min=10,
        dynamic_max=50,
        static_widths=(8, 10),
        static_labels=(STATIC_COLUMN_A, STATIC_COLUMN_B),
    )
    assert table.dynamic_label == DYNAMIC_COLUMN
    assert table.dynamic_min == 10
    assert table.dynamic_max == 50
    assert table.static_count == 2
    assert table.static_total_width == 18
    assert table.static_labels == (STATIC_COLUMN_A, STATIC_COLUMN_B)


def test_dynamic_width_table_init_mismatch() -> None:
    """Tests ValueError raised for mismatched static widths and labels."""
    with pytest.raises(ValueError, match="Length mismatch"):
        DynamicWidthTable(
            dynamic_label=DYNAMIC_COLUMN,
            static_widths=(8,),
            static_labels=(STATIC_COLUMN_A, STATIC_COLUMN_B),
        )


@pytest.mark.asyncio
async def test_dynamic_width_table_mount() -> None:
    """Tests the `on_mount` behavior of `DynamicWidthTable`."""
    table = DynamicWidthTable(
        dynamic_label=DYNAMIC_COLUMN,
        static_widths=(10, 12),
        static_labels=(STATIC_COLUMN_A, STATIC_COLUMN_B),
    )

    # using `run_test` to properly mount the widget
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield table

    app = TestApp()
    async with app.run_test() as pilot:
        # await mount completion
        await pilot.pause()
        assert len(table.columns) == 3
        assert table.columns[DYNAMIC_COLUMN_KEY].label.plain == DYNAMIC_COLUMN
        assert table.columns[STATIC_COLUMN_A_KEY].width == 10
        assert table.columns[STATIC_COLUMN_B_KEY].width == 12


# --- Specific Table Implementations ---


def test_connected_table_init() -> None:
    """Tests `ConnectedTable` has correct static columns."""
    table = ConnectedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("BUSID", "VID:PID", "BOUND", "ATTACHED")
    assert table.static_widths == (5, 9, 5, 8)


def test_persisted_table_init() -> None:
    """Tests PersistedTable has correct static columns."""
    table = PersistedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("GUID",)
    assert table.static_widths == (36,)


def test_auto_attached_table_init() -> None:
    """Tests `AutoAttachedTable` has correct static columns."""
    table = AutoAttachedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("SERIAL",)
    assert table.static_widths == (15,)


# --- Other Components ---


@patch("picolynx.components._components.getuser", return_value="testuser")
@patch("picolynx.components._components.gethostname", return_value="testhost")
@pytest.mark.asyncio
async def test_tui_header_compose(
    mock_gethostname: MagicMock, mock_getuser: MagicMock
) -> None:
    """Tests `TUIHeader` widget composition."""
    from textual.app import App

    class HeaderApp(App):
        def compose(self) -> ComposeResult:
            yield TUIHeader()

    app = HeaderApp()
    async with app.run_test() as pilot:
        title = pilot.app.query_one("#header-title", Label)
        hostname = pilot.app.query_one("#header-hostname", Label)
        # assuming a version is set, we check for the static part
        assert "[b]PicoLynx[/]" in str(title.content)
        assert str(hostname.content) == "testuser@testhost"


@pytest.mark.asyncio
async def test_tui_navigation_compose() -> None:
    """Tests `TUINavigation` widget composition."""

    class NavApp(App):
        def compose(self) -> ComposeResult:
            yield TUINavigation()

    app = NavApp()
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#nav-content")
        assert pilot.app.query_one("#nav-connected")
        assert pilot.app.query_one("#table-connected")
        assert pilot.app.query_one("#nav-persisted")
        assert pilot.app.query_one("#table-persisted")
        assert pilot.app.query_one("#nav-autoattach")
        assert pilot.app.query_one("#table-autoattach")
