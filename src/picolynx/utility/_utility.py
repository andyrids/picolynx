"""utility functions module."""

import csv
import ctypes
import re
import subprocess
from logging import basicConfig, getLogger
from typing import TYPE_CHECKING

from picolynx.exceptions import EnablePnPAuditError
from textual.logging import TextualHandler

if TYPE_CHECKING:
    from _win32typing import PyEventLogRecord  # pyright: ignore[reportMissingModuleSource]


LOG_FMT = "%(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d - %(message)s"

basicConfig(level="NOTSET", format=LOG_FMT, handlers=(TextualHandler(),))
logger = getLogger(__name__)


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
        ["auditpol", "/get", "/subcategory:Plug and Play Eventss", "/r"],
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


def parse_instanceid(instanceid: str) -> tuple[str, str, str]:
    """Parses `InstanceId` value into VID, PID & serial number.

    Args:
        instanceid: The device `InstanceID` value.

    Returns:
        The device VID, PID & serial ID values..
    """
    if not instanceid.startswith("USB\\"):
        return ("UNK", "UNK", "UNK")

    ptn = (
        r"VID_(?P<VID>[A-Z0-9]{4})&PID_(?P<PID>[A-Z0-9]{4})(?:&MI_\d{2})?\\(?P<SER>.+)"
    )
    if match := re.search(ptn, instanceid):
        return (match["VID"], match["PID"], match["SER"])
    return ("UNK", "UNK", "UNK")
