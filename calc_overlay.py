import tkinter as tk
import re
import threading
import ctypes
from ctypes import wintypes
import urllib.parse
import webbrowser
import io
import os
import tempfile
import base64
import subprocess
import json
from PIL import Image, ImageGrab

# Configuration file to remember screen position, size, and opacity
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_config.json")

# 1 PHP = 0.01589488 USDT
PHP_TO_USDT = 0.01589488

# Windows Hotkey constants
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_OEM_2 = 0xBF  # '?' and '/' key
VK_OEM_PLUS = 0xBB  # '+' / '=' key
VK_OEM_MINUS = 0xBD  # '-' / '_' key
VK_ADD = 0x6B  # Numpad '+'
VK_SUBTRACT = 0x6D  # Numpad '-'

HOTKEY_ID_FOCUS = 101
HOTKEY_ID_OP_PLUS1 = 102
HOTKEY_ID_OP_PLUS2 = 103
HOTKEY_ID_OP_MINUS1 = 104
HOTKEY_ID_OP_MINUS2 = 105

# Enable DPI Awareness so screen coordinates match physical pixels perfectly (fixes 125%/150% scaling offset bug)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def eval_math(expr):
    """Safely evaluates basic arithmetic expressions (+, -, *, /, %, parenthesis)."""
    clean_expr = re.sub(r"[^0-9\+\-\*\/\.\(\)\%\s]", "", expr)
    if not clean_expr:
        return None
    try:
        val = eval(clean_expr, {"__builtins__": None}, {})
        if isinstance(val, (int, float)):
            return float(val)
    except Exception:
        pass
    return None


def convert_single_token(token):
    """
    Converts a single value/math expression/currency string:
    - e.g. "10usdt" -> "10 USDT = 629.13 PHP"
    - e.g. "100" or "100php" -> "100 PHP = 1.5895 USDT"
    - e.g. "50*2" -> "100 PHP = 1.5895 USDT"
    """
    token = token.strip()
    if not token:
        return None

    # Check for explicit USDT/USD: "10 usdt", "2.5 usd"
    m_usdt = re.match(r"^([\d\.]+)\s*(?:usdt|usd)$", token, re.I)
    if m_usdt:
        try:
            val = float(m_usdt.group(1))
            php_val = val / PHP_TO_USDT
            return {
                "input": f"{val:g} USDT",
                "output": f"{php_val:,.2f} PHP",
                "display": f"{val:g} USDT = {php_val:,.2f} PHP",
                "out_val": f"{php_val:,.2f}",
                "php_num": php_val,
                "usdt_num": val
            }
        except Exception:
            pass

    # Check for math operators (+, -, *, /, %, (, ))
    has_operator = any(op in token for op in ["+", "-", "*", "/", "%", "(", ")"])
    if has_operator:
        val = eval_math(token)
        if val is not None:
            usdt_val = val * PHP_TO_USDT
            return {
                "input": f"{val:,.2f} PHP",
                "output": f"{usdt_val:,.4f} USDT",
                "display": f"{val:,.2f} PHP = {usdt_val:,.4f} USDT",
                "out_val": f"{usdt_val:,.4f}",
                "php_num": val,
                "usdt_num": usdt_val
            }
        return {"input": token, "output": "Math error", "display": f"{token}: Error", "out_val": "", "php_num": 0.0, "usdt_num": 0.0}

    # Check for direct number or number with "php"
    m_num = re.match(r"^([\d\.]+)\s*(?:php)?$", token, re.I)
    if m_num:
        try:
            php_val = float(m_num.group(1))
            usdt_val = php_val * PHP_TO_USDT
            return {
                "input": f"{php_val:,.2f} PHP",
                "output": f"{usdt_val:,.4f} USDT",
                "display": f"{php_val:,.2f} PHP = {usdt_val:,.4f} USDT",
                "out_val": f"{usdt_val:,.4f}",
                "php_num": php_val,
                "usdt_num": usdt_val
            }
        except Exception:
            pass

    return None


def process_query(text):
    text = text.strip()
    if not text:
        return []

    if "," in text or ";" in text:
        raw_parts = re.split(r"[,;]+", text)
        results = []
        for part in raw_parts:
            part = part.strip()
            if part:
                res = convert_single_token(part)
                if res:
                    results.append(res)
        return results

    res = convert_single_token(text)
    if res:
        return [res]

    return []


def extract_numbers_from_clipboard(text):
    if not text:
        return ""
    # Way 3: Matches any sequence of digits (including decimals) anywhere in the text
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return ""
    return ", ".join(numbers)


def launch_in_browser(target_url):
    """
    Opens Google Lens in a clean new tab in your default browser.
    """
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    edge_exe = next((p for p in edge_paths if os.path.exists(p)), None)

    # If Edge is installed, open directly in a new tab without window disruption
    if edge_exe:
        try:
            subprocess.Popen([edge_exe, target_url])
            return
        except Exception:
            pass

    # Standard default browser fallback
    webbrowser.open_new_tab(target_url)


class ScreenSnipper:
    """Full-screen sniper overlay for selecting any area on screen."""
    def __init__(self, on_snippet_taken, on_cancel=None):
        self.on_snippet_taken = on_snippet_taken
        self.on_cancel = on_cancel

        self.root = tk.Toplevel()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.30)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.close_snipper())

        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2, 40,
            text="🔍 Google Lens: Select any part of screen to search | ESC to cancel",
            fill="#ffffff",
            font=("Segoe UI", 12, "bold")
        )

    def on_press(self, event):
        self.start_screen_x = self.root.winfo_pointerx()
        self.start_screen_y = self.root.winfo_pointery()
        self.start_canvas_x = self.canvas.canvasx(event.x)
        self.start_canvas_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(
            self.start_canvas_x, self.start_canvas_y, self.start_canvas_x, self.start_canvas_y,
            outline="#89b4fa", width=2, fill="#313244", stipple="gray25"
        )

    def drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_canvas_x, self.start_canvas_y, cur_x, cur_y)

    def on_release(self, event):
        end_screen_x = self.root.winfo_pointerx()
        end_screen_y = self.root.winfo_pointery()

        x1 = int(min(self.start_screen_x, end_screen_x))
        y1 = int(min(self.start_screen_y, end_screen_y))
        x2 = int(max(self.start_screen_x, end_screen_x))
        y2 = int(max(self.start_screen_y, end_screen_y))

        self.root.withdraw()
        self.root.update()

        if (x2 - x1) > 5 and (y2 - y1) > 5:
            try:
                # Capture exact bounding box using physical screen coordinates
                captured_img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
                self.close_snipper()
                self.on_snippet_taken(captured_img)
                return
            except Exception as e:
                print("Grab error:", e)

        self.close_snipper()

    def close_snipper(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        if self.on_cancel:
            self.on_cancel()


class FloatingCalcOverlay:
    def __init__(self, root):
        self.root = root
        self.root.title("PHP ⇄ USDT & Google Lens")

        # Always on top & Frameless
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)

        # Compact widget dimensions: reduced default width by 35% (very small & compact)
        self._resize_job = None

        self.opacity = 1.0  # Range from 0.0 (100% transparent background) to 1.0 (pure solid black background)

        self.clipboard_watch_active = True
        self.last_clipboard_text = ""
        self._is_destroyed = False

        # Color key for true transparency in Windows
        self.transparent_key = "#010101"
        try:
            self.root.wm_attributes("-transparentcolor", self.transparent_key)
        except Exception:
            pass

        self.root.configure(bg="#000000")
        self.root.attributes("-alpha", 1.0)  # Keep window alpha 100% so text/buttons stay 100% crisp

        # Drag coordinates
        self._offsetx = 0
        self._offsety = 0

        # Load saved screen position and preferences if available
        saved_cfg = self._load_window_config()
        if saved_cfg and "opacity" in saved_cfg:
            self.opacity = saved_cfg["opacity"]

        self._build_ui()

        # Calculate snug base dimensions
        self.root.update_idletasks()
        init_w = int(self.root.winfo_reqwidth() * 0.65)
        init_h = self.root.winfo_reqheight()

        # Set default size as the STRICT MINIMUM LIMIT (cannot reduce smaller, but can increase)
        self.min_width = init_w
        self.min_height = init_h

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # Restore previous position or default near top-right
        if saved_cfg and "x" in saved_cfg and "y" in saved_cfg:
            start_x = max(0, min(screen_w - 50, saved_cfg["x"]))
            start_y = max(0, min(screen_h - 50, saved_cfg["y"]))
            self.fixed_width = max(self.min_width, saved_cfg.get("width", init_w))
            start_h = max(self.min_height, saved_cfg.get("height", init_h))
        else:
            self.fixed_width = init_w
            start_x = max(20, screen_w - self.fixed_width - 30)
            start_y = 80
            start_h = init_h

        self._start_w = self.fixed_width
        self._start_h = start_h
        self.root.geometry(f"{self.fixed_width}x{start_h}+{start_x}+{start_y}")

        # Apply saved opacity setting
        if self.opacity != 1.0:
            self.adjust_opacity(0.0)

        # Seed clipboard memory
        try:
            self.last_clipboard_text = self.root.clipboard_get()
        except Exception:
            self.last_clipboard_text = ""

        # Local window hotkeys
        self.root.bind("<Escape>", lambda e: self.on_close())
        self.root.bind("<Control-slash>", lambda e: self.focus_input())

        # Shortcuts for Opacity: Ctrl + and Ctrl - (supporting main keyboard, numpad, and Shift)
        self.root.bind("<Control-plus>", lambda e: self.adjust_opacity(0.1))
        self.root.bind("<Control-equal>", lambda e: self.adjust_opacity(0.1))
        self.root.bind("<Control-KP_Add>", lambda e: self.adjust_opacity(0.1))
        self.root.bind("<Control-minus>", lambda e: self.adjust_opacity(-0.1))
        self.root.bind("<Control-KP_Subtract>", lambda e: self.adjust_opacity(-0.1))

        # Global hotkey listener (Ctrl + /, Ctrl + Plus, Ctrl + Minus) in background daemon thread
        self._hotkey_thread = threading.Thread(target=self._listen_global_hotkey, daemon=True)
        self._hotkey_thread.start()

        # Start Tkinter-native clipboard watcher
        self.root.after(500, self._poll_clipboard)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # Header / Drag Bar
        self.header = tk.Frame(self.root, bg="#11111b", height=28)
        self.header.pack(fill="x", side="top")
        self.header.bind("<Button-1>", self.click_title)
        self.header.bind("<B1-Motion>", self.drag_title)

        title_lbl = tk.Label(
            self.header,
            text="MH",
            bg="#11111b",
            fg="#ff5555",
            font=("Segoe UI", 8, "bold")
        )
        title_lbl.pack(side="left", padx=4)
        title_lbl.bind("<Button-1>", self.click_title)
        title_lbl.bind("<B1-Motion>", self.drag_title)

        # Opacity + and - buttons
        btn_op_plus = tk.Label(
            self.header,
            text="+",
            bg="#1e1e2e",
            fg="#00ffff",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=4,
            pady=0
        )
        btn_op_plus.pack(side="left", padx=1)
        btn_op_plus.bind("<Button-1>", lambda e: self.adjust_opacity(0.1))

        btn_op_minus = tk.Label(
            self.header,
            text="-",
            bg="#1e1e2e",
            fg="#00ffff",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=5,
            pady=0
        )
        btn_op_minus.pack(side="left", padx=1)
        btn_op_minus.bind("<Button-1>", lambda e: self.adjust_opacity(-0.1))

        # Close button in upper right corner
        close_btn = tk.Label(
            self.header,
            text="✕ ",
            bg="#11111b",
            fg="#ff3333",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        close_btn.pack(side="right", padx=2)
        close_btn.bind("<Button-1>", lambda e: self.on_close())

        # Bottom Bar (Lens button + ON/OFF toggle + Toast + Resize Grip)
        self.bottom_bar = tk.Frame(self.root, bg="#11111b", height=22)
        self.bottom_bar.pack(fill="x", side="bottom")

        # Google Lens Button in Bottom Bar with high-contrast Border
        self.lens_frame = tk.Frame(
            self.bottom_bar,
            bg="#ff3333",  # High-contrast border color for Lens
            padx=1,
            pady=1
        )
        self.lens_frame.pack(side="left", padx=(3, 3), pady=1)

        self.btn_lens = tk.Label(
            self.lens_frame,
            text="🔍Lens",
            bg="#181825",
            fg="#ffff00",  # Bright yellow text
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
            padx=4,
            pady=0
        )
        self.btn_lens.pack()
        self.btn_lens.bind("<Button-1>", lambda e: self.start_lens_sniper())
        self.btn_lens.bind("<Enter>", lambda e: self.btn_lens.config(bg="#ff3333", fg="#ffffff"))
        self.btn_lens.bind("<Leave>", lambda e: self.btn_lens.config(bg="#181825", fg="#ffff00"))

        # Auto-clip toggle button in bottom bar
        self.btn_clip_toggle = tk.Label(
            self.bottom_bar,
            text="📋ON",
            bg="#181825",
            fg="#00ff66",
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
            padx=3,
            pady=1
        )
        self.btn_clip_toggle.pack(side="left", padx=(1, 3))
        self.btn_clip_toggle.bind("<Button-1>", lambda e: self.toggle_clip_watcher())

        # Notification / status label
        self.lbl_toast = tk.Label(
            self.bottom_bar,
            text="",
            font=("Segoe UI", 8),
            bg="#11111b",
            fg="#00ffff"
        )
        self.lbl_toast.pack(side="left", padx=2)

        # Prominent resize grip with hover feedback in bottom right
        self.grip = tk.Label(
            self.bottom_bar,
            text=" ⇲ ",
            font=("Segoe UI", 9, "bold"),
            bg="#11111b",
            fg="#ff5555",
            cursor="size_nw_se",
            padx=4
        )
        self.grip.pack(side="right")
        self.grip.bind("<Button-1>", self.start_resize)
        self.grip.bind("<B1-Motion>", self.do_resize)
        self.grip.bind("<Enter>", lambda e: self.grip.config(fg="#00ff66", bg="#313244"))
        self.grip.bind("<Leave>", lambda e: self.grip.config(fg="#ff5555", bg="#11111b"))

        # Calculator Container (tight compact padding)
        self.calc_panel = tk.Frame(self.root, bg="#181825", padx=4, pady=2)
        self.calc_panel.pack(fill="both", expand=True)

        # Input box
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            self.calc_panel,
            textvariable=self.entry_var,
            font=("Segoe UI", 10, "bold"),
            bg="#252538",
            fg="#ffffff",
            insertbackground="#ff3333",
            relief="flat",
            bd=2,
            justify="center"
        )
        self.entry.pack(fill="x", pady=(1, 3))
        self.entry.focus_set()
        self.entry.bind("<KeyRelease>", self.on_input_change)

        # Results display area (table view & summary)
        self.results_frame = tk.Frame(self.calc_panel, bg="#181825")
        self.results_frame.pack(fill="both", expand=True)

        # Header for the 2 columns (PHP➔USDT)
        self.table_header = tk.Frame(self.results_frame, bg="#181825")
        self.table_header.pack(fill="x", pady=(0, 2))

        self.th_php = tk.Label(
            self.table_header,
            text="PHP",
            font=("Segoe UI", 9, "bold"),
            bg="#181825",
            fg="#ff4444"  # Red for PHP
        )
        self.th_php.pack(side="left", padx=0)

        self.th_arrow = tk.Label(
            self.table_header,
            text="➔",
            font=("Segoe UI", 8, "bold"),
            bg="#181825",
            fg="#6c7086"
        )
        self.th_arrow.pack(side="left", padx=0)

        self.th_usdt = tk.Label(
            self.table_header,
            text="USDT",
            font=("Segoe UI", 9, "bold"),
            bg="#181825",
            fg="#00ff88"  # Neon Green for USDT
        )
        self.th_usdt.pack(side="left", padx=0)

        # Rows container (pure lightweight frame, zero lag, auto-expands & auto-contracts)
        self.table_rows_frame = tk.Frame(self.results_frame, bg="#181825")
        self.table_rows_frame.pack(fill="x", expand=True)

    def _blend_color(self, hex_fg, hex_bg, factor):
        """Blends a hex color toward background to simulate background opacity."""
        c1 = [int(hex_fg[i:i+2], 16) for i in (1, 3, 5)]
        c2 = [int(hex_bg[i:i+2], 16) for i in (1, 3, 5)]
        res = [int(c1[i] * factor + c2[i] * (1.0 - factor)) for i in range(3)]
        return "#{:02x}{:02x}{:02x}".format(*res)

    def adjust_opacity(self, delta):
        """Adjust background opacity: 0.0 (whole transparent) to 1.0 (whole solid black)."""
        self.opacity = round(max(0.0, min(1.0, self.opacity + delta)), 2)

        if self.opacity == 0.0:
            # 100% Whole Transparent background: everything matches transparent_key
            bg_main = self.transparent_key
            bg_bar = self.transparent_key
            bg_entry = "#11111b"  # Keep entry box subtly visible so user can see where to type
        elif self.opacity == 1.0:
            # 100% Whole Solid Black background
            bg_main = "#000000"
            bg_bar = "#050505"
            bg_entry = "#181825"
        else:
            # Smoothly transition from transparent_key up to rich solid black
            bg_main = self._blend_color("#000000", self.transparent_key, self.opacity)
            bg_bar = self._blend_color("#050505", self.transparent_key, self.opacity)
            bg_entry = self._blend_color("#181825", self.transparent_key, max(0.2, self.opacity))

        try:
            self.root.configure(bg=bg_main)
            self.header.configure(bg=bg_bar)
            self.bottom_bar.configure(bg=bg_bar)
            self.calc_panel.configure(bg=bg_main)
            self.results_frame.configure(bg=bg_main)
            self.table_header.configure(bg=bg_main)
            self.table_rows_frame.configure(bg=bg_main)
            self.entry.configure(bg=bg_entry)

            # Update child rows backgrounds
            for row in self.table_rows_frame.winfo_children():
                try:
                    row.configure(bg=bg_main)
                    for child in row.winfo_children():
                        try:
                            child.configure(bg=bg_main)
                        except Exception:
                            pass
                except Exception:
                    pass

            pct = int(self.opacity * 100)
            status_text = "Whole Transparent" if pct == 0 else ("Whole Black" if pct == 100 else f"BG Opacity: {pct}%")
            self.flash_toast(status_text)
        except Exception:
            pass

    # --- Google Lens Screen Sniper Workflow ---
    def start_lens_sniper(self):
        """Hides overlay and launches full-screen snippet capture tool."""
        self.root.withdraw()
        self.root.after(100, lambda: ScreenSnipper(
            on_snippet_taken=self.handle_screen_snippet,
            on_cancel=self.restore_window
        ))

    def restore_window(self):
        try:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        except Exception:
            pass

    def handle_screen_snippet(self, pil_image):
        """Called when user finishes selecting an area on screen."""
        self.restore_window()
        self.flash_toast("🔍 Opening Google Lens in browser...")
        threading.Thread(target=self._launch_lens_worker, args=(pil_image,), daemon=True).start()

    def _launch_lens_worker(self, pil_image):
        try:
            buf = io.BytesIO()
            rgb_img = pil_image.convert("RGB")
            rgb_img.save(buf, format="JPEG", quality=92)
            b64_data = base64.b64encode(buf.getvalue()).decode("ascii")

            html_bridge = (
                "<!DOCTYPE html>\n"
                "<html>\n"
                "<head>\n"
                "  <meta charset=\"utf-8\">\n"
                "  <title>Google Lens Search</title>\n"
                "  <style>\n"
                "    body {\n"
                "      background-color: #202124;\n"
                "      color: #e8eaed;\n"
                "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\n"
                "      display: flex;\n"
                "      flex-direction: column;\n"
                "      align-items: center;\n"
                "      justify-content: center;\n"
                "      height: 100vh;\n"
                "      margin: 0;\n"
                "    }\n"
                "    .spinner {\n"
                "      width: 44px;\n"
                "      height: 44px;\n"
                "      border: 4px solid #3c4043;\n"
                "      border-top: 4px solid #8ab4f8;\n"
                "      border-radius: 50%;\n"
                "      animation: spin 0.8s linear infinite;\n"
                "      margin-bottom: 16px;\n"
                "    }\n"
                "    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }\n"
                "  </style>\n"
                "</head>\n"
                "<body>\n"
                "  <div class=\"spinner\"></div>\n"
                "  <div style=\"font-size: 16px; font-weight: 500;\">Searching Google Lens...</div>\n"
                "  <form id=\"lensForm\" action=\"https://lens.google.com/v3/upload\" method=\"POST\" enctype=\"multipart/form-data\" style=\"display:none;\">\n"
                "    <input type=\"file\" name=\"encoded_image\" id=\"fileInput\">\n"
                "  </form>\n"
                "  <script>\n"
                "    (function() {\n"
                "      const b64 = \"" + b64_data + "\";\n"
                "      const bin = atob(b64);\n"
                "      const len = bin.length;\n"
                "      const bytes = new Uint8Array(len);\n"
                "      for (let i = 0; i < len; i++) {\n"
                "        bytes[i] = bin.charCodeAt(i);\n"
                "      }\n"
                "      const blob = new Blob([bytes], { type: 'image/jpeg' });\n"
                "      const file = new File([blob], 'lens_snippet.jpg', { type: 'image/jpeg' });\n"
                "      const dt = new DataTransfer();\n"
                "      dt.items.add(file);\n"
                "      document.getElementById('fileInput').files = dt.files;\n"
                "      document.getElementById('lensForm').submit();\n"
                "    })();\n"
                "  </script>\n"
                "</body>\n"
                "</html>"
            )

            temp_dir = tempfile.gettempdir()
            bridge_file = os.path.join(temp_dir, "google_lens_search.html")
            with open(bridge_file, "w", encoding="utf-8") as f:
                f.write(html_bridge)

            lens_url = "file:///" + bridge_file.replace("\\", "/")
            launch_in_browser(lens_url)
            self.root.after(0, lambda: self.flash_toast("✓ Google Lens opened in browser!"))
        except Exception as err:
            print("Lens launch error:", err)
            self.root.after(0, lambda: self.flash_toast("Error opening Lens"))

    def toggle_clip_watcher(self):
        """Toggle automatic clipboard watcher on/off."""
        self.clipboard_watch_active = not self.clipboard_watch_active
        if self.clipboard_watch_active:
            self.btn_clip_toggle.config(text="📋ON", fg="#a6e3a1")
            self.flash_toast("Clipboard watcher ON")
        else:
            self.btn_clip_toggle.config(text="📋OFF", fg="#6c7086")
            self.flash_toast("Clipboard watcher OFF")

    def flash_toast(self, msg):
        if self._is_destroyed:
            return
        self.lbl_toast.config(text=msg)
        self.root.after(3500, lambda: self.lbl_toast.config(text="") if not self._is_destroyed else None)

    def on_input_change(self, event=None):
        query = self.entry_var.get().strip()

        # Clear existing rows in table
        for widget in self.table_rows_frame.winfo_children():
            widget.destroy()

        cur_bg = self.table_rows_frame.cget("bg")

        if not query:
            # Placeholder row
            row = tk.Frame(self.table_rows_frame, bg=cur_bg)
            row.pack(fill="x", pady=2)
            lbl1 = tk.Label(row, text="Type amount...", font=("Segoe UI", 9, "italic"), bg=cur_bg, fg="#ff4444", anchor="w")
            lbl1.pack(side="left", padx=4)
            lbl2 = tk.Label(row, text="e.g. 100, 250", font=("Segoe UI", 9, "italic"), bg=cur_bg, fg="#00ff88", anchor="e")
            lbl2.pack(side="right", padx=4)
            self.schedule_auto_resize()
            return

        results = process_query(query)
        if not results:
            row = tk.Frame(self.table_rows_frame, bg=cur_bg)
            row.pack(fill="x", pady=2)
            lbl1 = tk.Label(row, text=query, font=("Segoe UI", 9, "bold"), bg=cur_bg, fg="#ff4444", anchor="w")
            lbl1.pack(side="left", padx=4)
            lbl2 = tk.Label(row, text="...", font=("Segoe UI", 9, "bold"), bg=cur_bg, fg="#ffff00", anchor="e")
            lbl2.pack(side="right", padx=4)
            self.schedule_auto_resize()
            return

        # Render each conversion result continuously: PHP➔USDT (no extra space, 2 decimals)
        for r in results:
            row = tk.Frame(self.table_rows_frame, bg=cur_bg)
            row.pack(fill="x", pady=2)

            # Left side (PHP numeric amount, 2 decimals)
            php_val_str = f"{r.get('php_num', 0.0):.2f}"
            lbl_php = tk.Label(
                row,
                text=php_val_str,
                font=("Segoe UI", 9, "bold"),
                bg=cur_bg,
                fg="#ff4444"  # High-contrast Red
            )
            lbl_php.pack(side="left", padx=0)

            # Middle arrow (flush, no space)
            lbl_sep = tk.Label(
                row,
                text="➔",
                font=("Segoe UI", 8),
                bg=cur_bg,
                fg="#6c7086"
            )
            lbl_sep.pack(side="left", padx=0)

            # Right side (USDT numeric amount, 2 decimals, flush)
            usdt_val_str = f"{r.get('usdt_num', 0.0):.2f}"
            lbl_usdt = tk.Label(
                row,
                text=usdt_val_str,
                font=("Segoe UI", 9, "bold"),
                bg=cur_bg,
                fg="#00ff88"  # High-contrast Neon Green
            )
            lbl_usdt.pack(side="left", padx=0)

        # Show total sum directly beneath the rows (moves lower as rows increase)
        if len(results) > 1:
            total_php = sum(r.get("php_num", 0.0) for r in results)
            total_usdt = sum(r.get("usdt_num", 0.0) for r in results)

            # Divider line above total
            div_line = tk.Frame(self.table_rows_frame, bg="#313244", height=1)
            div_line.pack(fill="x", pady=(4, 2), padx=0)

            total_row = tk.Frame(self.table_rows_frame, bg=cur_bg)
            total_row.pack(fill="x", pady=(1, 4))

            lbl_total_php = tk.Label(
                total_row,
                text=f"∑{total_php:.2f}",
                font=("Segoe UI", 9, "bold"),
                bg=cur_bg,
                fg="#ffff00"  # Bright Yellow
            )
            lbl_total_php.pack(side="left", padx=0)

            lbl_total_sep = tk.Label(
                total_row,
                text="➔",
                font=("Segoe UI", 8, "bold"),
                bg=cur_bg,
                fg="#ffff00"
            )
            lbl_total_sep.pack(side="left", padx=0)

            lbl_total_usdt = tk.Label(
                total_row,
                text=f"{total_usdt:.2f}",
                font=("Segoe UI", 9, "bold"),
                bg=cur_bg,
                fg="#ffff00"  # Bright Yellow
            )
            lbl_total_usdt.pack(side="left", padx=0)

        # Dynamically resize window to snugly fit input/rows/buttons
        self.schedule_auto_resize()

    def schedule_auto_resize(self):
        """Debounces resize to guarantee zero keystroke lag while expanding/contracting dynamically."""
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(30, self._do_auto_resize)

    def _do_auto_resize(self):
        self._resize_job = None
        if self._is_destroyed:
            return
        try:
            self.root.update_idletasks()
            # Do NOT increase width automatically; keep fixed width and only adjust height
            target_w = self.fixed_width
            needed_h = max(self.min_height, self.root.winfo_reqheight())

            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            cur_x = self.root.winfo_x()
            cur_y = self.root.winfo_y()

            # Only call geometry when size actually differs (avoids unnecessary redraw lag)
            if abs(cur_w - target_w) > 2 or abs(cur_h - needed_h) > 2:
                self.root.geometry(f"{target_w}x{needed_h}+{cur_x}+{cur_y}")
        except Exception:
            pass

    def focus_input(self, event=None):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.entry.focus_force()
            self.entry.selection_range(0, tk.END)
            self.entry.icursor(tk.END)
        except Exception:
            pass

    def _load_window_config(self):
        """Loads saved window position, width, and opacity from local disk."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_window_config(self):
        """Saves current window position, width, and opacity to local disk."""
        try:
            cfg = {
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
                "width": max(self.min_width, self.fixed_width),
                "height": max(self.min_height, self.root.winfo_height()),
                "opacity": self.opacity
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def on_close(self):
        self._is_destroyed = True
        self.clipboard_watch_active = False

        # Persist position to disk so it re-opens in the exact same location
        self._save_window_config()

        user32 = ctypes.windll.user32
        for hid in [HOTKEY_ID_FOCUS, HOTKEY_ID_OP_PLUS1, HOTKEY_ID_OP_PLUS2, HOTKEY_ID_OP_MINUS1, HOTKEY_ID_OP_MINUS2]:
            try:
                user32.UnregisterHotKey(None, hid)
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _poll_clipboard(self):
        if self._is_destroyed:
            return

        if self.clipboard_watch_active:
            try:
                clip_text = self.root.clipboard_get()
                if clip_text and clip_text != self.last_clipboard_text:
                    self.last_clipboard_text = clip_text
                    clean_text = clip_text.strip()
                    if clean_text:
                        extracted = extract_numbers_from_clipboard(clean_text)
                        if extracted:
                            self.entry_var.set(extracted)
                            self.on_input_change()
                            self.flash_toast("📋 Auto-converted from copy!")
            except Exception:
                pass

        if not self._is_destroyed:
            self.root.after(400, self._poll_clipboard)

    def _listen_global_hotkey(self):
        user32 = ctypes.windll.user32

        def safe_reg(hid, vk):
            if not user32.RegisterHotKey(None, hid, MOD_CONTROL | MOD_NOREPEAT, vk):
                user32.RegisterHotKey(None, hid, MOD_CONTROL, vk)

        safe_reg(HOTKEY_ID_FOCUS, VK_OEM_2)
        safe_reg(HOTKEY_ID_OP_PLUS1, VK_OEM_PLUS)
        safe_reg(HOTKEY_ID_OP_PLUS2, VK_ADD)
        safe_reg(HOTKEY_ID_OP_MINUS1, VK_OEM_MINUS)
        safe_reg(HOTKEY_ID_OP_MINUS2, VK_SUBTRACT)

        msg = wintypes.MSG()
        WM_HOTKEY = 0x0312

        while not self._is_destroyed and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                hid = msg.wParam
                if hid == HOTKEY_ID_FOCUS:
                    try:
                        self.root.after(0, self.focus_input)
                    except Exception:
                        break
                elif hid in (HOTKEY_ID_OP_PLUS1, HOTKEY_ID_OP_PLUS2):
                    try:
                        self.root.after(0, lambda: self.adjust_opacity(0.1))
                    except Exception:
                        break
                elif hid in (HOTKEY_ID_OP_MINUS1, HOTKEY_ID_OP_MINUS2):
                    try:
                        self.root.after(0, lambda: self.adjust_opacity(-0.1))
                    except Exception:
                        break

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hid in [HOTKEY_ID_FOCUS, HOTKEY_ID_OP_PLUS1, HOTKEY_ID_OP_PLUS2, HOTKEY_ID_OP_MINUS1, HOTKEY_ID_OP_MINUS2]:
            try:
                user32.UnregisterHotKey(None, hid)
            except Exception:
                pass

    def click_title(self, event):
        self._offsetx = event.x
        self._offsety = event.y

    def drag_title(self, event):
        x = self.root.winfo_pointerx() - self._offsetx
        y = self.root.winfo_pointery() - self._offsety
        self.root.geometry(f"+{x}+{y}")

    def start_resize(self, event):
        self._start_x = event.x_root
        self._start_y = event.y_root
        self._start_w = self.root.winfo_width()
        self._start_h = self.root.winfo_height()

    def do_resize(self, event):
        dx = event.x_root - self._start_x
        dy = event.y_root - self._start_y
        new_w = max(self.min_width, self._start_w + dx)
        new_h = max(self.min_height, self._start_h + dy)
        self.fixed_width = new_w  # Update the width preference to the user's dragged width
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        self.root.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")


if __name__ == "__main__":
    app_root = tk.Tk()
    app = FloatingCalcOverlay(app_root)
    app_root.mainloop()
