"""`__init__` for `picolynx` package."""

import contextlib
from importlib.metadata import PackageNotFoundError, version
from picolynx.exceptions import *

with contextlib.suppress(PackageNotFoundError):
    __version__ = version("picolynx")
