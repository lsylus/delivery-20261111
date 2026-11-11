"""Rectangular heater drawing service contract foundation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("heater-drawing-service")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
