# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-10-16

### Added

- Refresh (connections) key binding
- Support for USB storage devices

## [0.1.0] - 2025-10-14

### Added

- Newly connected devices are automatically selected
- Row selection on enter or row highlight with mouse/keyboard
- Created full unit test suite

### Changed

- Row highlighting for selected table rows
- DataTable layout and sizing, with a 100% height.

### Fixed

- Device removal race condition

## [0.1.dev37] - 2025-10-14

### Added

- Initial implementation of PicoLynx TUI for managing USBIPD devices on Windows.
- Device notification and message handling using Windows APIs.
- Thread-safe device operations and lock management.
- Custom TUI components: ConnectedTable, PersistedTable, AutoAttachedTable, TUIHeader, TUIFooter, TUINavigation.
- Device attach, bind, detach, and unbind actions.
- Windows device change event handling and incremental device updates.
- Utility functions for administrator check, PnP audit status, and instance ID parsing.
- Exception classes for PnP audit, USBIPD, and WSL errors.
- Enumerations and structures for device broadcast and USB-IF VID/PID values.
