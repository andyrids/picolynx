import pytest
from unittest.mock import patch
from picolynx.components._components import (
    DynamicWidthTable,
    ConnectedTable,
    PersistedTable,
    AutoAttachedTable,
    TUIHeader,
    TUINavigation
)

pytestmark = pytest.mark.asyncio

# --- DynamicWidthTable Tests ---

def test_dynamic_width_table_init():
    """Test the initialization of the DynamicWidthTable."""
    table = DynamicWidthTable(
        dynamic_label="Dynamic",
        dynamic_min=10,
        dynamic_max=50,
        static_widths=(8, 10),
        static_labels=("Static1", "Static2")
    )
    assert table.dynamic_label == "Dynamic"
    assert table.dynamic_min == 10
    assert table.dynamic_max == 50
    assert table.static_count == 2
    assert table.static_total_width == 18
    assert table.static_labels == ("Static1", "Static2")

def test_dynamic_width_table_init_mismatch():
    """Test that a ValueError is raised for mismatched static widths and labels."""
    with pytest.raises(ValueError, match="Length mismatch"):
        DynamicWidthTable(
            dynamic_label="Dynamic",
            static_widths=(8,),
            static_labels=("Static1", "Static2")
        )

async def test_dynamic_width_table_mount():
    """Test the on_mount behavior of DynamicWidthTable."""
    table = DynamicWidthTable(
        dynamic_label="Dynamic Col",
        static_widths=(10, 12),
        static_labels=("Static A", "Static B")
    )
    
    # Using run_test to properly mount the widget
    from textual.app import App
    class TestApp(App):
        def compose(self):
            yield table

    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause() # allow mount to complete
        assert len(table.columns) == 3
        assert table.columns[table.get_column_key("Dynamic Col")].label.plain == "Dynamic Col"
        assert table.columns[table.get_column_key("Static A")].width == 10
        assert table.columns[table.get_column_key("Static B")].width == 12


# --- Specific Table Implementations ---

def test_connected_table_init():
    """Test that ConnectedTable initializes with correct static columns."""
    table = ConnectedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("BUSID", "VID:PID", "BOUND", "ATTACHED")
    assert table.static_widths == (5, 9, 5, 8)

def test_persisted_table_init():
    """Test that PersistedTable initializes with correct static columns."""
    table = PersistedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("GUID",)
    assert table.static_widths == (36,)

def test_auto_attached_table_init():
    """Test that AutoAttachedTable initializes with correct static columns."""
    table = AutoAttachedTable()
    assert table.dynamic_label == "DESCRIPTION"
    assert table.static_labels == ("SERIAL",)
    assert table.static_widths == (15,)


# --- Other Components ---

@patch("picolynx.components._components.getuser", return_value="testuser")
@patch("picolynx.components._components.gethostname", return_value="testhost")
async def test_tui_header_compose(mock_gethostname, mock_getuser):
    """Test the composition of the TUIHeader widget."""
    from textual.app import App
    class HeaderApp(App):
        def compose(self):
            yield TUIHeader()

    app = HeaderApp()
    async with app.run_test() as pilot:
        title = pilot.app.query_one("#header-title")
        hostname = pilot.app.query_one("#header-hostname")
        # Assuming a version is set, we check for the static part
        assert "[b]PicoLynx[/]" in str(title.renderable)
        assert hostname.renderable.plain == "testuser@testhost"

async def test_tui_navigation_compose():
    """Test the composition of the TUINavigation widget."""
    from textual.app import App
    class NavApp(App):
        def compose(self):
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