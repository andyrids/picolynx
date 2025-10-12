"""Unit tests for `picolynx.commands` package."""

import json
import pytest
from unittest.mock import MagicMock, patch, ANY
import subprocess

from pydantic import ValidationError

from picolynx.commands._commands import (
    USBIPDDevice,
    USBIPDState,
    run_usbipd_attach,
    run_usbipd_bind,
    run_usbipd_detach,
    run_usbipd_state,
    run_usbipd_unbind,
    run_wsl_list,
)
from picolynx.exceptions import USBIPDError, WSLError

DEVICE_1_DESC = "USB Serial Device (COM1)"
DEVICE_1_GUID = "da56d144-cc8e-4103-875e-15af35bf5fbf"
DEVICE_1_INSTANCE_ID = "USB\\VID_2E8A&PID_0005\\E5DC12345678910"
DEVICE_1_SERIAL = "E5DC12345678910"
DEVICE_1_STUB_INSTANCE_ID = "USB\\Vid_80EE&Pid_CAFE\\E5DC12345678910"

DEVICE_2_DESC = "USB Serial Device (COM2)"
DEVICE_3_DESC = "USB Serial Device (COM3)"

# --- Pydantic Model Tests ---

def test_usbipd_device_model_creation(sample_device_data: dict) -> None:
    """Test successful creation of USBIPDDevice model."""
    device = USBIPDDevice(**sample_device_data)
    assert device.busid == "1-1"
    assert device.description == DEVICE_1_DESC
    assert device.instanceid == DEVICE_1_INSTANCE_ID
    assert device.persistedguid == DEVICE_1_GUID
    assert device.stubinstanceid == DEVICE_1_STUB_INSTANCE_ID

def test_usbipd_device_computed_fields(sample_device_data: dict) -> None:
    """Test the computed fields of the USBIPDDevice model."""
    device = USBIPDDevice(**sample_device_data)
    assert device.vid == "2E8A"
    assert device.pid == "0005"
    assert device.serial == DEVICE_1_SERIAL
    assert device.isbound is True
    assert device.isattached is True
    assert device.isconnected is True

def test_usbipd_device_missing_fields() -> None:
    """Test computed fields when optional data is missing."""
    device_data = {
        "Description": DEVICE_1_DESC,
        "InstanceId": DEVICE_1_INSTANCE_ID,
        "IsForced": False,
    }
    device = USBIPDDevice(**device_data)
    assert device.busid is None
    assert device.persistedguid is None
    assert device.stubinstanceid is None
    assert device.vid == "2E8A"
    assert device.pid == "0005"
    assert device.serial == DEVICE_1_SERIAL
    assert device.isbound is False
    assert device.isattached is False
    assert device.isconnected is False

def test_usbipd_device_invalid_instanceid():
    """Test computed fields with a malformed InstanceId."""
    device_data = {
        "Description": "Invalid Device",
        "InstanceId": "INVALID_STRING",
        "IsForced": False,
    }
    device = USBIPDDevice(**device_data)
    assert device.vid == "????"
    assert device.pid == "????"
    assert device.serial == "????"

def test_usbipd_state_model(sample_device_data: USBIPDDevice) -> None:
    """Test the top-level USBIPDState model."""
    state_data = {"Devices": [sample_device_data, sample_device_data]}
    state = USBIPDState(**state_data)
    assert len(state.devices) == 2
    assert isinstance(state.devices[0], USBIPDDevice)
    assert state.devices[1].description == DEVICE_1_DESC

def test_usbipd_state_validation_error() -> None:
    """Test that malformed state data raises a ValidationError."""
    with pytest.raises(ValidationError):
        USBIPDState(Devices=[{"INVALID_KEY": "INVALID_VALUE"}]) # pyright: ignore[reportArgumentType]


# --- Subprocess Command Tests ---

@patch("subprocess.Popen")
def test_run_usbipd_state_success(mock_popen) -> None:
    """Test run_usbipd_state on successful command execution."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_stdout = json.dumps({"Devices": []})
    mock_proc.communicate.return_value = (mock_stdout, "")
    mock_popen.return_value = mock_proc

    devices = run_usbipd_state()
    assert devices == []
    mock_popen.assert_called_with(["usbipd", "state"], stdout=ANY, stderr=ANY, text=True, shell=False)

@patch("subprocess.Popen")
def test_run_usbipd_state_command_error(mock_popen) -> None:
    """Test run_usbipd_state when the command returns an error."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = ("", "An error occurred")
    mock_popen.return_value = mock_proc

    with pytest.raises(USBIPDError, match="An error occurred"):
        run_usbipd_state()

@patch("subprocess.Popen")
def test_run_usbipd_state_file_not_found(mock_popen) -> None:
    """Test run_usbipd_state when usbipd is not installed."""
    mock_popen.side_effect = FileNotFoundError
    with pytest.raises(USBIPDError, match="Missing `usbipd`"):
        run_usbipd_state()

@patch("subprocess.Popen")
def test_run_usbipd_attach_success(mock_popen) -> None:
    """Test run_usbipd_attach on successful execution."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = ("Attached", "")
    mock_popen.return_value = mock_proc

    run_usbipd_attach("1-1")
    mock_popen.assert_called_with(
        ["usbipd", "attach", "--busid", "1-1", "--wsl"],
        stdout=ANY, stderr=ANY, text=True, shell=False
    )

@patch("subprocess.Popen")
def test_run_usbipd_bind_command_error(mock_popen) -> None:
    """Test run_usbipd_bind when the command fails."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = ("", "Bind failed")
    mock_popen.return_value = mock_proc

    with pytest.raises(USBIPDError, match="Bind failed"):
        run_usbipd_bind("2-1")

@patch("subprocess.Popen")
def test_run_usbipd_detach_by_busid(mock_popen) -> None:
    """Test run_usbipd_detach with a specific busid."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = ("", "")
    mock_popen.return_value = mock_proc

    run_usbipd_detach("3-2")
    mock_popen.assert_called_with(
        ["usbipd", "detach", "--busid", "3-2"],
        stdout=ANY, stderr=ANY, text=True, shell=False
    )

@patch("subprocess.Popen")
def test_run_usbipd_detach_all(mock_popen) -> None:
    """Test run_usbipd_detach with the --all flag."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = ("", "")
    mock_popen.return_value = mock_proc

    run_usbipd_detach(None)
    mock_popen.assert_called_with(
        ["usbipd", "detach", "--all"],
        stdout=ANY, stderr=ANY, text=True, shell=False
    )

@patch("subprocess.Popen")
def test_run_usbipd_unbind_timeout(mock_popen) -> None:
    """Test run_usbipd_unbind when the command times out."""
    mock_proc = MagicMock()
    mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="usbipd", timeout=5)
    mock_popen.return_value = mock_proc

    with pytest.raises(USBIPDError):
        run_usbipd_unbind("4-1")
    mock_proc.kill.assert_called_once()

@patch("subprocess.Popen")
def test_run_wsl_list_running(mock_popen) -> None:
    """Test run_wsl_list for running distributions."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("Ubuntu\r\nDebian\r\n", "")
    mock_popen.return_value = mock_proc

    distros = run_wsl_list(running=True)
    assert distros == ("Ubuntu", "Debian")
    mock_popen.assert_called_with(
        ["wsl", "--list", "--quiet", "--running"],
        stdout=ANY, stderr=ANY, text=True, shell=False, encoding="UTF-16-LE"
    )

@patch("subprocess.Popen")
def test_run_wsl_list_all(mock_popen) -> None:
    """Test run_wsl_list for all distributions."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("Ubuntu\r\n", "")
    mock_popen.return_value = mock_proc

    distros = run_wsl_list(running=False)
    assert distros == ("Ubuntu",)
    mock_popen.assert_called_with(
        ["wsl", "--list", "--quiet"],
        stdout=ANY, stderr=ANY, text=True, shell=False, encoding="UTF-16-LE"
    )

@patch("subprocess.Popen")
def test_run_wsl_list_error(mock_popen) -> None:
    """Test run_wsl_list when the command fails."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("", "WSL error")
    mock_popen.return_value = mock_proc

    with pytest.raises(WSLError, match="WSL error"):
        run_wsl_list()
