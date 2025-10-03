""""""
from ctypes import Structure, wintypes
from enum import IntEnum
from uuid import UUID


GUID_DEVINTERFACE_COMPORT = UUID("{86E0D1E0-8089-11D0-9CE4-08003E301F73}")
GUID_DEVINTERFACE_DISK = UUID("{53F56307-B6BF-11D0-94F2-00A0C91EFB8B}")
GUID_DEVINTERFACE_PARALLEL = UUID("{97F76EF0-F883-11D0-AF1F-0000F800845C}")
GUID_DEVINTERFACE_USB_DEVICE = UUID("{A5DCBF10-6530-11D2-901F-00C04FB951ED}")
GUID_DEVINTERFACE_USB_HOST_CONTROLLER = UUID("{3ABF6F2D-71C4-462A-8A92-1E6861E6AF27}")
GUID_DEVINTERFACE_USB_HUB = UUID("{F18A0E88-C30C-11D0-8815-00A0C906BED8}")
GUID_DEVINTERFACE_VOLUME = UUID("{53F5630D-B6BF-11D0-94F2-00A0C91EFB8B}")


class DBCDeviceType(IntEnum):
    """Device types for Device Broadcast structures.

    Attributes:
        DBT_DEVTYP_DEVICEINTERFACE: Class of devices. The structure is
            `DEV_BROADCAST_DEVICEINTERFACE`.

        DBT_DEVTYP_HANDLE: File system handle. The structure is
            `DEV_BROADCAST_HANDLE`.

        DBT_DEVTYP_OEM: OEM- or IHV-defined device type. The structure is a
            `DEV_BROADCAST_OEM`.

        DBT_DEVTYP_PORT: Serial or parallel port device. The structure is a
            `DEV_BROADCAST_PORT`.

        DBT_DEVTYP_VOLUME: Logical volume. The structure is a
            `DEV_BROADCAST_VOLUME`
    """
    DBT_DEVTYP_OEM = 0x00000000
    DBT_DEVTYP_VOLUME = 0x00000002
    DBT_DEVTYP_PORT = 0x00000003
    DBT_DEVTYP_DEVICEINTERFACE = 0x00000005
    DBT_DEVTYP_HANDLE = 0x00000006


class DBCEvent(IntEnum):
    """Device Broadcast event enumerations.
    
    Attributes:
        DBT_DEVNODES_CHANGED: A device has been added to or removed from the
            system.

        DBT_QUERYCHANGECONFIG: Permission is requested to change the current
            configuration due to a dock or undock.

        DBT_CONFIGCHANGED: The current configuration has changed, due to a
            dock or undock.

        DBT_CONFIGCHANGECANCELED: A request to change the current
            configuration due to a dock or undock has been canceled.

        DBT_DEVICEARRIVAL: A device has been inserted and is available.

        DBT_DEVICEQUERYREMOVE: Permission is requested to remove a device.

        DBT_DEVICEQUERYREMOVEFAILED: A request to remove a device has been
            canceled.

        DBT_DEVICEREMOVEPENDING: A device is about to be removed. Cannot be
            denied.

        DBT_DEVICEREMOVECOMPLETE: A device has been removed.

        DBT_DEVICETYPESPECIFIC: A device-specific event has occurred.

        DBT_CUSTOMEVENT: A custom event has occurred.

        DBT_USERDEFINED: The meaning of this message is user-defined.
    """
    DBT_DEVNODES_CHANGED = 0x0007
    DBT_DEVICEARRIVAL = 0x8000
    DBT_DEVICEQUERYREMOVE = 0x8001
    DBT_DEVICEQUERYREMOVEFAILED = 0x8002
    DBT_DEVICEREMOVEPENDING = 0x8003
    DBT_DEVICEREMOVECOMPLETE = 0x8004
    DBT_DEVICETYPESPECIFIC = 0x8005
    DBT_CUSTOMEVENT = 0x8006
    DBT_QUERYCHANGECONFIG = 0x0017
    DBT_CONFIGCHANGED = 0x0018
    DBT_CONFIGCHANGECANCELED = 0x0019
    DBT_USERDEFINED = 0xFFFF


class DBCVolumeFlags(IntEnum):
    """Device broadcast volume flags.

    Attributes:
        DBTF_MEDIA: Change affects media in drive.

        DBTF_NET: Indicated logical volume is a network volume.
    """

    DBTF_MEDIA = 0x0001
    DBTF_NET = 0x0002


class DEV_BROADCAST_DEVICEINTERFACE_W(Structure):
    """Contains information about a class of devices
    
    Attributes:
        dbcc_size: The size of this structure, in bytes.

        dbcc_devicetype: Set to `DBT_DEVTYP_DEVICEINTERFACE`.

        dbcc_reserved: Reserved; do not use.

        dbcc_classguid: The GUID for the interface device class.

        dbcc_name: A null-terminated string for the device name.
    """
    _fields_ = [
        ('dbcc_size', wintypes.DWORD),
        ('dbcc_devicetype', wintypes.DWORD),
        ('dbcc_reserved', wintypes.DWORD),
        ('dbcc_classguid', wintypes.BYTE * 16),
        ('dbcc_name', wintypes.WCHAR * 1)
    ]


class DEV_BROADCAST_HDR(Structure):
    """Standard header for information related to a device event.

    Attributes:
        dbch_size: The size of this structure, in bytes.

        dbch_devicetype: The device type (`DBCDeviceType`).
        
        dbch_reserved: Reserved; do not use.
    """
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD)
    ]


class DEV_BROADCAST_OEM(Structure):
    """Contains information about a modem, serial, or parallel port.

    Attributes:
        dbco_size: The size of this structure, in bytes.

        dbco_devicetype: Set to `DBT_DEVTYP_OEM`.

        dbco_reserved: Reserved; do not use.

        dbco_identifier: The OEM-specific identifier for the device.

        dbco_suppfunc: The OEM-specific function value. Possible values depend
            on the device.
    """
    _fields_ = [
        ("dbco_size", wintypes.DWORD),
        ("dbco_devicetype", wintypes.DWORD),
        ("dbco_reserved", wintypes.DWORD),
        ("dbco_identifier", wintypes.DWORD),
        ("dbco_suppfunc", wintypes.DWORD),
    ]


class DEV_BROADCAST_PORT_A(Structure):
    """Contains information about a modem/serial/parallel port (ANSI).

    Attributes:
        dbcp_size: The size of this structure, in bytes, including the actual
            length of the `dbcp_name`.

        dbcp_devicetype: Set to `DBT_DEVTYP_PORT`.

        dbcp_reserved: Reserved; do not use.

        dbcp_name: A null-terminated string specifying the friendly name of
            the port or the device connected.
        """
    _fields_ = [
        ("dbcp_size", wintypes.DWORD),
        ("dbcp_devicetype", wintypes.DWORD),
        ("dbcp_reserved", wintypes.DWORD),
        ("dbcp_name", wintypes.CHAR * 1),
    ]


class DEV_BROADCAST_PORT_W(Structure):
    """Contains information about a modem/serial/parallel port (WIDE).

    Attributes:
        dbcp_size: The size of this structure, in bytes, including the actual
            length of the `dbcp_name`.

        dbcp_devicetype: Set to `DBT_DEVTYP_PORT`.

        dbcp_reserved: Reserved; do not use.

        dbcp_name: A null-terminated string specifying the friendly name of
            the port or the device connected.
        """
    _fields_ = [
        ("dbcp_size", wintypes.DWORD),
        ("dbcp_devicetype", wintypes.DWORD),
        ("dbcp_reserved", wintypes.DWORD),
        ("dbcp_name", wintypes.WCHAR * 1),
    ]


class DEV_BROADCAST_VOLUME(Structure):
    """Contains information about a logical volume.
    
    Attributes:
        dbcv_size: The size of this structure, in bytes.

        dbcv_devicetype: Set to `DBT_DEVTYP_VOLUME`.

        dbcv_reserved: Reserved; do not use.

        dbcv_unitmask: The logical unit mask identifying one or more logical
            units. Each bit in the mask corresponds to one logical drive.

        dbcv_flags: This parameter can be `DBCVolumeFlags.DBTF_MEDIA` or
            `DBVolumeFlags.DBTF_NET`.
    """
    _fields_ = [
        ("dbcv_size", wintypes.DWORD),
        ("dbcv_devicetype", wintypes.DWORD),
        ("dbcv_reserved", wintypes.DWORD),
        ("dbcv_unitmask", wintypes.DWORD),
        ("dbcv_flags", wintypes.WORD)
    ]
