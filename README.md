# PicoLynx - Auto-attach Raspberry Pi Devices to WSL

PicoLynx is a TUI application that attaches and detaches Raspberry Pi Pico devices to any running WSL distributions, through monitoring of Windows PnP events and `usbipd-win`.

![TUI Logo](docs/img/picolynx_icon_500x500.png)

```sh
textual console -x DEBUG -x EVENT -x INFO -x SYSTEM
textual console -x DEBUG -x EVENT
```

```sh
textual run --dev src/picolynx/__main__.py
```

    & > .datatable--odd-row {
        background: #131a2c;
    }
    & > .datatable--even-row {
        background: #0f1525;
    }