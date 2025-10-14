"""Defines custom TUI components and tables for `PicoLynx`.

This module provides specialized widgets and `DataTable` classes for the
PicoLynx TUI, including dynamic-width tables for device data and compound
navigation elements. These components are used to display and interact with
USBIPD device information and application metadata.

Classes:
    DynamicWidthTable: Custom DataTable with a dynamic initial column.
    AutoAttachedTable: DataTable for auto-attached USBIPD devices.
    ConnectedTable: DataTable for connected USBIPD device output.
    PersistedTable: DataTable for persisted USBIPD device information.
    TUIFooter: TUI footer widget.
    TUIHeader: TUI header widget displaying version and hostname.
    TUINavigation: Compound navigation widget with tabbed tables.
"""

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
from textual.widgets import DataTable, Footer, Label, TabbedContent, TabPane
from textual.widgets.data_table import ColumnKey, RowKey

from picolynx import __version__


class DynamicWidthTable(DataTable[Any]):
    """Custom `DataTable` with a dynamic initial column.

    The first column expands and contracts in size with terminal resize,
    based on passed constraint parameters.
    """

    _previous_width: int = 0

    def __init__(
        self,
        dynamic_label: str,
        dynamic_min: int = 20,
        dynamic_max: int = 40,
        *,
        static_widths: tuple[int, ...],
        static_labels: tuple[str, ...],
        **kwargs,
    ) -> None:
        """Initialises the table & passes `kwargs` to `DataTable` parent.

        Args:
            dynamic_min: Minimum width of the dynamic column. Defaults to 20.
            dynamic_max: Maximum width of the dynamic column. Defaults to 40.
            dynamic_label: Label of the dynamic column. Defaults to "".
            static_widths: Width values of static columns.
            static_labels: Labels of the static columns.
            **kwargs: Keyword args for the parent `DataTable`.

        Raises:
            ValueError: On `static_widths` & `static_labels` length mismatch.
        """
        self._dynamic_label = dynamic_label
        self._dynamic_min = dynamic_min
        self._dynamic_max = dynamic_max
        self._static_count = len(static_widths)
        self._static_width = sum(static_widths)
        self._static_widths = static_widths
        if self._static_count != len(static_labels):
            raise ValueError(
                "Length mismatch: `static_labels` & `static_widths`"
            )
        self._static_labels = static_labels
        self._row_selected = None
        self._row_selected_key = None
        super().__init__(**kwargs)

    @property
    def dynamic_label(self) -> str:
        """Label of the dynamic column."""
        return self._dynamic_label

    @property
    def dynamic_max(self) -> int:
        """Maximum size of the dynamic column."""
        return self._dynamic_max

    @property
    def dynamic_min(self) -> int:
        """Minimum size of the dynamic column."""
        return self._dynamic_min

    @property
    def row_selected_key(self) -> RowKey | None:
        """Selected row key property."""
        return self._row_selected_key

    @property
    def static_count(self) -> int:
        """Count of static columns."""
        return self._static_count

    @property
    def static_labels(self) -> tuple[str, ...]:
        """Static column labels property."""
        return self._static_labels

    @property
    def static_total_width(self) -> int:
        """Total static column width."""
        return self._static_width

    @property
    def static_widths(self) -> tuple[int, ...]:
        """Static width values property."""
        return self._static_widths

    @property
    def total_padding(self) -> int:
        """Total padding size for total"""
        return self.cell_padding * len(self.columns) * 2

    @lru_cache(maxsize=32)
    def calculate_width(self, width: int) -> int:
        """Calculates available width after static columns & padding.

        Args:
            width: With of the `DataTable`.
        """
        dynamic_width = width - self.static_total_width - self.total_padding
        return max(dynamic_width, self.dynamic_min)

    async def initial_resize(self) -> None:
        """Performs an initial resize of the dynamic column."""
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(self.size.width)
        if self.update_previous_width(new_width):
            self.columns[ColumnKey("1")].width = new_width

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handles `DataTable` row selection events.

        Args:
            event: `RowSelected` event message.
        """
        self._row_selected_key = event.row_key

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Handles `DataTable` row highlight events.

        Args:
            event: `RowHighlighted` event message.
        """
        self._row_selected_key = event.row_key

    def on_mount(self) -> None:
        """Handles the DataTable setup on mount."""
        # set column `auto_width=True` via `width=None`
        self.add_column(self.dynamic_label, width=None, key="1")

        static_columns = zip(self.static_labels, self.static_widths)
        for key, (label, width) in enumerate(static_columns, start=2):
            self.add_column(label, width=width, key=str(key))
        # after initial layout has settled, we trigger a resize
        self.call_later(self.initial_resize)

    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """Handles widget resize events.

        Modifies the dynamic column width based on available width in the
        terminal window & the column content size.

        Args:
            event: Widget `Resize` event.
        """
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(event.size.width)
        if self.update_previous_width(new_width):
            column = self.columns[ColumnKey("1")]
            column.auto_width = new_width > column.content_width
            column.width = new_width
            self.refresh_column(0)
            self.refresh(layout=True)

    def update_previous_width(self, new_width: int) -> bool:
        """Updates previous width if different from `new_width`.

        Returns:
            True if previous width was updated, else False."""
        if self._previous_width != new_width:
            self._previous_width = new_width
            return True
        return False


class AutoAttachedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` auto-attached devices."""

    def __init__(self, **kwargs) -> None:
        """Initialises a `DataTable` for auto-attached devices."""
        super().__init__(
            dynamic_label="DESCRIPTION",
            dynamic_min=20,
            dynamic_max=45,
            static_widths=(15,),
            static_labels=("SERIAL",),
            **kwargs,
        )


class ConnectedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` connected device output."""

    def __init__(self, **kwargs) -> None:
        """Initialises a `DataTable` for connected devices."""
        super().__init__(
            dynamic_label="DESCRIPTION",
            dynamic_min=15,
            dynamic_max=45,
            static_widths=(5, 9, 5, 8),
            static_labels=("BUSID", "VID:PID", "BOUND", "ATTACHED"),
            **kwargs,
        )


class PersistedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` persisted device information."""

    def __init__(self, **kwargs) -> None:
        """Initialises a `DataTable` for persisted devices."""
        super().__init__(
            dynamic_label="DESCRIPTION",
            dynamic_min=20,
            dynamic_max=40,
            static_widths=(36,),
            static_labels=("GUID",),
            **kwargs,
        )


class TUIFooter(Footer):
    """TUI footer widget."""

    pass


class TUIHeader(Horizontal):
    """TUI header widget."""

    def compose(self) -> ComposeResult:
        """Generates the TUI header components."""
        version = f"[b]PicoLynx[/] [dim]v{__version__}[/]"
        yield Label(version, id="header-title")
        hostname = Text.from_markup(f"{getuser()}@{gethostname()}")
        yield Label(hostname, id="header-hostname")


class TUINavigation(Widget):
    """TUI compound navigation widget."""

    def compose(self) -> ComposeResult:
        """Generates navigation components."""
        with TabbedContent(id="nav-content"):
            with TabPane("Connected", id="nav-connected"):
                yield ConnectedTable(cursor_type="row", id="table-connected")
            with TabPane("Persisted", id="nav-persisted"):
                yield PersistedTable(cursor_type="none", id="table-persisted")
            with TabPane("Auto-attach", id="nav-autoattach"):
                yield AutoAttachedTable(
                    cursor_type="none", id="table-autoattach"
                )
