""""""
import ctypes
import json
import re
import subprocess
import sys
from logging import getLogger
from pydantic import BaseModel, Field, IPvAnyAddress, ValidationError, computed_field
from win32con import SW_SHOWNORMAL
from typing import Optional, TypedDict
from picolynx.exceptions import USBIPDError, WSLError
from picolynx.utility import LOG_FMT
from textual.logging import TextualHandler

__log = getLogger("commands")


class USBIPDDevice(BaseModel):
    """Device information structure for `usbipd` state JSON."""

    busid: Optional[str] = Field(None, alias="BusId")
    clientipaddress: Optional[IPvAnyAddress] = Field(None, alias="ClientIPAddress")
    description: str = Field(alias="Description")
    instanceid: str = Field(alias="InstanceId")
    isforced: bool = Field(alias="IsForced")
    persistedguid: Optional[str] = Field(None, alias="PersistedGuid")
    stubinstanceid: Optional[str] = Field(None, alias="StubInstanceId")

    @computed_field
    @property
    def vid(self) -> str:
        """Device vendor ID property."""
        ptn = r"VID_(?P<VID>[A-Z0-9]{4})"
        result = re.search(ptn, self.instanceid)
        return result["VID"] if result else "????"

    @computed_field
    @property
    def pid(self) -> str:
        """Device product ID property."""
        ptn = r"PID_(?P<PID>[A-Z0-9]{4})"
        result = re.search(ptn, self.instanceid)
        return result["PID"] if result else "????"

    @computed_field
    @property
    def serial(self) -> str:
        """Device product serial property."""
        ptn = r"\\(?P<SER>[A-Z0-9]+)$"
        result = re.search(ptn, self.instanceid)
        return result["SER"] if result else "????"

    @computed_field
    @property
    def isbound(self) -> bool:
        """Indicates if the device is bound."""
        return bool(self.persistedguid)

    @computed_field
    @property
    def isattached(self) -> bool:
        """Indicates if the device is attached."""
        return bool(self.stubinstanceid)

    @computed_field
    @property
    def isconnected(self) -> bool:
        """Indicates if the device is connected."""
        return bool(self.busid)


class USBIPDState(BaseModel):
    devices: list[USBIPDDevice] = Field(alias="Devices")


def run_as_administrator() -> bool:
    """Launches the app as Administrator.
    
    Returns:
        True if `ShellExecuteW` execution was successful, else False."""
    exit_code = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        " ".join(sys.argv),
        None,
        SW_SHOWNORMAL,
    )
    return exit_code > 32


def run_usbipd_attach(busid: str) -> None:
    """Attaches a USB device to WSL.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd attach` failure.
    """
    try:
        usbipd_attach = subprocess.Popen(
            ["usbipd", "attach", "--busid", busid, "--wsl"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        __log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e
    else:
        __log.info(f"Attached device @ BUSID {busid}")


def run_usbipd_bind(busid: str) -> None:
    """Registers a USB device for sharing, enabling attachment to WSL.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd bind` failure.
    """
    try:
        usbipd_attach = subprocess.Popen(
            ["usbipd", "bind", "--busid", busid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        __log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        __log.info(stdout or stderr)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e
    else:
        __log.info(f"Registered device @ BUSID {busid}")


def run_usbipd_detach(busid: Optional[str] = None) -> None:
    """Detach a USB device from WSL.

    Will detach all USB devices, if `busid` is not passed.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd detach` failure.
    """
    try:
        options = ("--all",) if busid is None else ("--busid", busid)
        usbipd_detach = subprocess.Popen(
            ["usbipd", "detach", *options],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        __log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_detach.communicate(timeout=5)
        if (msg := stdout or stderr):
            __log.info(msg)
        if usbipd_detach.returncode:
            raise USBIPDError(msg)
    except subprocess.TimeoutExpired as e:
        usbipd_detach.kill()
        raise USBIPDError from e
    else:
        __log.info(f"Detached device @ BUSID {busid}")


def run_usbipd_state() -> list[USBIPDDevice]:
    """Fetches the current state of all USB devices in machine-readable JSON.

    Raises:
       USBIPDError: `usbipd` is not installed.

    Returns:
        Current state of all USB devices.
    """
    try:
        usbipd_state = subprocess.Popen(
            ["usbipd", "state"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        __log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_state.communicate(timeout=5)
        if usbipd_state.returncode:
            raise USBIPDError(stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_state.kill()
        raise USBIPDError from e
    
    try:
        state = json.loads(stdout)
        return USBIPDState(**state).devices
    except json.JSONDecodeError as e:
        __log.exception(e)
    except ValidationError as e:
        __log.exception(e)
    return []
    

def run_usbipd_unbind(busid: str) -> None:
    """Unregisters a USB device for sharing.

    Args:
        busid: Device BUSID.

    Raises:
       USBIPDError: On `usbipd bind` failure.
    """
    try:
        usbipd_attach = subprocess.Popen(
            ["usbipd", "unbind", "--busid", busid],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except FileNotFoundError as e:
        __log.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        __log.info(stdout or stderr)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e
    else:
        __log.info(f"Unregistered device @ BUSID {busid}")


def run_wsl_list(running: bool = True) -> tuple[str, ...]:
    """Lists running WSL distributions.

    Returns:
        A list of running WSL distributions.
    """

    args = ["wsl", "--list", "--quiet"]
    if running:
        args.append("--running")
    distros = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        # must specify UTF-16 variant (no Byte Order Mark)
        encoding="UTF-16-LE",
    )

    try:
        stdout, stderr = distros.communicate(timeout=5)
        if stderr:
            raise WSLError(stderr)
    except subprocess.TimeoutExpired as e:
        distros.kill()
        raise WSLError from e

    return tuple(stdout.strip().splitlines())
