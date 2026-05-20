"""
Splash Screen
==============

Shows a borderless splash window while ClaudeMeter initialises.
Uses PIL to render the design and Win32 via ctypes to display it.
No extra dependencies beyond Pillow (already required).

Usage:
    splash = SplashScreen()
    splash.show()
    # ... do initialisation ...
    splash.close()
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import threading
import time
from pathlib import Path

__all__ = ['SplashScreen']

# ── Constants ──────────────────────────────────────────────────────────────────
_W, _H        = 360, 220          # splash dimensions (logical px)
_BG           = (28, 28, 30)      # dark background
_ORANGE       = (217, 119, 87)    # Claude orange
_WHITE        = (255, 255, 255)
_DIM          = (120, 120, 120)
_BAR_BG       = (55, 55, 58)
_BAR_FG       = (217, 119, 87)    # orange progress bar
_FADE_STEPS   = 20
_FADE_MS      = 15                # ms per fade step → ~300ms total fade
_SHOW_MS      = 800               # minimum display time before close is allowed

# Win32 constants
_WS_POPUP          = 0x80000000
_WS_EX_LAYERED     = 0x00080000
_WS_EX_TOPMOST     = 0x00000008
_WS_EX_TOOLWINDOW  = 0x00000080
_LWA_ALPHA         = 0x00000002
_LWA_COLORKEY      = 0x00000001
_GWL_EXSTYLE       = -20
_SM_CXSCREEN       = 0
_SM_CYSCREEN       = 1
_DIB_RGB_COLORS    = 0
_BI_RGB            = 0
_SRCCOPY           = 0x00CC0020


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize',          ctypes.c_uint32),
        ('biWidth',         ctypes.c_int32),
        ('biHeight',        ctypes.c_int32),
        ('biPlanes',        ctypes.c_uint16),
        ('biBitCount',      ctypes.c_uint16),
        ('biCompression',   ctypes.c_uint32),
        ('biSizeImage',     ctypes.c_uint32),
        ('biXPelsPerMeter', ctypes.c_int32),
        ('biYPelsPerMeter', ctypes.c_int32),
        ('biClrUsed',       ctypes.c_uint32),
        ('biClrImportant',  ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', _BITMAPINFOHEADER), ('bmiColors', ctypes.c_uint32 * 3)]


def _render_splash(width: int, height: int, progress: float = 0.0):
    """Render the splash image using PIL. Returns a PIL Image (RGBA)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    img  = Image.new('RGBA', (width, height), (*_BG, 255))
    draw = ImageDraw.Draw(img)

    # ── Background subtle vignette ──
    # Draw slightly lighter border
    draw.rounded_rectangle([0, 0, width-1, height-1], radius=12,
                            outline=(*_ORANGE, 60), width=1)

    # ── Load fonts ──
    windir = 'C:\\Windows'
    def _font(size, bold=True):
        names = [
            f'{windir}\\Fonts\\arialbd.ttf' if bold else f'{windir}\\Fonts\\arial.ttf',
            f'{windir}\\Fonts\\arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        for n in names:
            try:
                return ImageFont.truetype(n, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ── Big orange "C" ──
    c_font = _font(88)
    bbox   = draw.textbbox((0, 0), 'C', font=c_font)
    cw, ch = bbox[2]-bbox[0], bbox[3]-bbox[1]
    cx     = (width - cw) // 2 - bbox[0]
    cy     = int(height * 0.08) - bbox[1]
    draw.text((cx, cy), 'C', fill=(*_ORANGE, 255), font=c_font)

    # ── "ClaudeMeter" title ──
    title_font = _font(26)
    title      = 'ClaudeMeter'
    bbox       = draw.textbbox((0, 0), title, font=title_font)
    tw         = bbox[2] - bbox[0]
    tx         = (width - tw) // 2 - bbox[0]
    ty         = int(height * 0.62) - bbox[1]
    draw.text((tx, ty), title, fill=(*_WHITE, 255), font=title_font)

    # ── Subtitle ──
    sub_font = _font(12, bold=False)
    subtitle = 'Claude API Usage Monitor'
    bbox     = draw.textbbox((0, 0), subtitle, font=sub_font)
    sw       = bbox[2] - bbox[0]
    sx       = (width - sw) // 2 - bbox[0]
    sy       = ty + 34
    draw.text((sx, sy), subtitle, fill=(*_DIM, 255), font=sub_font)

    # ── Progress bar ──
    bar_margin = 32
    bar_h      = 3
    bar_y      = height - 28
    bar_w      = width - bar_margin * 2
    bar_r      = 2

    # Track
    draw.rounded_rectangle(
        [bar_margin, bar_y, bar_margin+bar_w, bar_y+bar_h],
        radius=bar_r, fill=(*_BAR_BG, 255)
    )
    # Fill
    fill_w = max(8, int(bar_w * min(progress, 1.0)))
    draw.rounded_rectangle(
        [bar_margin, bar_y, bar_margin+fill_w, bar_y+bar_h],
        radius=bar_r, fill=(*_BAR_FG, 255)
    )

    # ── Version ──
    ver_font = _font(10, bold=False)
    try:
        from usage_monitor_for_claude import __version__ as _v
        ver_text = f'v{_v}'
    except Exception:
        ver_text = 'v2.0.0'
    bbox     = draw.textbbox((0, 0), ver_text, font=ver_font)
    vx       = width - (bbox[2]-bbox[0]) - 10 - bbox[0]
    vy       = height - 18 - bbox[1]
    draw.text((vx, vy), ver_text, fill=(*_DIM, 180), font=ver_font)

    return img


def _pil_to_hbitmap(img):
    """Convert a PIL RGBA image to a Win32 HBITMAP."""
    import ctypes
    w, h = img.size
    # Convert to BGRA (Win32 DIB format)
    bgra = img.convert('RGBA')
    r, g, b, a = bgra.split()
    from PIL import Image as _Image
    bgra = _Image.merge('RGBA', (b, g, r, a))
    data = bgra.tobytes()

    bmi           = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = w
    bmi.bmiHeader.biHeight      = -h   # top-down
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = _BI_RGB

    hdc     = ctypes.windll.user32.GetDC(None)
    mem_dc  = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
    pp      = ctypes.c_void_p()
    hbm     = ctypes.windll.gdi32.CreateDIBSection(
        hdc, ctypes.byref(bmi), _DIB_RGB_COLORS,
        ctypes.byref(pp), None, 0
    )
    ctypes.windll.gdi32.SelectObject(mem_dc, hbm)
    ctypes.memmove(pp, data, len(data))
    ctypes.windll.gdi32.DeleteDC(mem_dc)
    ctypes.windll.user32.ReleaseDC(None, hdc)
    return hbm


class SplashScreen:
    """Borderless splash window shown during app startup."""

    def __init__(self) -> None:
        self._hwnd: int = 0
        self._thread: threading.Thread | None = None
        self._close_event = threading.Event()
        self._shown_at: float = 0.0
        self._progress: float = 0.0
        self._lock = threading.Lock()

    def show(self) -> None:
        """Show the splash screen in a background thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Give it a moment to render
        time.sleep(0.05)

    def set_progress(self, pct: float) -> None:
        """Update the progress bar (0.0 – 1.0)."""
        with self._lock:
            self._progress = pct
        self._redraw(pct)

    def close(self) -> None:
        """Signal the splash to complete its progress bar then fade out."""
        # Respect minimum display time
        elapsed = time.time() - self._shown_at
        remaining = _SHOW_MS / 1000 - elapsed
        if remaining > 0:
            time.sleep(remaining)
        # Signal _run() to finish progress animation then fade
        self._close_event.set()
        # Wait for _run thread to finish progress, then fade out
        if self._thread:
            self._thread.join(timeout=2.0)
        self._fade_out()

    def _run(self) -> None:
        """Create and show the Win32 window."""
        try:
            self._create_window()
            self._shown_at = time.time()
            self._redraw(0.0)

            # Animate progress bar while waiting for close signal
            prog = 0.0
            while not self._close_event.is_set():
                if prog < 0.85:
                    prog = min(prog + 0.012, 0.85)
                    self._redraw(prog)
                time.sleep(0.05)

            # Close signal received — animate progress to 100% before fading
            while prog < 1.0:
                prog = min(prog + 0.05, 1.0)
                self._redraw(prog)
                time.sleep(0.02)

            # Hold at 100% briefly so user can see it complete
            time.sleep(0.3)

        except Exception:
            pass

    def _create_window(self) -> None:
        """Register window class and create the splash window."""
        # Set per-monitor DPI awareness so coordinates are consistent
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        # Get DPI — use monitor-aware version
        hmon = ctypes.windll.user32.MonitorFromPoint(
            ctypes.wintypes.POINT(0, 0), 1  # MONITOR_DEFAULTTOPRIMARY
        )
        dpi_x = ctypes.c_uint(96)
        dpi_y = ctypes.c_uint(96)
        try:
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        except Exception:
            dpi_x.value = ctypes.windll.user32.GetDpiForSystem() or 96

        scale = dpi_x.value / 96

        # Physical dimensions
        w_phys = int(_W * scale)
        h_phys = int(_H * scale)

        # Use work area in physical pixels for centering
        class RECT(ctypes.Structure):
            _fields_ = [('left',ctypes.c_long),('top',ctypes.c_long),
                        ('right',ctypes.c_long),('bottom',ctypes.c_long)]
        work = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)
        x = work.left  + (work.right  - work.left - w_phys) // 2
        y = work.top   + (work.bottom - work.top  - h_phys) // 2

        # Use physical pixels directly with SW_HIDE initially
        w = w_phys
        h = h_phys

        hinstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.wintypes.HWND,
            ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )

        DefWindowProc = ctypes.windll.user32.DefWindowProcW
        DefWindowProc.restype  = ctypes.c_longlong
        DefWindowProc.argtypes = [
            ctypes.wintypes.HWND, ctypes.c_uint,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        ]

        @WNDPROC
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == 0x0002:  # WM_DESTROY
                ctypes.windll.user32.PostQuitMessage(0)
                return 0
            return DefWindowProc(hwnd, msg, wparam, lparam)

        self._wnd_proc = wnd_proc  # keep reference

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ('style',         ctypes.c_uint),
                ('lpfnWndProc',   ctypes.c_void_p),
                ('cbClsExtra',    ctypes.c_int),
                ('cbWndExtra',    ctypes.c_int),
                ('hInstance',     ctypes.wintypes.HANDLE),
                ('hIcon',         ctypes.wintypes.HANDLE),
                ('hCursor',       ctypes.wintypes.HANDLE),
                ('hbrBackground', ctypes.wintypes.HANDLE),
                ('lpszMenuName',  ctypes.c_wchar_p),
                ('lpszClassName', ctypes.c_wchar_p),
            ]

        cls              = WNDCLASSW()
        cls.lpfnWndProc  = ctypes.cast(wnd_proc, ctypes.c_void_p)
        cls.hInstance    = hinstance
        cls.lpszClassName = 'ClaudeMeterSplash'
        cls.hbrBackground = ctypes.windll.gdi32.CreateSolidBrush(
            _BG[0] | (_BG[1] << 8) | (_BG[2] << 16)
        )
        ctypes.windll.user32.RegisterClassW(ctypes.byref(cls))

        hwnd = ctypes.windll.user32.CreateWindowExW(
            _WS_EX_LAYERED | _WS_EX_TOPMOST | _WS_EX_TOOLWINDOW,
            'ClaudeMeterSplash', 'ClaudeMeter',
            _WS_POPUP,
            x, y, w, h,
            None, None, hinstance, None
        )
        self._hwnd  = hwnd
        self._scale = scale
        self._w     = w_phys
        self._h     = h_phys

        # Start invisible — render content first, then show to avoid jump
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 0, _LWA_ALPHA)

        # Force correct position before showing
        _SWP_FLAGS = 0x0014  # SWP_NOSIZE | SWP_NOZORDER ... actually reposition
        ctypes.windll.user32.SetWindowPos(hwnd, -1, x, y, w, h, 0x0010)  # HWND_TOPMOST, SWP_NOACTIVATE

        # Draw content while still transparent
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.UpdateWindow(hwnd)

        # Pause to let window settle in position before fading in
        time.sleep(0.15)

        # Fade in
        for i in range(_FADE_STEPS + 1):
            alpha = int(255 * i / _FADE_STEPS)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, alpha, _LWA_ALPHA)
            time.sleep(_FADE_MS / 1000)

    def _redraw(self, progress: float) -> None:
        """Redraw the splash with updated progress."""
        if not self._hwnd:
            return
        try:
            img = _render_splash(self._w, self._h, progress)
            if not img:
                return
            hbm = _pil_to_hbitmap(img)
            hdc = ctypes.windll.user32.GetDC(self._hwnd)
            mem = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
            ctypes.windll.gdi32.SelectObject(mem, hbm)
            ctypes.windll.gdi32.BitBlt(
                hdc, 0, 0, img.width, img.height,
                mem, 0, 0, _SRCCOPY
            )
            ctypes.windll.gdi32.DeleteDC(mem)
            ctypes.windll.gdi32.DeleteObject(hbm)
            ctypes.windll.user32.ReleaseDC(self._hwnd, hdc)
        except Exception:
            pass

    def _fade_out(self) -> None:
        """Fade the splash window to transparent then destroy it."""
        if not self._hwnd:
            return
        try:
            for i in range(_FADE_STEPS, -1, -1):
                alpha = int(255 * i / _FADE_STEPS)
                ctypes.windll.user32.SetLayeredWindowAttributes(
                    self._hwnd, 0, alpha, _LWA_ALPHA
                )
                time.sleep(_FADE_MS / 1000)
            ctypes.windll.user32.DestroyWindow(self._hwnd)
            self._hwnd = 0
        except Exception:
            pass
