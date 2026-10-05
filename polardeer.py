"""Polar Deer - 가벼운 화면 녹화기 (워터마크 없음)

ffmpeg를 직접 호출해서 녹화한다. 외부 파이썬 패키지는 필요 없다.
  - 영역 / 창(프로세스) / 전체 화면 녹화
  - 화질(품질, FPS, 해상도 비율, 인코더) 설정
  - 전역 단축키
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# 좌표를 실제 픽셀 기준으로 맞추기 위해 Tk 생성 전에 DPI 인식 설정
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_NAME = "Polar Deer"
SETTINGS_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "PolarDeer" / "settings.json"
LOG_PATH = SETTINGS_PATH.with_name("ffmpeg.log")
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"

# 브랜드 색상 (로고 가이드)
NAVY = "#012C4E"
NAVY_HOVER = "#0A3F6B"
GOLD = "#EAD292"
CREAM = "#F6F2E9"
TILE = "#E8E3D6"
TILE_HOVER = "#DDD7C7"
INK = "#0B2540"
MUTED = "#6B7785"
REC_RED = "#C8352F"
REC_ON_NAVY = "#FF7B72"

# ---------------------------------------------------------------- Win32 ----
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HANDLE, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
SW_RESTORE = 9
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def virtual_screen():
    gm = user32.GetSystemMetrics
    return gm(76), gm(77), gm(78), gm(79)  # x, y, w, h


def list_monitors():
    """[(x, y, w, h), ...] 주 모니터가 먼저 오도록 정렬."""
    found = []

    def cb(_h, _dc, rect, _lp):
        r = rect.contents
        found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
    found.sort(key=lambda m: (m[0] != 0 or m[1] != 0, m[0], m[1]))
    return found


def process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return "?"
    finally:
        kernel32.CloseHandle(h)


def list_windows():
    """보이는 최상위 창 목록: [{hwnd, pid, proc, title}]"""
    result = []
    me = os.getpid()

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        result.append({"hwnd": int(hwnd), "pid": pid.value, "proc": process_name(pid.value), "title": buf.value})
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    result.sort(key=lambda w: (w["proc"].lower(), w["title"].lower()))
    return result


def window_screen_rect(hwnd):
    """창의 실제 보이는 영역(그림자 제외) (x, y, w, h)."""
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


# ------------------------------------------------------------- hotkeys -----
VK_NAMES = {0x20: "Space", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
            0x21: "PageUp", 0x22: "PageDown", 0x13: "Pause", 0x2C: "PrintScreen", 0x91: "ScrollLock"}
VK_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(12)})
VK_NAMES.update({c: chr(c) for c in range(0x30, 0x3A)})
VK_NAMES.update({c: chr(c) for c in range(0x41, 0x5B)})

# 단축키 id <-> 설정 키
HOTKEYS = {"hk_toggle": 1, "hk_region": 2, "hk_window": 3, "hk_screen": 4}
HOTKEY_LABELS = {
    "hk_toggle": "시작 / 정지 (현재 선택한 대상)",
    "hk_region": "영역 녹화",
    "hk_window": "창 녹화 (현재 활성 창)",
    "hk_screen": "전체 화면 녹화",
}


def hotkey_text(mods, vk):
    parts = []
    if mods & MOD_WIN:
        parts.append("Win")
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    parts.append(VK_NAMES.get(vk, f"0x{vk:02X}"))
    return " + ".join(parts)


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class HotkeyThread(threading.Thread):
    """RegisterHotKey는 등록한 스레드의 메시지 루프로 전달되므로 전용 스레드에서 처리한다."""

    def __init__(self, events):
        super().__init__(daemon=True)
        self.cmds = queue.Queue()
        self.events = events

    def bind(self, hid, mods, vk):
        self.cmds.put((hid, mods, vk))

    def run(self):
        msg = wt.MSG()
        while True:
            try:
                while True:
                    hid, mods, vk = self.cmds.get_nowait()
                    user32.UnregisterHotKey(None, hid)
                    ok = user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk)
                    self.events.put(("hk_ok" if ok else "hk_fail", hid))
            except queue.Empty:
                pass
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == WM_HOTKEY:
                    self.events.put(("hk", msg.wParam))
            time.sleep(0.02)


# -------------------------------------------------------------- ffmpeg -----
def find_ffmpeg():
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for p in (here / "ffmpeg.exe", Path(sys.executable).parent / "ffmpeg.exe"):
        if p.exists():
            return str(p)
    return shutil.which("ffmpeg")


QUALITY_NAMES = ["낮음 (작은 용량)", "보통", "높음", "최고 (큰 용량)"]
FPS_CHOICES = ["15", "24", "30", "60"]
SCALE_CHOICES = ["100%", "75%", "50%"]
ENCODER_LABELS = {
    "h264_nvenc": "GPU - NVIDIA (NVENC)",
    "h264_qsv": "GPU - Intel (QSV)",
    "h264_amf": "GPU - AMD (AMF)",
    "libx264": "CPU (x264)",
}


ENCODER_SHORT = {"h264_nvenc": "NVENC", "h264_qsv": "QSV", "h264_amf": "AMF", "libx264": "CPU (x264)"}


def encoder_args(enc, q):
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p4", "-rc", "vbr", "-cq", str([34, 28, 23, 18][q]), "-b:v", "0"]
    if enc == "h264_qsv":
        return ["-c:v", enc, "-global_quality", str([32, 27, 22, 18][q])]
    if enc == "h264_amf":
        qp = str([32, 27, 22, 18][q])
        return ["-c:v", enc, "-quality", "balanced", "-rc", "cqp", "-qp_i", qp, "-qp_p", qp]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str([30, 25, 21, 17][q])]


def probe_encoders(ffmpeg):
    """실제로 동작하는 인코더만 반환 (libx264는 항상 마지막)."""
    ok = []
    for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2",
               "-c:v", enc, "-f", "null", "-"]
        try:
            if subprocess.run(cmd, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0:
                ok.append(enc)
        except Exception:
            pass
    ok.append("libx264")
    return ok


# ------------------------------------------------------------ settings -----
DEFAULTS = {
    "mode": "screen",            # screen | region | window
    "monitor": 0,
    "region": None,              # [x, y, w, h]
    "window_screen_capture": False,
    "quality": 2,
    "fps": "30",
    "scale": "100%",
    "cursor": True,
    "encoder": "auto",
    "outdir": str(Path.home() / "Videos" / "PolarDeer"),
    "hk_toggle": [0, 0x78],                      # F9
    "hk_region": [MOD_WIN | MOD_SHIFT, 0x52],    # Win+Shift+R
    "hk_window": [MOD_WIN | MOD_SHIFT, 0x45],    # Win+Shift+E  (Win+Shift+W는 다른 프로그램이 자주 사용)
    "hk_screen": [MOD_WIN | MOD_SHIFT, 0x46],    # Win+Shift+F
    "minimize": True,
}


def load_settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ------------------------------------------------------------ widgets ------
def rrect(c, x1, y1, x2, y2, r, **kw):
    """둥근 사각형 (smooth polygon)."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class Tile(tk.Canvas):
    """로고 가이드의 툴바 버튼: 둥근 타일 + 아이콘 + 라벨."""

    def __init__(self, parent, k, icon, label, command):
        self.k = k
        self.w, self.h = round(92 * k), round(88 * k)
        super().__init__(parent, width=self.w, height=self.h, bg=CREAM, highlightthickness=0, cursor="hand2")
        self.icon, self.label, self.command = icon, label, command
        self.selected = False
        self.hover = False
        self.enabled = True
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.redraw()

    def _set_hover(self, v):
        self.hover = v
        self.redraw()

    def _click(self, e):
        if self.enabled and 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.command()

    def set_selected(self, v):
        self.selected = v
        self.redraw()

    def set_enabled(self, v):
        self.enabled = v
        self.configure(cursor="hand2" if v else "arrow")
        self.redraw()

    def redraw(self):
        self.delete("all")
        k = self.k
        tile_h = round(58 * k)
        bg = NAVY if self.selected else (TILE_HOVER if self.hover and self.enabled else TILE)
        fg = GOLD if self.selected else NAVY
        if not self.enabled and not self.selected:
            fg = "#9AA3AD"
        pad = round(8 * k)
        rrect(self, pad, 2, self.w - pad, tile_h, round(12 * k), fill=bg, outline="")
        self._draw_icon(self.w / 2, tile_h / 2 + 1, fg, bg)
        self.create_text(self.w / 2, tile_h + round(15 * k), text=self.label, fill=INK if self.enabled else MUTED,
                         font=("Malgun Gothic", 9, "bold" if self.selected else "normal"))

    def _draw_icon(self, cx, cy, fg, bg):
        k = self.k
        u = lambda v: v * k  # noqa: E731  (아이콘은 40x40 기준 좌표로 그림)
        x0, y0 = cx - u(20), cy - u(20)
        P = lambda x, y: (x0 + u(x), y0 + u(y))  # noqa: E731
        lw = max(2, round(2.6 * k))
        if self.icon == "region":
            rrect(self, *P(7, 8), *P(33, 32), u(3), fill="", outline=fg, width=lw, dash=(max(3, round(4 * k)), max(2, round(3 * k))))
        elif self.icon == "window":
            rrect(self, *P(6, 8), *P(34, 32), u(3), fill="", outline=fg, width=lw)
            self.create_line(*P(6, 15), *P(34, 15), fill=fg, width=lw)
            self.create_oval(*P(10, 10.5), *P(12.4, 12.9), fill=fg, outline=fg)
        elif self.icon == "screen":
            rrect(self, *P(6, 8), *P(34, 27), u(3), fill="", outline=fg, width=lw)
            self.create_line(*P(20, 27), *P(20, 33), fill=fg, width=lw)
            self.create_line(*P(13, 33), *P(27, 33), fill=fg, width=lw, capstyle="round")
        elif self.icon == "gear":
            import math
            for i in range(8):
                a = math.radians(i * 45)
                self.create_line(*P(20 + 8 * math.cos(a), 20 + 8 * math.sin(a)),
                                 *P(20 + 13 * math.cos(a), 20 + 13 * math.sin(a)), fill=fg, width=round(5 * k))
            self.create_oval(*P(9, 9), *P(31, 31), fill=fg, outline=fg)
            self.create_oval(*P(15.5, 15.5), *P(24.5, 24.5), fill=bg, outline=bg)


class RoundButton(tk.Canvas):
    """큰 둥근 버튼 (녹화 시작/정지)."""

    def __init__(self, parent, k, command):
        self.k = k
        self.h = round(50 * k)
        super().__init__(parent, height=self.h, bg=CREAM, highlightthickness=0, cursor="hand2")
        self.command = command
        self.text = ""
        self.fill, self.fg, self.hover_fill = NAVY, GOLD, NAVY_HOVER
        self.hover = False
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self.command() if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.h else None)

    def _hover(self, v):
        self.hover = v
        self.redraw()

    def configure_style(self, text, fill, hover_fill, fg):
        self.text, self.fill, self.hover_fill, self.fg = text, fill, hover_fill, fg
        self.redraw()

    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 10:
            return
        rrect(self, 1, 1, w - 1, self.h - 1, round(14 * self.k), fill=self.hover_fill if self.hover else self.fill, outline="")
        self.create_text(w / 2, self.h / 2, text=self.text, fill=self.fg, font=("Malgun Gothic", 12, "bold"))


# --------------------------------------------------------- region picker ---
def pick_region(root, on_done):
    """가상 화면 전체를 덮는 반투명 오버레이에서 드래그로 영역 선택. Esc/우클릭 취소."""
    vx, vy, vw, vh = virtual_screen()
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.35)
    top.geometry(f"{vw}x{vh}{vx:+d}{vy:+d}")
    canvas = tk.Canvas(top, bg=NAVY, highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(vw // 2, 48, fill=GOLD, font=("Malgun Gothic", 16, "bold"),
                       text="드래그해서 녹화할 영역을 선택하세요   (Esc / 우클릭: 취소)")
    state = {"x0": 0, "y0": 0, "rect": None, "label": None}

    def press(e):
        state["x0"], state["y0"] = e.x, e.y
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline=GOLD, width=2)
        state["label"] = canvas.create_text(e.x + 6, e.y - 12, anchor="w", fill=GOLD, font=("Malgun Gothic", 11, "bold"))

    def drag(e):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)
            canvas.coords(state["label"], min(state["x0"], e.x) + 6, min(state["y0"], e.y) - 12)
            canvas.itemconfigure(state["label"], text=f"{abs(e.x - state['x0'])} x {abs(e.y - state['y0'])}")

    def release(e):
        x, y = min(state["x0"], e.x), min(state["y0"], e.y)
        w, h = abs(e.x - state["x0"]), abs(e.y - state["y0"])
        top.destroy()
        if w >= 64 and h >= 64:
            on_done([x + vx, y + vy, w, h])

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    top.bind("<Escape>", lambda _e: top.destroy())
    top.bind("<ButtonPress-3>", lambda _e: top.destroy())
    top.focus_force()


# ------------------------------------------------------------------ app ----
class App:
    def __init__(self):
        self.s = load_settings()
        self.ffmpeg = find_ffmpeg()
        self.events = queue.Queue()
        self.proc = None
        self.pending_cmds = []
        self.recording = False
        self.starting = False
        self.out_file = None
        self.last_file = None
        self.t0 = 0.0
        self.windows = []
        self.capturing_key = None   # 단축키 입력 대기 중인 설정 키
        self.hk_failed = set()
        self.hk_buttons = {}
        self.settings_win = None
        self.cb_encoder = None
        self.encoders = ["libx264"]
        self.monitors = list_monitors()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=CREAM)
        self.root.resizable(False, False)
        self.k = max(1.0, self.root.winfo_fpixels("1i") / 96)
        try:
            self.root.iconbitmap(default=str(ASSETS / "polardeer.ico"))
        except tk.TclError:
            pass
        self.setup_style()

        self.mode = tk.StringVar(value=self.s["mode"])
        self.var_quality = tk.StringVar(value=QUALITY_NAMES[self.s["quality"]])
        self.var_fps = tk.StringVar(value=self.s["fps"])
        self.var_scale = tk.StringVar(value=self.s["scale"])
        self.var_encoder = tk.StringVar()
        self.var_cursor = tk.BooleanVar(value=self.s["cursor"])
        self.var_min = tk.BooleanVar(value=self.s["minimize"])
        self.var_outdir = tk.StringVar(value=self.s["outdir"])
        self.var_winscreen = tk.BooleanVar(value=self.s["window_screen_capture"])
        self.update_encoder_var()
        for v in (self.var_quality, self.var_fps, self.var_scale, self.var_encoder):
            v.trace_add("write", lambda *_: self.update_summary())

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg.exe 를 찾을 수 없습니다.\nPATH에 ffmpeg를 추가하거나 이 프로그램 옆에 ffmpeg.exe 를 두세요.")
        else:
            threading.Thread(target=self.probe, daemon=True).start()

        self.hotkeys = HotkeyThread(self.events)
        self.hotkeys.start()
        for key, hid in HOTKEYS.items():
            self.hotkeys.bind(hid, *self.s[key])
        self.refresh_windows()
        self.set_mode(self.s["mode"])
        self.update_summary()
        self.root.after(50, self.poll)

    # ----- 스타일 -----
    def setup_style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        base = ("Malgun Gothic", 9)
        st.configure(".", font=base, background=CREAM, foreground=INK)
        st.configure("TFrame", background=CREAM)
        st.configure("TLabel", background=CREAM, foreground=INK)
        st.configure("Muted.TLabel", foreground=MUTED)
        st.configure("Section.TLabel", foreground=MUTED, font=("Malgun Gothic", 8, "bold"))
        st.configure("TCheckbutton", background=CREAM, foreground=INK)
        st.map("TCheckbutton", background=[("active", CREAM)])
        st.configure("TCombobox", fieldbackground="white", background=TILE, arrowcolor=NAVY, bordercolor="#CFC8B6",
                     lightcolor="white", darkcolor="white", padding=3)
        st.map("TCombobox", fieldbackground=[("readonly", "white"), ("disabled", TILE)],
               foreground=[("readonly", INK)], selectbackground=[("readonly", "white")], selectforeground=[("readonly", INK)])
        self.root.option_add("*TCombobox*Listbox.background", "white")
        self.root.option_add("*TCombobox*Listbox.foreground", INK)
        self.root.option_add("*TCombobox*Listbox.selectBackground", NAVY)
        self.root.option_add("*TCombobox*Listbox.selectForeground", GOLD)
        self.root.option_add("*TCombobox*Listbox.font", ("Malgun Gothic", 9))
        st.configure("TEntry", fieldbackground="white", bordercolor="#CFC8B6", padding=4)
        st.configure("TButton", background=TILE, foreground=NAVY, bordercolor="#CFC8B6", focuscolor=TILE,
                     lightcolor=TILE, darkcolor=TILE, padding=(10, 4))
        st.map("TButton", background=[("active", TILE_HOVER), ("disabled", CREAM)], foreground=[("disabled", "#9AA3AD")])
        st.configure("Navy.TButton", background=NAVY, foreground=GOLD, bordercolor=NAVY, focuscolor=NAVY,
                     lightcolor=NAVY, darkcolor=NAVY, padding=(12, 5), font=("Malgun Gothic", 9, "bold"))
        st.map("Navy.TButton", background=[("active", NAVY_HOVER)])

    # ----- 메인 UI -----
    def build_ui(self):
        k, r = self.k, self.root
        pad = round(18 * k)

        # 헤더
        hdr = tk.Frame(r, bg=NAVY)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)
        sizes = [28, 36, 44, 56]
        want = 30 * k
        size = next((s for s in sizes if s >= want), sizes[-1])
        try:
            self.logo_img = tk.PhotoImage(file=str(ASSETS / f"mark_{size}.png"))
            tk.Label(hdr, image=self.logo_img, bg=NAVY).grid(row=0, column=0, padx=(pad, 8), pady=round(10 * k))
        except tk.TclError:
            pass
        tk.Label(hdr, text="Polar Deer", bg=NAVY, fg=GOLD, font=("Georgia", 17)).grid(row=0, column=1, sticky="w")
        self.lbl_rec = tk.Label(hdr, text="", bg=NAVY, fg=REC_ON_NAVY, font=("Malgun Gothic", 10, "bold"))
        self.lbl_rec.grid(row=0, column=2, padx=pad)

        body = tk.Frame(r, bg=CREAM)
        body.grid(row=1, column=0, sticky="ew", padx=pad, pady=(round(16 * k), round(14 * k)))

        # 툴바: 영역 / 창 / 전체 화면 | 설정
        bar = tk.Frame(body, bg=CREAM)
        bar.grid(row=0, column=0, sticky="ew")
        self.tiles = {}
        for i, (key, icon, label) in enumerate((("region", "region", "영역"), ("window", "window", "창"), ("screen", "screen", "전체 화면"))):
            t = Tile(bar, k, icon, label, lambda m=key: self.set_mode(m))
            t.grid(row=0, column=i, padx=2)
            self.tiles[key] = t
        tk.Frame(bar, bg="#D5CFBE", width=1).grid(row=0, column=3, sticky="ns", padx=round(8 * k), pady=round(6 * k))
        self.btn_settings = Tile(bar, k, "gear", "설정", self.open_settings)
        self.btn_settings.grid(row=0, column=4, padx=2)

        # 대상 상세
        self.detail = tk.Frame(body, bg=CREAM)
        self.detail.grid(row=1, column=0, sticky="ew", pady=(round(12 * k), 0))
        self.detail.columnconfigure(0, weight=1)

        self.f_region = ttk.Frame(self.detail)
        self.f_region.columnconfigure(0, weight=1)
        self.lbl_region = ttk.Label(self.f_region, text=self.region_text())
        self.lbl_region.grid(row=0, column=0, sticky="w")
        self.btn_region = ttk.Button(self.f_region, text="영역 다시 선택", command=lambda: self.select_region())
        self.btn_region.grid(row=0, column=1)

        self.f_window = ttk.Frame(self.detail)
        self.f_window.columnconfigure(0, weight=1)
        self.cb_window = ttk.Combobox(self.f_window, state="readonly", width=40, postcommand=self.refresh_windows)
        self.cb_window.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.f_window, text="새로고침", command=self.refresh_windows).grid(row=0, column=1, padx=(6, 0))
        ttk.Checkbutton(self.f_window, text="창 영역을 화면에서 캡처 (겹친 창도 함께 찍힘)", variable=self.var_winscreen).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.f_screen = ttk.Frame(self.detail)
        self.f_screen.columnconfigure(0, weight=1)
        mon_labels = [f"모니터 {i + 1}   {m[2]} x {m[3]}" + ("   (주 모니터)" if m[0] == 0 and m[1] == 0 else "") for i, m in enumerate(self.monitors)]
        self.cb_monitor = ttk.Combobox(self.f_screen, state="readonly", values=mon_labels)
        self.cb_monitor.current(min(self.s["monitor"], len(mon_labels) - 1))
        self.cb_monitor.grid(row=0, column=0, sticky="ew")

        self.lbl_summary = ttk.Label(body, style="Muted.TLabel")
        self.lbl_summary.grid(row=2, column=0, sticky="w", pady=(round(12 * k), round(10 * k)))

        self.btn_rec = RoundButton(body, k, self.toggle)
        self.btn_rec.grid(row=3, column=0, sticky="ew")
        self.lbl_status = ttk.Label(body, text="대기 중", style="Muted.TLabel", anchor="center")
        self.lbl_status.grid(row=4, column=0, sticky="ew", pady=(round(8 * k), 0))
        self.lbl_status.bind("<Button-1>", lambda _e: self.reveal_last())
        body.columnconfigure(0, weight=1)
        self.refresh_rec_button()

    def region_text(self):
        r = self.s["region"]
        return f"{r[2]} x {r[3]}   ({r[0]}, {r[1]})" if r else "선택된 영역 없음"

    def set_mode(self, m):
        if self.recording or self.starting:
            return
        self.mode.set(m)
        for key, t in self.tiles.items():
            t.set_selected(key == m)
        for key, f in (("region", self.f_region), ("window", self.f_window), ("screen", self.f_screen)):
            if key == m:
                f.grid(row=0, column=0, sticky="ew")
            else:
                f.grid_remove()

    def update_summary(self):
        q = self.var_quality.get().split(" ")[0]
        key = self.encoder_key()
        enc = ENCODER_SHORT[self.encoders[0] if key == "auto" else key]
        self.lbl_summary.configure(text=f"품질 {q}  ·  {self.var_fps.get()} fps  ·  크기 {self.var_scale.get()}  ·  {enc}")

    def refresh_rec_button(self):
        if self.recording:
            el = int(time.time() - self.t0)
            self.btn_rec.configure_style(f"■   녹화 정지    {el // 60:02d}:{el % 60:02d}", REC_RED, "#A82B26", "white")
        else:
            self.btn_rec.configure_style(f"●   녹화 시작    {hotkey_text(*self.s['hk_toggle'])}", NAVY, NAVY_HOVER, GOLD)

    def set_status(self, text, link=False):
        self.lbl_status.configure(text=text, cursor="hand2" if link else "")

    def reveal_last(self):
        if self.last_file and os.path.exists(self.last_file) and not self.recording:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.last_file)])

    # ----- 설정 창 -----
    def open_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        k = self.k
        w = tk.Toplevel(self.root)
        self.settings_win = w
        w.title("설정 - Polar Deer")
        w.configure(bg=CREAM)
        w.resizable(False, False)
        w.transient(self.root)
        try:
            w.iconbitmap(str(ASSETS / "polardeer.ico"))
        except tk.TclError:
            pass
        pad = round(18 * k)
        f = ttk.Frame(w)
        f.grid(row=0, column=0, padx=pad, pady=pad)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)
        row = 0

        def section(text):
            nonlocal row
            ttk.Label(f, text="  ".join(text), style="Section.TLabel").grid(row=row, column=0, columnspan=4, sticky="w", pady=(0 if row == 0 else 14, 4))
            row += 1

        section("화질")
        ttk.Label(f, text="품질").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(f, state="readonly", values=QUALITY_NAMES, textvariable=self.var_quality, width=16).grid(row=row, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(f, text="FPS").grid(row=row, column=2, sticky="w")
        ttk.Combobox(f, state="readonly", values=FPS_CHOICES, textvariable=self.var_fps, width=8).grid(row=row, column=3, sticky="ew", padx=(8, 0))
        row += 1
        ttk.Label(f, text="크기").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(f, state="readonly", values=SCALE_CHOICES, textvariable=self.var_scale, width=16).grid(row=row, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(f, text="인코더").grid(row=row, column=2, sticky="w")
        self.cb_encoder = ttk.Combobox(f, state="readonly", values=self.encoder_labels(), textvariable=self.var_encoder, width=22)
        self.cb_encoder.grid(row=row, column=3, sticky="ew", padx=(8, 0))
        row += 1
        ttk.Checkbutton(f, text="마우스 커서 포함", variable=self.var_cursor).grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(f, text="녹화 중 창 최소화", variable=self.var_min).grid(row=row, column=2, columnspan=2, sticky="w", pady=(6, 0))
        row += 1

        section("저장 폴더")
        d = ttk.Frame(f)
        d.grid(row=row, column=0, columnspan=4, sticky="ew")
        d.columnconfigure(0, weight=1)
        ttk.Entry(d, textvariable=self.var_outdir, width=42).grid(row=0, column=0, sticky="ew")
        ttk.Button(d, text="찾아보기", command=self.browse).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(d, text="열기", command=self.open_folder).grid(row=0, column=2, padx=(6, 0))
        row += 1

        section("단축키")
        for key in HOTKEYS:
            ttk.Label(f, text=HOTKEY_LABELS[key]).grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
            b = ttk.Button(f, width=22, command=lambda kk=key: self.capture_key(kk))
            b.grid(row=row, column=2, columnspan=2, sticky="ew", padx=(8, 0))
            self.hk_buttons[key] = b
            row += 1
        ttk.Label(f, text="버튼을 누른 뒤 원하는 키 조합을 입력하세요 (Esc: 취소)", style="Muted.TLabel").grid(row=row, column=0, columnspan=4, sticky="w", pady=(2, 0))
        row += 1
        ttk.Button(f, text="닫기", style="Navy.TButton", command=w.destroy).grid(row=row, column=0, columnspan=4, sticky="e", pady=(16, 0))
        self.refresh_hk_labels()
        w.bind("<Destroy>", lambda e: self.on_settings_closed() if e.widget is w else None)
        w.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w.winfo_width()) // 2
        y = self.root.winfo_rooty() + round(30 * k)
        w.geometry(f"+{max(0, x)}+{max(0, y)}")

    def on_settings_closed(self):
        self.settings_win = None
        self.cb_encoder = None
        self.hk_buttons = {}
        if self.capturing_key:
            self.capturing_key = None
            self.root.unbind("<KeyPress>")

    def encoder_labels(self):
        return ["자동"] + [ENCODER_LABELS[e] for e in self.encoders]

    def update_encoder_var(self):
        keys = ["auto"] + self.encoders
        cur = self.s["encoder"] if self.s["encoder"] in keys else "auto"
        self.var_encoder.set(self.encoder_labels()[keys.index(cur)])

    def encoder_key(self):
        labels = self.encoder_labels()
        i = labels.index(self.var_encoder.get()) if self.var_encoder.get() in labels else 0
        return (["auto"] + self.encoders)[i]

    def browse(self):
        d = filedialog.askdirectory(initialdir=self.var_outdir.get() or None, parent=self.settings_win or self.root)
        if d:
            self.var_outdir.set(d)

    def open_folder(self):
        d = self.var_outdir.get()
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    # ----- 단축키 설정 -----
    def refresh_hk_labels(self):
        for key, b in self.hk_buttons.items():
            txt = hotkey_text(*self.s[key])
            b.configure(text=txt + ("   (사용 불가)" if key in self.hk_failed else ""))
        self.refresh_rec_button()

    def capture_key(self, which):
        if self.capturing_key or not self.settings_win:
            return
        self.capturing_key = which
        self.hk_buttons[which].configure(text="키를 누르세요…")
        self.settings_win.bind("<KeyPress>", self.on_key_capture)
        self.settings_win.focus_force()

    def on_key_capture(self, e):
        if e.keycode in (16, 17, 18, 91, 92):  # 수식키 단독 입력은 무시
            return "break"
        which, self.capturing_key = self.capturing_key, None
        self.settings_win.unbind("<KeyPress>")
        if e.keysym == "Escape":
            self.refresh_hk_labels()
            return "break"
        if e.keycode not in VK_NAMES:
            self.refresh_hk_labels()
            self.set_status("지원하지 않는 키입니다")
            return "break"
        mods = ((MOD_SHIFT if key_down(0x10) else 0) | (MOD_CONTROL if key_down(0x11) else 0)
                | (MOD_ALT if key_down(0x12) else 0) | (MOD_WIN if key_down(0x5B) or key_down(0x5C) else 0))
        self.s[which] = [mods, e.keycode]
        self.hk_failed.discard(which)
        self.hotkeys.bind(HOTKEYS[which], mods, e.keycode)
        self.refresh_hk_labels()
        return "break"

    # ----- 이벤트 처리 -----
    def poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "hk":
                    self.on_hotkey(ev[1])
                elif kind == "hk_fail":
                    key = next(k for k, v in HOTKEYS.items() if v == ev[1])
                    self.hk_failed.add(key)
                    self.refresh_hk_labels()
                    self.set_status(f"단축키 '{HOTKEY_LABELS[key].split(' (')[0]}' 등록 실패: 다른 프로그램이 사용 중입니다 (설정에서 변경)")
                elif kind == "hk_ok":
                    key = next(k for k, v in HOTKEYS.items() if v == ev[1])
                    self.hk_failed.discard(key)
                elif kind == "encoders":
                    self.encoders = ev[1]
                    self.update_encoder_var()
                    if self.cb_encoder:
                        self.cb_encoder.configure(values=self.encoder_labels())
                    self.update_summary()
                elif kind == "stopped":
                    self.finish(error=False)
        except queue.Empty:
            pass
        if self.recording:
            self.tick()
        self.root.after(50, self.poll)

    def on_hotkey(self, hid):
        if self.starting:
            return
        if hid == HOTKEYS["hk_toggle"] or self.recording:   # 녹화 중에는 어떤 단축키든 정지
            self.toggle()
        elif hid == HOTKEYS["hk_region"]:
            self.select_region(then_start=True)
        elif hid == HOTKEYS["hk_window"]:
            self.record_foreground_window()
        elif hid == HOTKEYS["hk_screen"]:
            self.set_mode("screen")
            self.start()

    def probe(self):
        self.events.put(("encoders", probe_encoders(self.ffmpeg)))

    def tick(self):
        el = int(time.time() - self.t0)
        try:
            size = os.path.getsize(self.out_file)
        except OSError:
            size = 0
        self.lbl_rec.configure(text=f"●  REC  {el // 3600:02d}:{el // 60 % 60:02d}:{el % 60:02d}")
        self.set_status(f"녹화 중   {size / 1048576:.1f} MB")
        self.refresh_rec_button()
        if self.proc and self.proc.poll() is not None:  # ffmpeg가 비정상 종료
            self.finish(error=True)

    # ----- 대상 선택 -----
    def refresh_windows(self):
        self.windows = list_windows()
        labels = [f"{w['proc']}  —  {w['title'][:60]}" for w in self.windows]
        cur = self.cb_window.get()
        self.cb_window.configure(values=labels)
        if cur in labels:
            self.cb_window.set(cur)
        elif labels and not cur:
            self.cb_window.current(0)

    def select_region(self, then_start=False):
        if self.recording or self.starting:
            return

        def done(rect):
            self.s["region"] = rect
            self.lbl_region.configure(text=self.region_text())
            self.set_mode("region")
            self.set_status("영역이 지정되었습니다")
            if then_start:
                self.start()

        pick_region(self.root, done)

    def record_foreground_window(self):
        hwnd = user32.GetForegroundWindow()
        self.refresh_windows()
        idx = next((i for i, w in enumerate(self.windows) if w["hwnd"] == hwnd), None)
        if idx is None:
            self.set_status("현재 활성 창은 녹화할 수 없습니다")
            winsound.MessageBeep()
            return
        self.cb_window.current(idx)
        self.set_mode("window")
        self.start()

    # ----- 녹화 -----
    def toggle(self):
        if self.starting:
            return
        if self.recording:
            self.stop()
        else:
            self.start()

    def build_commands(self, outfile):
        """시도할 ffmpeg 명령 목록 [우선순위 높은 순]. 앞의 것이 바로 실패하면 다음 것을 쓴다."""
        mode = self.mode.get()
        fps = self.var_fps.get()
        cursor = self.var_cursor.get()
        base = [self.ffmpeg, "-hide_banner", "-y"]

        def gdi(*inp, rect=None):
            c = base + ["-f", "gdigrab", "-framerate", fps, "-draw_mouse", "1" if cursor else "0"]
            if rect:
                x, y, w, h = rect
                c += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}"]
            return c + ["-i", *inp]

        # (입력부 명령, 소스 필터) 후보들
        candidates = []
        if mode == "window":
            i = self.cb_window.current()
            if i < 0 or i >= len(self.windows):
                raise ValueError("녹화할 프로세스(창)를 선택하세요.")
            hwnd = self.windows[i]["hwnd"]
            if not user32.IsWindow(hwnd):
                raise ValueError("선택한 창이 닫혔습니다. 새로고침 후 다시 선택하세요.")
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
                time.sleep(0.5)
            if self.var_winscreen.get():
                candidates.append((gdi("desktop", rect=window_screen_rect(hwnd)), None))
            else:
                # Windows Graphics Capture: GPU 렌더링 앱도 캡처되고, 다른 창이 가려도 영향 없음
                # (구버전 Windows 10은 max_framerate가 무시되어 프레임이 쏟아지므로 fps 필터로 제한)
                src = f"gfxcapture=hwnd={hwnd}:max_framerate={fps}:capture_cursor={'true' if cursor else 'false'},fps={fps}"
                candidates.append((base, src + ",hwdownload,format=bgra"))
                candidates.append((gdi(f"hwnd={hwnd}"), None))
        else:
            if mode == "region":
                if not self.s["region"]:
                    raise ValueError("먼저 '영역 다시 선택'으로 녹화할 영역을 지정하세요.")
                x, y, w, h = self.s["region"]
                mon = self.monitors[0]
            else:
                x, y, w, h = mon = self.monitors[max(0, self.cb_monitor.current())]
            on_primary = mon == self.monitors[0] and x >= mon[0] and y >= mon[1] \
                and x + w <= mon[0] + mon[2] and y + h <= mon[1] + mon[3]
            if on_primary:
                # Desktop Duplication(GPU): gdigrab보다 고해상도/고FPS에서 훨씬 빠름. 기본 모니터의 좌표는 0,0 기준.
                src = (f"ddagrab=output_idx=0:framerate={fps}:draw_mouse={1 if cursor else 0}"
                       f":video_size={w}x{h}:offset_x={x - mon[0]}:offset_y={y - mon[1]}")
                candidates.append((base, src + ",hwdownload,format=bgra"))
            candidates.append((gdi("desktop", rect=(x, y, w, h)), None))

        post = ["crop=trunc(iw/2)*2:trunc(ih/2)*2"]  # H.264는 가로세로가 짝수여야 함
        sc = int(self.var_scale.get().rstrip("%")) / 100
        if sc < 1:
            post.append(f"scale=trunc(iw*{sc}/2)*2:trunc(ih*{sc}/2)*2")
        post.append("format=yuv420p")
        enc = self.encoder_key()
        if enc == "auto":
            enc = self.encoders[0]
        tail = encoder_args(enc, QUALITY_NAMES.index(self.var_quality.get())) + ["-r", fps, "-movflags", "+faststart", outfile]

        cmds = []
        for head, src in candidates:
            if src:  # 입력 장치 없이 소스 필터만 쓰는 경우
                cmds.append(head + ["-filter_complex", ",".join([src] + post)] + tail)
            else:
                cmds.append(head + ["-vf", ",".join(post)] + tail)
        return cmds

    def collect_settings(self):
        self.s.update({
            "mode": self.mode.get(),
            "monitor": max(0, self.cb_monitor.current()),
            "window_screen_capture": self.var_winscreen.get(),
            "quality": QUALITY_NAMES.index(self.var_quality.get()),
            "fps": self.var_fps.get(),
            "scale": self.var_scale.get(),
            "cursor": self.var_cursor.get(),
            "encoder": self.encoder_key(),
            "outdir": self.var_outdir.get(),
            "minimize": self.var_min.get(),
        })
        save_settings(self.s)

    def start(self):
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg.exe 를 찾을 수 없습니다.")
            return
        self.collect_settings()
        outdir = self.var_outdir.get()
        try:
            os.makedirs(outdir, exist_ok=True)
            self.out_file = os.path.join(outdir, datetime.now().strftime("PolarDeer_%Y%m%d_%H%M%S.mp4"))
            self.pending_cmds = self.build_commands(self.out_file)
        except Exception as e:
            messagebox.showwarning(APP_NAME, str(e))
            return
        self.starting = True
        for t in self.tiles.values():
            t.set_enabled(False)
        self.btn_settings.set_enabled(False)
        self.set_status("시작하는 중…")
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.write_bytes(b"")
        except OSError:
            pass
        hide = self.var_min.get() and self.mode.get() != "window"
        if hide:
            self.root.iconify()  # 녹화 화면에 이 창이 찍히지 않도록
            if self.settings_win:
                self.settings_win.destroy()
        self.root.after(450 if hide else 0, self.launch_next)

    def launch_next(self):
        cmd = self.pending_cmds.pop(0)
        try:
            with open(LOG_PATH, "ab") as log:
                log.write(("\n$ " + " ".join(cmd) + "\n").encode("utf-8", "replace"))
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                         stderr=open(LOG_PATH, "ab"), creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            self.reset_ui()
            self.root.deiconify()
            messagebox.showerror(APP_NAME, f"ffmpeg 실행 실패: {e}")
            return
        self.root.after(1000, self.check_started)

    def check_started(self):
        if self.proc.poll() is not None:
            if self.pending_cmds:  # 이 방식이 실패했으면 호환 방식으로 재시도
                self.launch_next()
            else:
                self.finish(error=True)
            return
        self.starting = False
        self.recording = True
        self.t0 = time.time()
        self.beep(1000)

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        self.set_status("저장 중…")
        proc = self.proc

        def work():
            try:
                proc.stdin.write(b"q")  # ffmpeg에 'q'를 보내면 파일을 정상적으로 마무리하고 종료
                proc.stdin.flush()
                proc.wait(timeout=20)
            except Exception:
                proc.kill()
            self.events.put(("stopped", proc.returncode))

        threading.Thread(target=work, daemon=True).start()

    def reset_ui(self):
        self.recording = False
        self.starting = False
        self.lbl_rec.configure(text="")
        for t in self.tiles.values():
            t.set_enabled(True)
        self.btn_settings.set_enabled(True)
        self.refresh_rec_button()

    def finish(self, error):
        self.reset_ui()
        self.root.deiconify()
        self.root.lift()
        if error:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            try:
                tail = "\n".join(LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:])
            except Exception:
                tail = ""
            self.set_status("녹화 실패")
            messagebox.showerror(APP_NAME, f"녹화 중 오류가 발생했습니다.\n\n{tail}\n\n로그: {LOG_PATH}")
            return
        self.beep(600)
        try:
            mb = os.path.getsize(self.out_file) / 1048576
            self.last_file = self.out_file
            self.set_status(f"저장됨: {os.path.basename(self.out_file)}  ({mb:.1f} MB)  — 클릭하면 폴더에서 보기", link=True)
        except OSError:
            self.set_status("저장 실패 (파일 없음)")

    @staticmethod
    def beep(freq):
        threading.Thread(target=lambda: winsound.Beep(freq, 90), daemon=True).start()

    def on_close(self):
        if self.recording:
            if not messagebox.askyesno(APP_NAME, "녹화 중입니다. 정지하고 종료할까요?"):
                return
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.wait(timeout=15)
            except Exception:
                self.proc.kill()
        self.collect_settings()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
