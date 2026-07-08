import psutil
import time
import threading
import tkinter as tk
from tkinter import simpledialog
import sys
import winreg
import os
import json
import ctypes
import math

try:
    import pynvml
    pynvml.nvmlInit()
    gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    HAS_GPU = True
except Exception:
    HAS_GPU = False

try:
    import wmi
    try:
        w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
        HAS_WMI = True
    except Exception:
        try:
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            HAS_WMI = True
        except Exception:
            HAS_WMI = False
except Exception:
    HAS_WMI = False

try:
    import win32pdh
    HAS_PDH = True
except Exception:
    HAS_PDH = False

UPDATE_MS = 2000  # update interval

state = {
    'cpu_percent': 0.0,
    'ram_percent': 0.0,
    'cpu_temp': None,
    'gpu_percent': None,
    'gpu_temp': None,
    'net_up': 0.0,
    'net_down': 0.0,
    'disks': [],
    'show_cpu': True,
    'show_ram': True,
    'show_gpu': True,
    'show_disk': True,
    'show_network': True,
    'running': True,
    'temp_threshold': 80.0,
    'collapsed_mode': True,
    'expanded': False,
    'show_floating_bar': True
}

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__)), "winmonitor_config.json")

def load_config():
    try:
        path = CONFIG_FILE
        if not os.path.exists(path):
            path = os.path.join(os.path.expanduser("~"), "winmonitor_config.json")
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                state['show_cpu'] = data.get('show_cpu', True)
                state['show_ram'] = data.get('show_ram', True)
                state['show_gpu'] = data.get('show_gpu', True)
                state['show_disk'] = data.get('show_disk', True)
                state['show_network'] = data.get('show_network', True)
                state['temp_threshold'] = data.get('temp_threshold', 80.0)
                state['collapsed_mode'] = data.get('collapsed_mode', True)
                state['show_floating_bar'] = data.get('show_floating_bar', True)
    except Exception as e:
        print("Failed to load config:", e)

def save_config():
    try:
        data = {
            'show_cpu': state['show_cpu'],
            'show_ram': state['show_ram'],
            'show_gpu': state['show_gpu'],
            'show_disk': state['show_disk'],
            'show_network': state['show_network'],
            'temp_threshold': state['temp_threshold'],
            'collapsed_mode': state['collapsed_mode'],
            'show_floating_bar': state['show_floating_bar']
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except PermissionError:
            user_config = os.path.join(os.path.expanduser("~"), "winmonitor_config.json")
            with open(user_config, 'w') as f:
                json.dump(data, f, indent=4)
    except Exception as e:
        print("Failed to save config:", e)

def toggle_module(module):
    key = f"show_{module}"
    state[key] = not state[key]
    save_config()
    if root and canvas:
        root.after(0, lambda: draw_bar(canvas))

load_config()

icon = None
root = None
canvas = None
right_edge_anchor = None
bar_y = None

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "WinMonitor"


def is_autorun_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, REG_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def toggle_autorun():
    if getattr(sys, 'frozen', False):
        app_path = sys.executable
    else:
        app_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        
    if is_autorun_enabled():
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, REG_NAME)
            winreg.CloseKey(key)
            print("Autorun disabled.")
        except Exception as e:
            print("Failed to disable autorun:", e)
    else:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, app_path)
            winreg.CloseKey(key)
            print("Autorun enabled for path:", app_path)
        except Exception as e:
            print("Failed to enable autorun:", e)


def toggle_autorun_from_tray(icon, item):
    toggle_autorun()


class CoreTempSharedDataEx(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("uiLoad", ctypes.c_uint * 256),
        ("uiTjMax", ctypes.c_uint * 128),
        ("uiCoreCnt", ctypes.c_uint),
        ("uiCPUCnt", ctypes.c_uint),
        ("fTemp", ctypes.c_float * 256),
        ("fVID", ctypes.c_float),
        ("fCPUSpeed", ctypes.c_float),
        ("fFSBSpeed", ctypes.c_float),
        ("fMultiplier", ctypes.c_float),
        ("sCPUName", ctypes.c_char * 100),
        ("ucFahrenheit", ctypes.c_ubyte),
        ("ucDeltaToTjMax", ctypes.c_ubyte),
        ("ucTdpSupported", ctypes.c_ubyte),
        ("ucPowerSupported", ctypes.c_ubyte),
        ("uiStructVersion", ctypes.c_uint),
        ("uiTdp", ctypes.c_uint * 128),
        ("fPower", ctypes.c_float * 128),
        ("fMultipliers", ctypes.c_float * 256),
    ]

def get_coretemp_temperature():
    try:
        hMapFile = ctypes.windll.kernel32.OpenFileMappingW(4, False, "CoreTempSharedData")
        if not hMapFile:
            return None
        pBuf = ctypes.windll.kernel32.MapViewOfFile(hMapFile, 4, 0, 0, 0)
        if not pBuf:
            ctypes.windll.kernel32.CloseHandle(hMapFile)
            return None
        try:
            data = CoreTempSharedDataEx.from_address(pBuf)
            if data.uiCoreCnt > 0:
                temps = [data.fTemp[i] for i in range(data.uiCoreCnt)]
                is_fahrenheit = bool(data.ucFahrenheit)
                raw_temp = max(temps) if temps else None
                if raw_temp is not None and is_fahrenheit:
                    raw_temp = (raw_temp - 32) * 5 / 9
                return raw_temp
        finally:
            ctypes.windll.kernel32.UnmapViewOfFile(pBuf)
            ctypes.windll.kernel32.CloseHandle(hMapFile)
    except Exception:
        pass
    return None

def get_temps():
    cpu_t, gpu_t = None, None
    
    # Try CoreTemp shared memory first
    cpu_t = get_coretemp_temperature()
    
    # Fallback to WMI if CoreTemp is not running/available
    if cpu_t is None and HAS_WMI:
        try:
            for s in w.Sensor():
                if s.SensorType == 'Temperature':
                    if cpu_t is None and 'CPU Package' in s.Name:
                        cpu_t = s.Value
                    elif gpu_t is None and 'GPU' in s.Name:
                        gpu_t = s.Value
                if cpu_t and gpu_t:
                    break
        except Exception:
            pass
    elif HAS_WMI:
        # If we got CPU temp from CoreTemp, still try to find GPU temp from WMI
        try:
            for s in w.Sensor():
                if s.SensorType == 'Temperature' and 'GPU' in s.Name:
                    gpu_t = s.Value
                    break
        except Exception:
            pass
            
    # Try NVML for GPU temp if WMI did not provide it
    if gpu_t is None and HAS_GPU:
        try:
            gpu_t = pynvml.nvmlDeviceGetTemperature(gpu_handle, 0)
        except Exception:
            pass
            
    return cpu_t, gpu_t


def make_gauge_icon(percent, size=(64, 64)):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    w_px, h_px = size
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("Segoe UI", 20)
    except Exception:
        try:
            font_large = ImageFont.truetype("seguisym.ttf", 20)
        except Exception:
            font_large = ImageFont.load_default()

    cx, cy = w_px // 2, h_px // 2
    radius = min(w_px, h_px) // 2 - 4
    
    # Background track (thin ring)
    draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=0, end=360, fill=(80, 80, 80, 255), width=4)

    # Active progress arc
    start = -90
    end = int(start + 360 * (percent / 100.0))
    if percent > 0:
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=start, end=end, fill=(255, 255, 255, 255), width=4)

    # Percentage text
    pct_text = f"{int(percent)}"
    try:
        bbox = draw.textbbox((0, 0), pct_text, font=font_large)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        try:
            tw, th = font_large.getsize(pct_text)
        except Exception:
            tw, th = 15, 15
            
    draw.text((cx - tw / 2, cy - th / 2 - 2), pct_text, font=font_large, fill=(255, 255, 255, 255))

    return img


def draw_monitor(canvas, x_offset=12, y_offset=12, color="#888888"):
    # Screen outline
    canvas.create_rectangle(x_offset - 8, y_offset - 7, x_offset + 8, y_offset + 3, outline=color, width=2)
    # Stand neck
    canvas.create_line(x_offset, y_offset + 3, x_offset, y_offset + 6, fill=color, width=2)
    # Base
    canvas.create_line(x_offset - 4, y_offset + 6, x_offset + 4, y_offset + 6, fill=color, width=2)

def draw_flame(canvas, x_offset=12, y_offset=12, color="#ff3300"):
    # Simple flame polygon points relative to center (x_offset, y_offset)
    points = [
        x_offset, y_offset - 8,
        x_offset - 3, y_offset - 4,
        x_offset - 5, y_offset,
        x_offset - 5, y_offset + 4,
        x_offset - 2, y_offset + 7,
        x_offset, y_offset + 8,
        x_offset + 2, y_offset + 7,
        x_offset + 5, y_offset + 4,
        x_offset + 5, y_offset,
        x_offset + 3, y_offset - 4
    ]
    canvas.create_polygon(points, fill=color, outline=color, smooth=True)
    inner_points = [
        x_offset, y_offset - 3,
        x_offset - 2, y_offset,
        x_offset - 2, y_offset + 3,
        x_offset, y_offset + 5,
        x_offset + 2, y_offset + 3,
        x_offset + 2, y_offset
    ]
    canvas.create_polygon(inner_points, fill="#ffea00", outline="#ffea00", smooth=True)

def draw_bar(canvas):
    canvas.delete('all')
    
    cpu = state['cpu_percent']
    ram = state['ram_percent']
    cpu_temp = state['cpu_temp']
    gpu = state['gpu_percent']
    gpu_temp = state['gpu_temp']
    up = state['net_up']
    down = state['net_down']
    
    def fmt_speed(kb_s):
        if kb_s >= 1024:
            return f"{kb_s/1024:.1f} MB/s"
        return f"{kb_s:.0f} KB/s"
        
    global right_edge_anchor, bar_y
    
    # Check if collapsed mode is active and we are not hovered/expanded
    if state.get('collapsed_mode', True) and not state.get('expanded', False):
        cpu_t = state.get('cpu_temp')
        gpu_t = state.get('gpu_temp')
        threshold = state.get('temp_threshold', 80.0)
        
        high_temp = False
        if cpu_t is not None and cpu_t >= threshold:
            high_temp = True
        if gpu_t is not None and gpu_t >= threshold:
            high_temp = True
            
        if high_temp:
            draw_flame(canvas, 12, 12, "#ff3300")
        else:
            draw_monitor(canvas, 12, 12, "#888888")
            
        new_win_w = 24
    else:
        parts = []
        def add_divider():
            if parts:
                parts.append(("  |  ", "#888888"))
                
        if state.get('show_cpu', True):
            parts.append(("CPU ", "#888888"))
            cpu_val = f"{cpu:.0f}%"
            if cpu_temp:
                cpu_val += f" ({cpu_temp:.0f}°C)"
            parts.append((cpu_val, "#00e1ff"))
            
        if state.get('show_ram', True):
            add_divider()
            parts.append(("RAM ", "#888888"))
            parts.append((f"{ram:.0f}%", "#ffea00"))
            
        if state.get('show_disk', True):
            disks = state.get('disks', [])
            for i, disk in enumerate(disks):
                if i == 0:
                    add_divider()
                else:
                    parts.append(("   ", "#888888"))
                parts.append((f"{disk['label']}: ↑ ", "#888888"))
                parts.append((f"{disk['read']:.0f}%", "#00ff88"))
                parts.append((" ↓ ", "#888888"))
                parts.append((f"{disk['write']:.0f}%", "#00ff88"))
                
        if state.get('show_gpu', True) and HAS_GPU and gpu is not None:
            add_divider()
            parts.append(("GPU ", "#888888"))
            gpu_val = f"{gpu:.0f}%"
            if gpu_temp:
                gpu_val += f" ({gpu_temp:.0f}°C)"
            parts.append((gpu_val, "#ff007f"))
            
        if state.get('show_network', True):
            add_divider()
            parts.append(("↑ ", "#888888"))
            parts.append((f"{fmt_speed(up)}", "#ff7700"))
            parts.append(("  ↓ ", "#888888"))
            parts.append((f"{fmt_speed(down)}", "#00a2ff"))
            
        if not parts:
            parts.append(("WinMonitor (All hidden)", "#888888"))
            
        x = 5
        y = 12
        for text, color in parts:
            txt_id = canvas.create_text(x, y, text=text, fill=color, font=("Segoe UI", 9, "bold"), anchor="w", tags="text_group")
            bbox = canvas.bbox(txt_id)
            if bbox:
                x = bbox[2]
                
        new_win_w = int(x) + 5
        
    canvas.config(width=new_win_w)
    
    if root:
        if bar_y is None:
            bar_y = root.winfo_y()
        if right_edge_anchor is None:
            right_edge_anchor = root.winfo_x() + root.winfo_width()
        new_x = right_edge_anchor - new_win_w
        root.geometry(f"{new_win_w}x24+{new_x}+{bar_y}")


flash_state = False

def flash_loop():
    global flash_state
    if not state['running'] or canvas is None:
        return
        
    cpu_t = state.get('cpu_temp')
    gpu_t = state.get('gpu_temp')
    threshold = state.get('temp_threshold', 80.0)
    
    high_temp = False
    if cpu_t is not None and cpu_t >= threshold:
        high_temp = True
    if gpu_t is not None and gpu_t >= threshold:
        high_temp = True
        
    if high_temp:
        flash_state = not flash_state
        bg_color = '#550000' if flash_state else '#0a0a0c'
        canvas.config(bg=bg_color)
        root.config(bg=bg_color)
    else:
        canvas.config(bg='#0a0a0c')
        root.config(bg='#0a0a0c')
        flash_state = False
        
    root.after(500, flash_loop)

def set_temp_threshold_dialog():
    new_val = simpledialog.askfloat(
        "Temperature Threshold",
        "Enter temperature threshold (°C) for warning alert:",
        initialvalue=state['temp_threshold'],
        minvalue=30.0,
        maxvalue=120.0,
        parent=root
    )
    if new_val is not None:
        state['temp_threshold'] = new_val
        save_config()

def on_enter(event):
    if state.get('collapsed_mode', True):
        state['expanded'] = True
        draw_bar(canvas)

def on_leave(event):
    if state.get('collapsed_mode', True):
        if root:
            x = root.winfo_x()
            y = root.winfo_y()
            w = root.winfo_width()
            h = root.winfo_height()
            mx, my = root.winfo_pointerxy()
            if not (x <= mx <= x + w and y <= my <= y + h):
                state['expanded'] = False
                draw_bar(canvas)

def toggle_collapsed_mode(icon=None, item=None):
    state['collapsed_mode'] = not state['collapsed_mode']
    if not state['collapsed_mode']:
        state['expanded'] = True
    else:
        state['expanded'] = False
    save_config()
    if root and canvas:
        root.after(0, lambda: draw_bar(canvas))

def set_floating_bar_visibility(visible):
    state['show_floating_bar'] = visible
    save_config()
    if root:
        root.after(0, apply_floating_bar_visibility)

def apply_floating_bar_visibility():
    if root:
        if state.get('show_floating_bar', True):
            root.deiconify()
            if canvas:
                draw_bar(canvas)
        else:
            root.withdraw()

def refresh_bar_ui():
    if not state['running'] or canvas is None:
        return
    draw_bar(canvas)
    if root:
        root.attributes('-topmost', True)
    root.after(1000, refresh_bar_ui)


def update_loop():
    global state, icon
    psutil.cpu_percent(interval=None)
    last_net = psutil.net_io_counters()
    last_time = time.time()
    
    pdh_query = None
    disk_counters = {}
    if HAS_PDH:
        try:
            pdh_query = win32pdh.OpenQuery()
            _, instances = win32pdh.EnumObjectItems(None, None, 'PhysicalDisk', win32pdh.PERF_DETAIL_WIZARD)
            for inst in instances:
                if inst == '_Total':
                    continue
                import re
                letters = re.findall(r'([A-Za-z]):', inst)
                label = "/".join(letters) if letters else inst
                r_counter = win32pdh.AddEnglishCounter(pdh_query, rf'\PhysicalDisk({inst})\% Disk Read Time')
                w_counter = win32pdh.AddEnglishCounter(pdh_query, rf'\PhysicalDisk({inst})\% Disk Write Time')
                disk_counters[inst] = {
                    'label': label,
                    'read_counter': r_counter,
                    'write_counter': w_counter
                }
            win32pdh.CollectQueryData(pdh_query)
        except Exception as e:
            print("Failed to initialize win32pdh disk counters:", e)
            pdh_query = None
            
    while state['running']:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        
        now = time.time()
        net = psutil.net_io_counters()
        dt = now - last_time if now - last_time > 0 else 1.0
        up = (net.bytes_sent - last_net.bytes_sent) / dt / 1024.0
        down = (net.bytes_recv - last_net.bytes_recv) / dt / 1024.0
        last_net = net
        last_time = now
        
        cpu_temp, gpu_temp = get_temps()
        
        gpu_percent = None
        if HAS_GPU:
            try:
                gpu_percent = pynvml.nvmlDeviceGetUtilizationRates(gpu_handle).gpu
            except Exception:
                gpu_percent = None
                
        state['cpu_percent'] = cpu
        state['ram_percent'] = ram
        state['cpu_temp'] = cpu_temp
        state['gpu_percent'] = gpu_percent
        state['gpu_temp'] = gpu_temp
        state['net_up'] = up
        state['net_down'] = down
        
        disks_data = []
        if pdh_query:
            try:
                win32pdh.CollectQueryData(pdh_query)
                for inst, counters in disk_counters.items():
                    _, val_read = win32pdh.GetFormattedCounterValue(counters['read_counter'], win32pdh.PDH_FMT_DOUBLE)
                    _, val_write = win32pdh.GetFormattedCounterValue(counters['write_counter'], win32pdh.PDH_FMT_DOUBLE)
                    disks_data.append({
                        'label': counters['label'],
                        'read': max(0.0, min(100.0, val_read)),
                        'write': max(0.0, min(100.0, val_write))
                    })
            except Exception:
                pass
        state['disks'] = disks_data
        
        def fmt_speed(kb_s):
            if kb_s >= 1024:
                return f"{kb_s/1024:.1f}M"
            return f"{kb_s:.0f}K"
            
        up_text = fmt_speed(up)
        down_text = fmt_speed(down)
        
        img = make_gauge_icon(cpu)
        if img and icon:
            icon.icon = img
            
        tooltip = ""
        if state.get('show_cpu', True):
            tooltip += f"CPU: {cpu:.0f}%"
            if cpu_temp:
                tooltip += f" ({cpu_temp:.0f}°C)"
            tooltip += " | "
        if state.get('show_ram', True):
            tooltip += f"RAM: {ram:.0f}% | "
        if tooltip.endswith(" | "):
            tooltip = tooltip[:-3]
        if tooltip:
            tooltip += "\n"
        if state.get('show_disk', True) and disks_data:
            disk_strs = [f"{d['label']}: ↑{d['read']:.0f}% ↓{d['write']:.0f}%" for d in disks_data]
            tooltip += f"Disks: {' '.join(disk_strs)}\n"
        if state.get('show_gpu', True) and HAS_GPU and gpu_percent is not None:
            tooltip += f"GPU: {gpu_percent:.0f}%"
            if gpu_temp:
                tooltip += f" ({gpu_temp:.0f}°C)"
            tooltip += "\n"
        if state.get('show_network', True):
            tooltip += f"Up: {up_text}/s | Down: {down_text}/s"
        tooltip = tooltip.strip()
        if not tooltip:
            tooltip = "WinMonitor"
            
        if icon:
            icon.title = tooltip[:127]
            
        # Debug print status to terminal
        gpu_str = ""
        if HAS_GPU and gpu_percent is not None:
            gpu_t_str = f" ({gpu_temp:.0f}°C)" if gpu_temp else ""
            gpu_str = f" | GPU: {gpu_percent:.0f}%{gpu_t_str}"
        cpu_t_str = f" ({cpu_temp:.0f}°C)" if cpu_temp else ""
        disk_str = ""
        if disks_data:
            disk_strs = [f"{d['label']}:R:{d['read']:.0f}% W:{d['write']:.0f}%" for d in disks_data]
            disk_str = f" | Disks: {' '.join(disk_strs)}"
        print(f"[{time.strftime('%H:%M:%S')}] Active | CPU: {cpu:.0f}%{cpu_t_str} | RAM: {ram:.0f}%{disk_str}{gpu_str} | Up: {up_text}/s | Down: {down_text}/s")
            
        time.sleep(UPDATE_MS / 1000.0)
        
    if pdh_query:
        try:
            win32pdh.CloseQuery(pdh_query)
        except Exception:
            pass


def run_tray():
    global icon, root
    try:
        import pystray
    except Exception:
        return
        
    def on_exit(icon, item):
        state['running'] = False
        icon.stop()
        if root:
            root.after(0, root.destroy)

    icon = pystray.Icon('win-monitor')
    icon.title = 'WinMonitor'
    icon.menu = pystray.Menu(
        pystray.MenuItem('Show Modules', pystray.Menu(
            pystray.MenuItem('CPU', lambda item: toggle_module('cpu'), checked=lambda item: state['show_cpu']),
            pystray.MenuItem('RAM', lambda item: toggle_module('ram'), checked=lambda item: state['show_ram']),
            pystray.MenuItem('Disk', lambda item: toggle_module('disk'), checked=lambda item: state['show_disk']),
            pystray.MenuItem('GPU', lambda item: toggle_module('gpu'), checked=lambda item: state['show_gpu']),
            pystray.MenuItem('Network', lambda item: toggle_module('network'), checked=lambda item: state['show_network'])
        )),
        pystray.MenuItem('Collapsed Mode', toggle_collapsed_mode, checked=lambda item: state['collapsed_mode']),
        pystray.MenuItem('Show Floating Bar', lambda item: set_floating_bar_visibility(not state.get('show_floating_bar', True)), checked=lambda item: state.get('show_floating_bar', True)),
        pystray.MenuItem('Start with Windows', toggle_autorun_from_tray, checked=lambda item: is_autorun_enabled()),
        pystray.MenuItem('Exit', on_exit)
    )
    
    # Start updater thread
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()
    
    # Initial icon
    img = make_gauge_icon(0)
    if img:
        icon.icon = img
            
    try:
        icon.visible = True
    except Exception:
        pass
        
    try:
        icon.run()
    except Exception:
        pass


def on_exit_from_gui():
    state['running'] = False
    if icon:
        icon.stop()
    root.destroy()


if __name__ == '__main__':

            
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-alpha', 0.95)
    root.configure(bg='#0a0a0c')
    
    # Drag support
    def start_drag(event):
        root._drag_start_x = event.x
        root._drag_start_y = event.y

    def drag(event):
        global right_edge_anchor, bar_y
        x = root.winfo_x() + event.x - root._drag_start_x
        y = root.winfo_y() + event.y - root._drag_start_y
        root.geometry(f"+{x}+{y}")
        # Keep track of where the right edge is anchored
        right_edge_anchor = x + root.winfo_width()
        bar_y = y
        
    # Dimensions: start with a standard width, will auto-resize instantly
    win_w = 480 if HAS_GPU else 380
    win_h = 24
    
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    # Initial position: bottom right, right above the taskbar
    x = screen_w - win_w - 10
    y = screen_h - win_h - 40
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")
    
    # Initialize the right edge anchor and Y position point
    right_edge_anchor = x + win_w
    bar_y = y
    
    canvas = tk.Canvas(root, width=win_w, height=win_h, bg='#0a0a0c', highlightthickness=1, highlightbackground='#2a2a30')
    canvas.pack(fill='both', expand=True)
    
    canvas.bind("<ButtonPress-1>", start_drag)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<Enter>", on_enter)
    canvas.bind("<Leave>", on_leave)
    
    # Right click menu
    menu = tk.Menu(root, tearoff=0)
    
    show_menu = tk.Menu(menu, tearoff=0)
    
    show_cpu_var = tk.BooleanVar(value=state['show_cpu'])
    show_ram_var = tk.BooleanVar(value=state['show_ram'])
    show_disk_var = tk.BooleanVar(value=state['show_disk'])
    show_gpu_var = tk.BooleanVar(value=state['show_gpu'])
    show_network_var = tk.BooleanVar(value=state['show_network'])
    
    show_menu.add_checkbutton(label="CPU", variable=show_cpu_var, command=lambda: toggle_module('cpu'))
    show_menu.add_checkbutton(label="RAM", variable=show_ram_var, command=lambda: toggle_module('ram'))
    show_menu.add_checkbutton(label="Disk", variable=show_disk_var, command=lambda: toggle_module('disk'))
    show_menu.add_checkbutton(label="GPU", variable=show_gpu_var, command=lambda: toggle_module('gpu'))
    show_menu.add_checkbutton(label="Network", variable=show_network_var, command=lambda: toggle_module('network'))
    
    menu.add_cascade(label="Show Modules", menu=show_menu)
    menu.add_separator()
    
    collapsed_var = tk.BooleanVar(value=state['collapsed_mode'])
    menu.add_checkbutton(label="Collapsed Mode", variable=collapsed_var, command=toggle_collapsed_mode)
    
    show_floating_bar_var = tk.BooleanVar(value=state.get('show_floating_bar', True))
    menu.add_checkbutton(label="Show Floating Bar", variable=show_floating_bar_var, command=lambda: set_floating_bar_visibility(show_floating_bar_var.get()))
    
    menu.add_command(label="Set Temp Threshold...", command=set_temp_threshold_dialog)
    menu.add_separator()
    
    autorun_var = tk.BooleanVar(value=is_autorun_enabled())
    menu.add_checkbutton(label="Start with Windows", variable=autorun_var, command=toggle_autorun)
    menu.add_separator()
    menu.add_command(label="Exit", command=on_exit_from_gui)
    
    def show_context_menu(event):
        # Update checkbox status before showing menu
        autorun_var.set(is_autorun_enabled())
        show_cpu_var.set(state['show_cpu'])
        show_ram_var.set(state['show_ram'])
        show_disk_var.set(state['show_disk'])
        show_gpu_var.set(state['show_gpu'])
        show_network_var.set(state['show_network'])
        collapsed_var.set(state['collapsed_mode'])
        show_floating_bar_var.set(state.get('show_floating_bar', True))
        menu.post(event.x_root, event.y_root)
        
    canvas.bind("<Button-3>", show_context_menu)
    
    # Run tray icon in separate thread
    tray_thread = threading.Thread(target=run_tray, daemon=True)
    tray_thread.start()
    
    # Run GUI refresh loop
    refresh_bar_ui()
    
    # Hide window at startup if show_floating_bar is False
    if not state.get('show_floating_bar', True):
        root.withdraw()
    
    # Run temperature warning flashing loop
    flash_loop()
    
    root.mainloop()
