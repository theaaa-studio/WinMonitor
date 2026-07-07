# WinMonitor

A lightweight, elegant, and non-intrusive hardware system monitor for Windows. It runs as a thin status bar that floats on or right above the taskbar in the bottom-right corner of the screen.

## Features
- **Real-Time Data**: Dynamic text display showing CPU%, RAM%, GPU% (if available), and network speeds (Upload/Download).
- **Temperatures**: Displays CPU package and GPU core temperatures (via LibreHardwareMonitor).
- **Draggable**: Drag with your left mouse button to position it anywhere on your screen.
- **Auto-Sizing**: Automatically shrinks or grows to fit the active text perfectly.
- **Fixed Right Anchor**: Auto-resizes from the left side, keeping the right edge fixed exactly where you position it.
- **Auto-Run**: Toggle "Start with Windows" directly from the right-click menu or the system tray icon to enable/disable starting on boot.
- **Lightweight**: Minimal CPU and RAM footprint.

## Requirements
Ensure you have the following installed:
- Python 3.10+
- `psutil`
- `pillow`
- `pystray`
- `pynvml` (for NVIDIA GPU tracking)
- `wmi` (for CPU/GPU temperature tracking via LibreHardwareMonitor)

To install dependencies:
```bash
pip install psutil pillow pystray pynvml wmi
```

## Running the Script
To start WinMonitor:
```bash
python WinMonitor.py
```

## Compiling to Executable (.exe)
You can bundle the script into a standalone Windows executable using PyInstaller:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build the executable:
   ```bash
   pyinstaller --onefile --noconsole --name=WinMonitor WinMonitor.py
   ```
3. The compiled `WinMonitor.exe` will be located inside the `dist/` directory.

## License
MIT License
