""""""

import asyncio
from typing import Any
from textual import events, work
from textual.widgets.data_table import ColumnKey
from textual.widgets import DataTable


class DeviceTable(DataTable[Any]):
    """A `DataTable` for `usbipd` connected device output."""

    COL1_MIN_WIDTH = 20
    COL1_MAX_WIDTH = 40
    COL2_WIDTH = 5
    COL3_WIDTH = 4
    COL4_WIDTH = 4
    COL5_WIDTH = 5
    COL6_WIDTH = 8
    STATIC_WIDTH = sum(
        (COL2_WIDTH, COL3_WIDTH, COL4_WIDTH, COL5_WIDTH, COL6_WIDTH)
    )

    _previous_width = COL1_MIN_WIDTH

    def on_mount(self) -> None:
        """"""
        self.add_column("DESCRIPTION", width=self.COL1_MIN_WIDTH, key="1")
        self.add_column("BUSID", width=self.COL2_WIDTH, key="2")
        self.add_column("VID", width=self.COL3_WIDTH, key="3")
        self.add_column("PID", width=self.COL4_WIDTH, key="4")
        self.add_column("BOUND", width=self.COL5_WIDTH, key="5")
        self.add_column("ATTACHED", width=self.COL6_WIDTH, key="6")

    @work(exclusive=True)
    async def on_resize(self, event: events.Resize) -> None:
        """"""
        await asyncio.sleep(0.1)
        padding = self.cell_padding * (len(self.columns) * 2)
        dynamic_width = event.size.width - self.STATIC_WIDTH - padding
        dynamic_width = max(dynamic_width, self.COL1_MIN_WIDTH)
        dynamic_width = min(dynamic_width, self.COL1_MAX_WIDTH)

        if self._previous_width != dynamic_width:
            self._previous_width = dynamic_width
            self.columns[ColumnKey("1")].width = dynamic_width
            self.refresh()
