""""""
from importlib.metadata import PackageNotFoundError, version
try:
    __version__ = version("picolynx")
except PackageNotFoundError:
    pass