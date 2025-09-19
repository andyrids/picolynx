"""Exceptions module.

Classes:
    EnablePnPAuditError: Raised on failure to enable PnP audit.

    USBIPDError: Raised on `usbipd` command error.

    WSLError: Raised on `wsl` command error.
"""

__all__ = ("EnablePnPAuditError", "USBIPDError", "WSLError")

class EnablePnPAuditError(Exception):
    """Raised on failure to enable PnP audit."""

    pass


class USBIPDError(Exception):
    """Raised on `usbipd` command error."""

    pass


class WSLError(Exception):
    """"""

    pass