""""""

import getpass
import logging
import time
import threading
from itertools import chain
from pathlib import Path
import socket
from typing import ClassVar

from mpremote import mip
from rich.console import Console
from rich.pretty import pprint
from rich.text import Text
from rich.table import Table
from picolynx.connection._serial import REPL, Device, Transport, buffer_factory
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.logging import TextualHandler
from textual.widgets import DataTable, Footer, Header, Label, Tree
from textual.widgets.tree import TreeNode

Binding = tuple[str, str, str]

logging.basicConfig(level="NOTSET", handlers=(TextualHandler(),))
_logger = logging.getLogger(__name__)


class TUIHeader(Horizontal):
    """"""

    def compose(self) -> ComposeResult:
        """"""
        yield Label(f"[b]Serpent[/] [dim]v0.1.0[/]", id="header-title")
        hostname = Text.from_markup(
            f"{getpass.getuser()}@{socket.gethostname()}"
        )
        yield Label(hostname, id="header-hostname")


# app-title app-user-host


class TUI(App):
    """"""

    BINDINGS: ClassVar[list[Binding]] = [
        ("d", "toggle_dark", "Toggle dark mode"),
    ]

    CSS_PATH: ClassVar[str] = "global.tcss"

    TITLE: ClassVar[str] = "TITLE"
    SUB_TITLE: ClassVar[str] = "SUBTITLE"

    def __init__(self, device: Device) -> None:
        """_summary_

        Args:
            connection: _description_
        """
        super().__init__()
        self.device = device
        self.device_tree = Tree("📁 Device", id="listdir")
        self.device_tree.can_focus = False
        self.device_tree.can_focus_children = False
        self.device_tree.guide_depth = 3
        self.device_tree.border_title = "Device Content"
        self._exit_event = threading.Event()
        self.connection_lock = threading.Lock()

    def compose(self) -> ComposeResult:
        yield TUIHeader()
        with Horizontal():
            yield DataTable(show_header=False, cursor_type="none", id="info")
            yield DataTable(show_header=False, cursor_type="none", id="statvfs")
        with Horizontal():
            yield self.device_tree
        # yield Footer()

    def on_mount(self) -> None:
        """"""
        self.device_tree.loading = True
        self.update_device()

        info_table = self.query_one("#info", DataTable)
        info_table.border_title = "Device Information"
        info_table.add_columns("", "")
        for label, value in self.device.uname().items():
            info_table.add_row(f"[label]{label.capitalize()}", value)

        statvfs_table = self.query_one("#statvfs", DataTable)
        statvfs_table.border_title = "Device Filesystem"
        statvfs_table.add_columns("", "")
        for label, value in self.device.statvfs().items():
            statvfs_table.add_row(f"[label]{label}", value)

    def on_unmount(self) -> None:
        """"""
        self._exit_event.set()

    @work(thread=True, exclusive=True)
    def update_device(self) -> None:
        """"""
        while not self._exit_event.is_set():
            try:
                with self.connection_lock:
                    directories, files = self.device.listdir()
                if not self._exit_event.is_set():
                    self.call_from_thread(
                        self.repopulate_tree, directories, files
                    )
            except Exception as e:
                _logger.exception(e)

                pass
            self._exit_event.wait(2)

    def repopulate_tree(
        self, directories: dict[Path, int], files: dict[Path, int]
    ) -> None:
        """"""
        self.device_tree.loading = False
        self.device_tree.clear()
        tree_nodes: dict[Path, TreeNode] = {Path("/"): self.device_tree.root}

        for path in sorted(chain(directories, files)):
            if path.name == "/":
                continue

            parent_node = tree_nodes[path.parent]
            if path in files:
                label = f"📄 {path.name}  [dim]({files[path]} B)[/dim]"
                parent_node.add_leaf(label)
            else:
                label = f"📁 {path.name}"
                tree_nodes[path] = parent_node.add(label, allow_expand=False)
        self.device_tree.root.allow_expand = False
        self.device_tree.root.label = "📁 Device"
        self.device_tree.root.expand_all()

    def action_device_install(self) -> None:
        mip._install_package(
            self.device.transport,
            "github:andyrids/micropython-networkutils/",
            "https://micropython.org/pi/v2",
            "lib",
            "main",
            True,
        )

        self.update_device()

    @work(thread=True, exclusive=True)
    def install_package(self) -> None:
        """"""
        try:
            with self.connection_lock:
                mip._install_package(
                    self.device.transport,
                    "github:andyrids/micropython-networkutils/",
                    "https://micropython.org/pi/v2",
                    "lib",
                    "main",
                    True,
                )
        except Exception:
            _logger.exception(e)


"""
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
OSError: [Errno 2] ENOENT
"""


if __name__ == "__main__":
    connection = None
    try:
        buffer, data_consumer = buffer_factory()
        device = Device(name=None)

        app = TUI(device=device)
        app.run()
    except Exception as e:
        _logger.exception(e)

    finally:
        if connection:
            connection.transport.serial.close()
