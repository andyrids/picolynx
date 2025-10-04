import asyncio
from functools import lru_cache
from getpass import getuser
from socket import gethostname
from typing import Any, ClassVar
from typing_extensions import Literal

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Label, TabbedContent, TabPane
from textual.widgets.data_table import ColumnKey

from picolynx import __version__


class DynamicWidthTable(DataTable[Any]):
    """"""

    _previous_width: int = 0

    def __init__(
            self,
            dynamic_min: int = 20,
            dynamic_max: int = 40,
            dynamic_label: str = "",
            *,
            static_widths: tuple[int, ...],
            static_labels: tuple[str, ...],
            **kwargs
        ) -> None:
        """"""
        self._dynamic_label = dynamic_label
        self._dynamic_min = dynamic_min
        self._dynamic_max = dynamic_max
        self._static_count = len(static_widths)
        self._static_width = sum(static_widths)
        self._static_widths = static_widths
        if self._static_count != len(static_labels):
            raise ValueError(f"Missing label from `{static_labels}`")
        self._static_labels = static_labels
        super().__init__(**kwargs)
    
    @property
    def dynamic_label(self) -> str:
        """"""
        return self._dynamic_label

    @property
    def dynamic_max(self) -> int:
        """"""
        return self._dynamic_max

    @property
    def dynamic_min(self) -> int:
        """"""
        return self._dynamic_min
    
    @property
    def static_count(self) -> int:
        """"""
        return self._static_count

    @property
    def static_total_width(self) -> int:
        """"""
        return self._static_width

    @property
    def static_labels(self) -> tuple[str, ...]:
        """"""
        return self._static_labels
    
    @property
    def static_widths(self) -> tuple[int, ...]:
        """"""
        return self._static_widths
    
    @property
    def total_padding(self) -> int:
        """Total padding size for total"""
        return self.cell_padding * len(self.columns) * 2
    
    @lru_cache(maxsize=32)
    def calculate_width(self, width: int) -> int:
        """"""
        dynamic_width = width - self.static_total_width - self.total_padding
        dynamic_width = max(dynamic_width, self.dynamic_min)
        return min(dynamic_width, self.dynamic_max)
    
    def on_mount(self) -> None:
        """"""
        initial_width = self.calculate_width(self.dynamic_min)
        self.add_column(self.dynamic_label, width=initial_width, key="1")

        static_columns = zip(self.static_labels, self.static_widths)
        for key, (label, width) in enumerate(static_columns, start=2):
            self.add_column(label, width=width, key=str(key))
        
        self.focus()
    
    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """"""
        await asyncio.sleep(0.1)
        new_width = self.calculate_width(event.size.width)
        self.log.info(f"{new_width=}, {self.static_total_width}, {self.total_padding}")
        if self._previous_width != new_width:
            self._previous_width = new_width
            self.columns[ColumnKey("1")].width = new_width
            self.refresh_column(0)
            self.refresh(layout=True)


class AutoAttachedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` auto-attached devices."""

    def __init__(self, **kwargs) -> None:
        """"""
        super().__init__(
            dynamic_min=20,
            dynamic_max=40,
            dynamic_label="DESCRIPTION",
            static_widths=(15,),
            static_labels=("SERIAL",),
            **kwargs
        )


class ConnectedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` connected device output."""

    def __init__(self, **kwargs) -> None:
        """"""
        super().__init__(
            dynamic_min=15,
            dynamic_max=40,
            dynamic_label="DESCRIPTION",
            static_widths=(5, 7, 5, 8),
            static_labels=("BUSID", "VID:PID", "BOUND", "ATTACHED"),
            **kwargs
        )


class PersistedTable(DynamicWidthTable):
    """A `DataTable` for `usbipd` persisted device information."""

    def __init__(self, **kwargs) -> None:
        """"""
        super().__init__(
            dynamic_min=20,
            dynamic_max=36,
            dynamic_label="DESCRIPTION",
            static_widths=(20,),
            static_labels=("GUID",),
            **kwargs
        )


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
                yield ConnectedTable(cursor_type="none", id="table-connected")
            with TabPane("Persisted", id="nav-persisted"):
                yield PersistedTable(cursor_type="none", id="table-persisted")
            with TabPane("Auto-attach", id="nav-autoattach"):
                yield AutoAttachedTable(cursor_type="none", id="table-autoattach")

