import asyncio
from functools import lru_cache
from getpass import getuser
from socket import gethostname
from typing import Any

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Label, TabbedContent, TabPane
from textual.widgets.data_table import ColumnKey

from picolynx import __version__


class AutoAttachedTable(DataTable[Any]):
    """A `DataTable` for `usbipd` auto-attached devices."""
    COL1_MIN_WIDTH = 20
    COL1_MAX_WIDTH = 40
    COL2_WIDTH = 15
    STATIC_WIDTH = COL2_WIDTH

    _previous_width = COL1_MIN_WIDTH

    @property
    def total_padding(self) -> int:
        """"""
        return self.cell_padding * 2 * 2

    @lru_cache(maxsize=32)
    def calculate_width(self, width: int) -> int:
        """"""
        dynamic_width = width - self.STATIC_WIDTH - self.total_padding
        dynamic_width = max(dynamic_width, self.COL1_MIN_WIDTH)
        return min(dynamic_width, self.COL1_MAX_WIDTH)

    def on_mount(self) -> None:
        """"""
        initial_width = self.calculate_width(self.size.width)
        self.add_column("DESCRIPTION", width=initial_width, key="1")
        self.add_column("SERIAL", width=self.COL2_WIDTH, key="2")
        if self.COL1_MIN_WIDTH != initial_width:
            self._previous_width = initial_width

    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """"""
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(event.size.width)

        if self._previous_width != new_width:
            self._previous_width = new_width
            self.columns[ColumnKey("1")].width = new_width

class DeviceTable(DataTable[Any]):
    """A `DataTable` for `usbipd` connected device output."""
    COL1_MIN_WIDTH = 15
    COL1_MAX_WIDTH = 40
    COL2_WIDTH = 5
    COL3_WIDTH = 7
    COL4_WIDTH = 5
    COL5_WIDTH = 8
    STATIC_WIDTH = sum((COL2_WIDTH, COL3_WIDTH, COL4_WIDTH, COL5_WIDTH))

    _previous_width = COL1_MIN_WIDTH

    def on_mount(self) -> None:
        """"""
        initial_width = self.calculate_width(self.size.width)
        self.add_column("DESCRIPTION", width=initial_width, key="1")
        self.add_column("BUSID", width=self.COL2_WIDTH, key="2")
        self.add_column("VID:PID", width=self.COL3_WIDTH, key="3")
        self.add_column("BOUND", width=self.COL4_WIDTH, key="4")
        self.add_column("ATTACHED", width=self.COL5_WIDTH, key="5")
        if self.COL1_MIN_WIDTH != initial_width:
            self._previous_width = initial_width

    @property
    def total_padding(self) -> int:
        """"""
        return self.cell_padding * 5 * 2

    @lru_cache(maxsize=32)
    def calculate_width(self, width: int) -> int:
        """"""
        dynamic_width = width - self.STATIC_WIDTH - self.total_padding
        dynamic_width = max(dynamic_width, self.COL1_MIN_WIDTH)
        return min(dynamic_width, self.COL1_MAX_WIDTH)

    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """"""
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(event.size.width)
        self.log.info(f"{event.size.width - self.STATIC_WIDTH - self.total_padding=}")
        self.log.info(f"{new_width=}")
        if self._previous_width != new_width:
            self._previous_width = new_width
            self.columns[ColumnKey("1")].width = new_width
            self.refresh()


class PersistedTable(DataTable[Any]):
    """A `DataTable` for `usbipd` persisted device information."""

    COL1_MIN_WIDTH = 20
    COL1_MAX_WIDTH = 36
    COL2_WIDTH = 20
    STATIC_WIDTH = COL2_WIDTH

    _previous_width = COL1_MIN_WIDTH

    @property
    def total_padding(self) -> int:
        """"""
        return self.cell_padding * 2 * 2

    @lru_cache(maxsize=32)
    def calculate_width(self, width: int) -> int:
        """"""
        dynamic_width = width - self.STATIC_WIDTH - self.total_padding
        dynamic_width = max(dynamic_width, self.COL1_MIN_WIDTH)
        return min(dynamic_width, self.COL1_MAX_WIDTH)

    def on_mount(self) -> None:
        """"""
        initial_width = self.calculate_width(self.size.width)
        self.add_column("DESCRIPTION", width=initial_width, key="1")
        self.add_column("GUID", width=self.COL2_WIDTH, key="2")
        if self.COL1_MIN_WIDTH != initial_width:
            self._previous_width = initial_width
    
    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """"""
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(event.size.width)

        if self._previous_width != new_width:
            self._previous_width = new_width
            self.columns[ColumnKey("1")].width = new_width


class TUIHeader(Horizontal):
    """TUI header widget."""

    def compose(self) -> ComposeResult:
        """Generates the TUI header components."""
        version = f"[b]PicoLynx[/] [dim]v{__version__}[/]"
        yield Label(version, id="header-title")
        hostname = Text.from_markup(f"{getuser()}@{gethostname()}")
        yield Label(hostname, id="header-hostname")


class TUINavigation(Widget):
    """"""
    
    def compose(self) -> ComposeResult:
        """"""
        with TabbedContent(id="nav-content"):
            with TabPane("Connected", id="nav-connected"):
                yield DeviceTable(cursor_type="none", id="table-connected")
            with TabPane("Persisted", id="nav-persisted"):
                yield PersistedTable(cursor_type="none", id="table-persisted")
            with TabPane("Auto-attach", id="nav-autoattach"):
                yield AutoAttachedTable(cursor_type="none", id="table-autoattach")
