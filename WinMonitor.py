import psutil
import time
import threading
import tkinter as tk
import sys
import winreg
import os

try:
    import pynvml
    pynvml.nvmlInit()
    gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    HAS_GPU = True
except Exception:
    HAS_GPU = False

try:
    import wmi
    w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
    HAS_WMI = True
except Exception:
    HAS_WMI = False

UPDATE_MS = 2000  # update interval

state = {
    'cpu_percent': 0.0,
    'ram_percent': 0.0,
    'cpu_temp': None,
    'gpu_percent': None,
    'gpu_temp': None,
    'net_up': 0.0,
    'net_down': 0.0,
    'running': True
}

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


def get_temps():
    cpu_t, gpu_t = None, None
    if HAS_WMI:
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
    return cpu_t, gpu_t


def make_gauge_icon(percent, up_kb_s, down_kb_s, size=(64, 64)):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    w_px, h_px = size
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("seguisym.ttf", 18)
        font_small = ImageFont.truetype("seguisym.ttf", 10)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # background circle
    cx, cy = w_px // 2, h_px // 2 - 6
    radius = min(w_px, h_px) // 2 - 4
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(24, 24, 24, 255))

    # arc for percent
    start = -90
    end = int(start + 360 * (percent / 100.0))
    draw.pieslice((cx - radius, cy - radius, cx + radius, cy + radius), start, end, fill=(38, 162, 255, 255))

    # inner circle to create ring
    inner_r = int(radius * 0.7)
    draw.ellipse((cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r), fill=(12, 12, 12, 255))

    # percentage text
    pct_text = f"{int(percent)}%"
    try:
        bbox = draw.textbbox((0, 0), pct_text, font=font_large)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = font_large.getsize(pct_text)
    draw.text((cx - tw / 2, cy - th / 2), pct_text, font=font_large, fill=(255, 255, 255, 255))

    # network speeds below the gauge
    up_text = f"↑ {up_kb_s}"
    down_text = f"↓ {down_kb_s}"
    try:
        up_bb = draw.textbbox((0, 0), up_text, font=font_small)
        up_w = up_bb[2] - up_bb[0]
    except Exception:
        up_w, _ = font_small.getsize(up_text)
    try:
        down_bb = draw.textbbox((0, 0), down_text, font=font_small)
        down_w = down_bb[2] - down_bb[0]
    except Exception:
        down_w, _ = font_small.getsize(down_text)
    gap = 6
    draw.text((cx - up_w - gap/2, h_px - 14), up_text, font=font_small, fill=(180, 255, 180, 255))
    draw.text((cx + gap/2, h_px - 14), down_text, font=font_small, fill=(180, 180, 255, 255))

    return img


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
        
    parts = []
    parts.append(("CPU ", "#888888"))
    cpu_val = f"{cpu:.0f}%"
    if cpu_temp:
        cpu_val += f" ({cpu_temp:.0f}°C)"
    parts.append((cpu_val, "#00e1ff"))
    
    parts.append(("  |  RAM ", "#888888"))
    parts.append((f"{ram:.0f}%", "#ffea00"))
    
    if HAS_GPU and gpu is not None:
        parts.append(("  |  GPU ", "#888888"))
        gpu_val = f"{gpu:.0f}%"
        if gpu_temp:
            gpu_val += f" ({gpu_temp:.0f}°C)"
        parts.append((gpu_val, "#ff007f"))
        
    parts.append(("  |  ↑ ", "#888888"))
    parts.append((f"{fmt_speed(up)}", "#ff7700"))
    parts.append(("  ↓ ", "#888888"))
    parts.append((f"{fmt_speed(down)}", "#00a2ff"))
    
    global right_edge_anchor, bar_y
    x = 5
    y = 12
    for text, color in parts:
        txt_id = canvas.create_text(x, y, text=text, fill=color, font=("Segoe UI", 9, "bold"), anchor="w", tags="text_group")
        bbox = canvas.bbox(txt_id)
        if bbox:
            x = bbox[2]
            
    # Calculate exact width needed (plus right padding)
    new_win_w = int(x) + 5
    
    # Update canvas config size
    canvas.config(width=new_win_w)
    
    # Adjust window size and position to keep right edge fixed
    if root:
        if bar_y is None:
            bar_y = root.winfo_y()
        if right_edge_anchor is None:
            right_edge_anchor = root.winfo_x() + root.winfo_width()
        new_x = right_edge_anchor - new_win_w
        root.geometry(f"{new_win_w}x24+{new_x}+{bar_y}")


def refresh_bar_ui():
    if not state['running'] or canvas is None:
        return
    draw_bar(canvas)
    root.after(1000, refresh_bar_ui)


def update_loop():
    global state, icon
    psutil.cpu_percent(interval=None)
    last_net = psutil.net_io_counters()
    last_time = time.time()
    
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
        
        def fmt_speed(kb_s):
            if kb_s >= 1024:
                return f"{kb_s/1024:.1f}M"
            return f"{kb_s:.0f}K"
            
        up_text = fmt_speed(up)
        down_text = fmt_speed(down)
        
        img = make_gauge_icon(cpu, up_text, down_text)
        if img and icon:
            icon.icon = img
            
        tooltip = f"CPU: {cpu:.0f}%"
        if cpu_temp:
            tooltip += f" ({cpu_temp:.0f}°C)"
        tooltip += f" | RAM: {ram:.0f}%\n"
        if HAS_GPU and gpu_percent is not None:
            tooltip += f"GPU: {gpu_percent:.0f}%"
            if gpu_temp:
                tooltip += f" ({gpu_temp:.0f}°C)"
            tooltip += "\n"
        tooltip += f"Up: {up_text}/s | Down: {down_text}/s"
        
        if icon:
            icon.title = tooltip[:127]
            
        # Debug print status to terminal
        gpu_str = ""
        if HAS_GPU and gpu_percent is not None:
            gpu_t_str = f" ({gpu_temp:.0f}°C)" if gpu_temp else ""
            gpu_str = f" | GPU: {gpu_percent:.0f}%{gpu_t_str}"
        cpu_t_str = f" ({cpu_temp:.0f}°C)" if cpu_temp else ""
        print(f"[{time.strftime('%H:%M:%S')}] Active | CPU: {cpu:.0f}%{cpu_t_str} | RAM: {ram:.0f}%{gpu_str} | Up: {up_text}/s | Down: {down_text}/s")
            
        time.sleep(UPDATE_MS / 1000.0)


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
        pystray.MenuItem('Start with Windows', toggle_autorun_from_tray, checked=lambda item: is_autorun_enabled()),
        pystray.MenuItem('Exit', on_exit)
    )
    
    # Start updater thread
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()
    
    # Initial icon
    img = make_gauge_icon(0, "0K", "0K")
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
    
    # Right click menu
    menu = tk.Menu(root, tearoff=0)
    
    autorun_var = tk.BooleanVar(value=is_autorun_enabled())
    menu.add_checkbutton(label="Start with Windows", variable=autorun_var, command=toggle_autorun)
    menu.add_separator()
    menu.add_command(label="Exit", command=on_exit_from_gui)
    
    def show_context_menu(event):
        # Update checkbox status before showing menu
        autorun_var.set(is_autorun_enabled())
        menu.post(event.x_root, event.y_root)
        
    canvas.bind("<Button-3>", show_context_menu)
    
    # Run tray icon in separate thread
    tray_thread = threading.Thread(target=run_tray, daemon=True)
    tray_thread.start()
    
    # Run GUI refresh loop
    refresh_bar_ui()
    
    root.mainloop()
