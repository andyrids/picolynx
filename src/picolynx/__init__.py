""""""

from importlib.metadata import PackageNotFoundError, version
from picolynx.exceptions import *

try:
    __version__ = version("picolynx")
except PackageNotFoundError:
    pass
