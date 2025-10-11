"""Defines custom exception classes for PnP audit, USBIPD, and WSL errors.

This module provides specialized exception types for errors encountered
when enabling PnP audit, executing `usbipd` commands, or running `wsl`
commands.

Classes:
    EnablePnPAuditError: Exception raised on failure to enable PnP audit.
    USBIPDError: Exception raised on `usbipd` command error.
    WSLError: Exception raised on `wsl` command error.
"""

__all__ = ("EnablePnPAuditError", "USBIPDError", "WSLError")


class EnablePnPAuditError(Exception):
    """Raised on failure to enable PnP audit."""

    pass


class USBIPDError(Exception):
    """Raised on `usbipd` command error."""

    pass


class WSLError(Exception):
    """Raised on `wsl` command error."""

    pass
