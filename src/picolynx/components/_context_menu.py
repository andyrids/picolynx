""""""
import logging
from typing import Callable
from textual import on
from textual.logging import TextualHandler
from textual.widgets import OptionList
from textual.widgets._tree import TreeNode

LOG_FMT = "%(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d - %(message)s"

logging.basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))
logger = logging.getLogger(__name__)

def attach(m) -> None:
    logger.info(m)

def bind(m) -> None:
    logger.info(m)

def auto_attach(m) -> None:
    logger.info(m)


class ContextMenu(OptionList):
    """"""

    DEFAULT_INTERACTIONS: list[tuple[str, Callable]] = [
        ("Attach", attach),
        ("Bind", bind),
        ("Auto-Attach", auto_attach),
    ]

    def __init__(self, *args, **kwargs) -> None:
        """"""
        self.interactions = self.DEFAULT_INTERACTIONS
        self.item = None
        super().__init__(*args, **kwargs)
    
    def reload(self, node: TreeNode) -> None:
        self.clear_options()
        self.item = node.data
        # Add options
        for label, _ in self.interactions:
            self.add_option(label, label)
        # Positioning & focus logic as before
        self.add_class("open")
        self.highlighted = 0
        self.focus()
    
    @on(OptionList.OptionSelected)
    def execute_interaction(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is not self or self.item is None:
            return
        _, interaction = self.interactions[event.option_index]
        # You may want to pass a driver as well
        interaction(self.item)
        self.remove_class("open")

    def on_blur(self) -> None:
        self.action_hide()

    def action_hide(self) -> None:
        self.remove_class("open")
