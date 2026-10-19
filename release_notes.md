# WinMonitor 1.2

WinMonitor 1.2 introduces full system tray integration with live CPU gauge and tooltip stats, smooth debounced collapsed mode, enhanced multi-monitor dragging, and background minimize-to-tray support.

---

## What's New in v1.2

- **Interactive System Tray Icon:**
  - Added live circular CPU usage gauge in the Windows notification area tray.
  - Added real-time stats tooltip showing CPU%, RAM%, Disks, GPU%, and network upload/download speeds on hover.
  - Added comprehensive tray right-click menu to toggle the floating bar, toggle modules, switch collapsed mode, set temperature thresholds, toggle startup on boot, or exit.
  - Double-clicking the tray icon toggles floating bar visibility.

- **Minimize to Tray (Background Operation):**
  - Closing the floating bar (`Alt+F4` or close signal) now withdraws it to run silently in the background tray instead of quitting.
  - Saves floating bar visibility (`show_bar`) in `winmonitor_config.json`.
  - Re-mapped exit actions to clean shutdown via context menu or tray menu "Exit".

- **Smooth Collapsed Mode & Flicker Fix:**
  - Debounced (150 ms) hover expansion and screen-coordinate hit-testing (`winfo_rootx`, `winfo_pointerxy`) eliminates rapid expanding/collapsing flickering loops.
  - Added geometry caching (`_last_geo`) to prevent redundant Tkinter layout recalculations on idle frames.

- **Enhanced Multi-Monitor & DPI-Aware Dragging:**
  - Switched from canvas-relative coordinates to absolute screen coordinates (`event.x_root`), enabling smooth movement across multiple displays (including monitors placed with negative coordinates).
  - Anchors the right edge to the internally requested width rather than `winfo_width()`, preventing position shifting across monitors with different DPI scalings.

- **Centered Gauge Labeling:**
  - Calculated exact font ink bounds via `draw.textbbox()` to mathematically center numbers in the tray gauge icon.
  - Capped tray percentage at `99%` to prevent 3-digit overflow outside the circular gauge bounds.

- **Reliable Taskbar Button Suppression:**
  - Updated tool-window styling (`WS_EX_TOOLWINDOW`) to target `GetAncestor(root.winfo_id(), GA_ROOT)` to ensure the taskbar button remains hidden across display and visibility changes.

---

## Key Features

- **Real-Time Data:** View CPU%, RAM%, GPU%, network speeds (Upload/Download), and per-drive disk performance active times.
- **Drive Selection System:** Enable or disable individual disk drives (e.g. show only `D:`) from the **Select Disks** context menu.
- **Customizable Visibility:** Toggle individual modules (CPU, RAM, Disk, GPU, Network) on/off directly from the right-click context menu.
- **Always on Top & Draggable:** Drag to position anywhere. Auto-resizes from the left side, keeping the right edge fixed.
- **Temperature Monitoring:** Displays CPU package and GPU core temperatures with configurable visual alerts.
- **Auto-Run:** "Startup App" toggle available in both the bar context menu and the tray menu.
- **Configuration Persistence:** Settings are saved locally to `winmonitor_config.json` and persist across runs.
- **Lightweight:** Minimal CPU and RAM footprint.

---

## Installation & Running

Download `WinMonitor.exe` attached to this release and run it directly. No Python installation is required.

> **Note:** On Windows 11, the tray icon may initially appear in the hidden notification icons overflow area (click the `^` chevron next to the clock). Drag it onto the main taskbar for permanent visibility.

*Released under the MIT License.*
