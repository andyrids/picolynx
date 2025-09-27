""""""
import ctypes
import json
import subprocess
import sys
from win32con import SW_SHOWNORMAL
from typing import Optional, TypedDict
from picolynx.exceptions import USBIPDError, WSLError
from picolynx.utility import logger


class USBIPDDevice(TypedDict):
    """Device information structure for `usbipd` state JSON."""

    BusId: str
    ClientIPAddress: Optional[str]
    Description: str
    InstanceId: str
    IsForced: bool
    PersistedGuid: Optional[str]
    StubInstanceId: Optional[str]


class USBIPDState(TypedDict):
    """Top-level structure for `usbipd` state JSON."""

    Devices: list[USBIPDDevice]


def run_as_administrator() -> int:
    """"""
    return ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        " ".join(sys.argv),
        None,
        SW_SHOWNORMAL,
    )


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
        logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e


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
        logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_attach.communicate(timeout=5)
        logger.info(stdout or stderr)
        if usbipd_attach.returncode:
            raise USBIPDError(stdout or stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_attach.kill()
        raise USBIPDError from e


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
        logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_detach.communicate(timeout=5)
        if (msg := stdout or stderr):
            logger.info(msg)
        if usbipd_detach.returncode:
            raise USBIPDError(msg)
    except subprocess.TimeoutExpired as e:
        usbipd_detach.kill()
        raise USBIPDError from e


def run_usbipd_state() -> USBIPDState:
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
        logger.fatal("`usbipd` is not installed", exc_info=True)
        raise USBIPDError("Missing `usbipd`: `winget install usbipd`") from e

    try:
        stdout, stderr = usbipd_state.communicate(timeout=5)
        if usbipd_state.returncode:
            raise USBIPDError(stderr)
    except subprocess.TimeoutExpired as e:
        usbipd_state.kill()
        raise USBIPDError from e
    return json.loads(stdout)


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
