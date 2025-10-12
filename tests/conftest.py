"""Conftest fixtures for `pytest` unit test functions."""
from typing import Any
import pytest

@pytest.fixture
def sample_device_data() -> dict[str, Any]:
    """Provides a sample dictionary of USBIPD device data."""
    return {
        "Description": "USB Serial Device (COM1)",
        "InstanceId": "USB\\VID_2E8A&PID_0005\\E5DC12345678910",
        "BusId": "1-1",
        "ClientIPAddress": "127.0.0.1",
        "IsForced": False,
        "PersistedGuid": "da56d144-cc8e-4103-875e-15af35bf5fbf",
        "StubInstanceId": "USB\\Vid_80EE&Pid_CAFE\\E5DC12345678910",
    }
