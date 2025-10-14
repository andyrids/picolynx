# PicoLynx - Attach Microcontrollers to WSL

PicoLynx is a Windows-only TUI (Text-based User Interface) application for attaching and detaching microcontroller devices to WSL (Windows Subsystem for Linux) distributions. It monitors Windows [`WM_DEVICECHANGE`](https://learn.microsoft.com/en-us/windows/win32/devio/wm-devicechange) messages
with `pywin32` and leverages `usbipd-win` to manage device connections.

![PicoLynx TUI](docs/img/picolynx.png)

https://github.com/user-attachments/assets/d5382270-cae8-4eb4-90a6-28ccb96e5250

## Features

- **Manual control**: Easily attach, bind, detach, or unbind devices using keyboard shortcuts.
- **Live device table**: View connected and persisted devices in real time.
- **Windows message monitoring**: Reacts instantly to hardware changes.
- **Thread-safe**: Ensures safe device operations even with concurrent events.
- **Beautiful TUI**: Built with `Textual` for a modern terminal experience & many theme options.
- **Auto-attachment (TODO)**: Detects devices as they are connected & automatically attaches to WSL.

## Requirements

Windows 10/11 is the only supported platform, given the nature of this package. `PicoLynx` requires administrator privileges to interact with USB devices. If not run as administrator, it will prompt for elevation.

### Install `usbipd-win`

This tool enables sharing locally connected USB devices to other machines, including Hyper-V guests and WSL 2. Full instructions are available @ [usbipd-win Github](https://github.com/dorssel/usbipd-win). Window package manager can be used to install the tool:

```sh
winget install usbipd
```

### Install `WSL`

Microsoft WSL documentation is available @ [learn.microsoft.com](https://learn.microsoft.com/en-us/windows/wsl/install). The following Windows features are required, which can be enabled by searching for 'Turn Windows features on or off' in the Start Menu:

- Virtual Machine Platform
- Windows Hypervisor Platform
- Windows Subsystem for Linux

Its worth updating WSL if newly enabled:

```sh
wsl --update
```

To install a Linux distribution, refer to the guide listed above.

## `PicoLynx` Installation

[Astral uv](https://docs.astral.sh/uv/) package manager is recommended for a fast, isolated, and reliable install. To install `uv`, use the following command:

```sh
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

You can install `PicoLynx` globally with the following `uv` command:

```sh
uv tool install picolynx
```

Or:

```sh
uv tool install "git+https://github.com/andyrids/picolynx.git"
```

You can run `PicoLynx` without installing, by running the following command:

```sh
uvx picolynx
```

Or:

```sh
uvx "git+https://github.com/andyrids/picolynx.git"
```

## Keyboard Shortcuts

| Key | Action |
| --- | ------ |
|  a  | Attach |
|  b  | Bind   |
|  d  | Detach |
|  u  | Unbind |

Select a device in the table and press the corresponding key to perform the action.

## Development

The `just` command runner ([GitHub page](https://github.com/casey/just)) is a handy way to save and run project-specific commands, which are written in a file called `justfile`.

If you use `just`, you can add use the commands below to run `PicoLynx` in development mode, with the `textual` console integration:

This command uses `uv` to sync the package dependencies and create a `.venv`:

```sh
just sync
```

Alias for:

```sh
uv sync
```

Running the command below in one terminal, will activate the `textual` console:

```sh
just console
```

Alias for:

```sh
uv run textual console -x EVENT -x SYSTEM
```

Running this command will run `PicoLynx` in development mode.

```sh
just dev
```

Alias for:

```sh
uv run textual run --dev src/picolynx/__main__.py
```

## Acknowledgements

- [`usbipd-win`](https://github.com/dorssel/usbipd-win)
- [`textual`](https://textual.textualize.io/)
- [`textual-cookbook`](https://github.com/ttygroup/textual-cookbook)
- [`transcendent-textual`](https://github.com/Textualize/transcendent-textual)
- [`Astral uv`](https://docs.astral.sh/uv/)
- [`just`](https://github.com/casey/just)
