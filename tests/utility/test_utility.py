import pytest
from unittest.mock import patch, MagicMock

from picolynx.utility._utility import (
    is_administrator,
    is_pnp_audit,
    is_pnp_event,
    parse_instanceid,
)
from picolynx.exceptions import EnablePnPAuditError


# --- is_administrator ---
@patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1)
def test_is_administrator_when_true(mock_is_admin):
    """Test is_administrator when the user is an admin."""
    assert is_administrator() is True
    mock_is_admin.assert_called_once()

@patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0)
def test_is_administrator_when_false(mock_is_admin):
    """Test is_administrator when the user is not an admin."""
    assert is_administrator() is False
    mock_is_admin.assert_called_once()

# --- parse_instanceid ---
@pytest.mark.parametrize(
    "instance_id, expected",
    [
        (
            "USB\\VID_2E8A&PID_0005\\E6616407E3656C26",
            ("2E8A", "0005", "E6616407E3656C26"),
        ),
        (
            "USB\\VID_1234&PID_ABCD&MI_00\\7&12345678&0&0000",
            ("1234", "ABCD", "7&12345678&0&0000"), # Serial can be complex
        ),
        ("SOME_OTHER_STRING", ("UNK", "UNK", "UNK")),
        ("VID_FAIL&PID_FAIL\\SERIAL", ("UNK", "UNK", "UNK")),
    ],
)
def test_parse_instanceid(instance_id, expected):
    """Test parse_instanceid with various valid and invalid formats."""
    assert parse_instanceid(instance_id) == expected

# --- is_pnp_event ---
def test_is_pnp_event():
    """Test the is_pnp_event function."""
    mock_event_pnp = MagicMock()
    mock_event_pnp.EventID = 6416

    mock_event_not_pnp = MagicMock()
    mock_event_not_pnp.EventID = 1234

    assert is_pnp_event(mock_event_pnp) is True
    assert is_pnp_event(mock_event_not_pnp) is False

# --- is_pnp_audit ---
@patch("subprocess.Popen")
def test_is_pnp_audit_when_enabled(mock_popen):
    """Test is_pnp_audit when the audit policy is correctly set."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    # Simulate the CSV output from auditpol
    mock_stdout = (
        'Machine Name,Policy Target,Subcategory,Subcategory GUID,Inclusion Setting,Exclusion Setting,Setting Value\r\n'
        'WIN-123,System,"Plug and Play Events",{0cce959b-69ae-11d9-bed3-505054503030},Success and Failure,,'
    )
    mock_proc.communicate.return_value = (mock_stdout, "")
    mock_popen.return_value = mock_proc

    assert is_pnp_audit() is True

@patch("subprocess.Popen")
def test_is_pnp_audit_when_disabled(mock_popen):
    """Test is_pnp_audit when the audit policy is not set."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_stdout = (
        'Machine Name,Policy Target,Subcategory,Subcategory GUID,Inclusion Setting,Exclusion Setting,Setting Value\r\n'
        'WIN-123,System,"Plug and Play Events",{...},No Auditing,,'
    )
    mock_proc.communicate.return_value = (mock_stdout, "")
    mock_popen.return_value = mock_proc

    assert is_pnp_audit() is False

@patch("subprocess.Popen")
def test_is_pnp_audit_process_error(mock_popen):
    """Test is_pnp_audit when the subprocess returns an error."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("", "Error executing command")
    mock_popen.return_value = mock_proc

    with pytest.raises(EnablePnPAuditError, match="Error executing command"):
        is_pnp_audit()
