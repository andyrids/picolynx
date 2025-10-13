"""ContaINS fixtures for unit test functions."""

from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from picolynx.commands import USBIPDDevice

DEVICE_DESC = "USB Serial Device (COM1)"
DEVICE_INSTANCE_ID = "USB\\VID_2E8A&PID_0005\\E5DC12345678910"
DEVICE_BUSID = "1-1"
DEVICE_CLIENT_IPADDR = "127.0.0.1"
DEVICE_ISFORCED = False
DEVICE_PERSISTED_GUID = "da56d144-cc8e-4103-875e-15af35bf5fbf"
DEVICE_STUB_INSTANCE_ID = "USB\\Vid_80EE&Pid_CAFE\\E5DC12345678910"

DEVICE_2_DESC = "USB Serial Device (COM2)"
DEVICE_2_BUSID = "2-2"

DEVICE_C_DESC = "USB Serial Device (COM3)"

@pytest.fixture
def sample_device_data() -> dict[str, Any]:
    """Provides a sample dictionary of USBIPD device data."""
    return {
        "Description": DEVICE_DESC,
        "InstanceId": DEVICE_INSTANCE_ID,
        "BusId": DEVICE_BUSID,
        "ClientIPAddress": DEVICE_CLIENT_IPADDR,
        "IsForced": DEVICE_ISFORCED,
        "PersistedGuid": DEVICE_PERSISTED_GUID,
        "StubInstanceId": DEVICE_STUB_INSTANCE_ID,
    }


@pytest.fixture
def mock_run_usbipd_state(
        sample_device_data: MagicMock
    ) -> Generator[MagicMock | AsyncMock, Any, None]:
    """Fixture to mock run_usbipd_state globally for tests."""

    mock_device = USBIPDDevice(**sample_device_data)
    with patch(
        "picolynx.__main__.run_usbipd_state", return_value=[mock_device]
    ) as mock:
        yield mock