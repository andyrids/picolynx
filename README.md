# PicoLynx - Auto-attach Raspberry Pi Devices to WSL

PicoLynx is a TUI application that attaches and detaches Raspberry Pi Pico devices to any running WSL distributions, through monitoring of Windows PnP events and `usbipd-win`.

![TUI Logo](docs/img/picolynx_icon_250x250.png){:style="float: right;margin-right: 7px;margin-top: 7px;"}

PicoLynx is a Windows-only TUI (Text User Interface) application for automatically attaching and detaching Raspberry Pi Pico devices to any running WSL (Windows Subsystem for Linux) distributions. It monitors Windows Plug and Play (PnP) events and leverages usbipd-win to manage device connections seamlessly.

Features
Automatic Device Management: Detects Raspberry Pi Pico devices as they are connected/disconnected and attaches/detaches them to/from WSL distributions.
Manual Control: Easily attach, bind, detach, or unbind devices using keyboard shortcuts.
Live Device Table: View connected and persisted devices in real time.
Windows PnP Event Monitoring: Reacts instantly to hardware changes.
Thread-safe Operations: Ensures safe device operations even with concurrent events.
Beautiful TUI: Built with Textual for a modern terminal experience.
Requirements
Windows 10/11 (This application is Windows-only)
usbipd-win (must be installed and available in your PATH)
WSL with at least one running distribution
Python 3.11+ (recommended to use via Astral's uv package manager)
Installation
We recommend using the Astral uv package manager for a fast, isolated, and reliable install.

1. Install uv
Follow the instructions on the uv GitHub page to install uv for your platform.

2. Install PicoLynx
You can install PicoLynx globally using either of the following commands:

uv tool install [picolynx](VALID_FILE)
# or
uvx [picolynx](VALID_FILE)
This will install the picolynx command and all dependencies in an isolated environment.

Usage
Launching the TUI
Simply run:

[picolynx](VALID_FILE)
The TUI will open, displaying connected Raspberry Pi Pico devices and their status with WSL.

Keyboard Shortcuts
| Key | Action | |-----|---------------| | a | Attach | | b | Bind | | d | Detach | | u | Unbind |

Select a device in the table and press the corresponding key to perform the action.

Using with just
If you use the just command runner, you can add the following to your justfile for convenience:

# [justfile](VALID_FILE)
run:
    [picolynx](VALID_FILE)
Then simply run:

just run
Development
To run the application in development mode:

textual run --dev [src/picolynx/__main__.py](VALID_FILE)
For debugging with extra logging:

textual console -x DEBUG -x EVENT -x INFO -x SYSTEM
Troubleshooting
Administrator Rights: PicoLynx requires administrator privileges to interact with USB devices. If not run as administrator, it will prompt for elevation.
usbipd-win: Ensure usbipd-win is installed and available in your system PATH.
WSL: At least one WSL distribution must be installed and running.
License
[Missing link]

Acknowledgements
usbipd-win
Textual
Astral uv
just