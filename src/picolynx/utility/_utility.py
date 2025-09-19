"""utility functions module."""

import csv
import ctypes
import subprocess
from typing import TYPE_CHECKING

import winerror
from picolynx.exceptions import EnablePnPAuditError

if TYPE_CHECKING:
    from _win32typing import PyEventLogRecord  # pyright: ignore[reportMissingModuleSource]

__all__ = ("is_administrator", "is_pnp_audit", "is_pnp_event")

def is_administrator() -> bool:
    """Indicates whether shell user is administrator."""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def is_pnp_audit() -> bool:
    """Indicates `auditpol` PnP event auditing status.

    Raises:
        EnablePnPAuditError: On `auditpol` process error.

    Returns:
        True if policy inclusion setting is success & failure, else False.
    """
    pnp_status = subprocess.Popen(
        ["auditpol", "/get", "/subcategory:Plug and Play Events", "/r"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )

    try:
        stdout, stderr = pnp_status.communicate(timeout=5)
        if stderr:
            raise EnablePnPAuditError(stderr)
    except subprocess.TimeoutExpired as e:
        pnp_status.kill()
        raise EnablePnPAuditError from e

    if pnp_status.returncode == 0 and stdout:
        policy = next(csv.DictReader(stdout.lower().strip().splitlines()))
        return policy.get("inclusion setting") == "success and failure"
    return False


def is_pnp_event(event: "PyEventLogRecord") -> bool:
    """Indicates if an event is a PnP event.

    Args:
        event: An event log record.

    Returns:
        True if `event.EventID` is 6416 (PnP), else False.
    """
    return winerror.HRESULT_CODE(event.EventID) == 6416