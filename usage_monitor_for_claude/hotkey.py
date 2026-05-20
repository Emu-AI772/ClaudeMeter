"""
Hotkey
=======

Registers a global hotkey (Ctrl+Shift+C) that toggles the ClaudeMeter
popup open or closed, even when the app is minimised to the tray.

Uses Win32 RegisterHotKey / GetMessage loop — no extra dependencies.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Callable

__all__ = ['start_hotkey_listener']

# Virtual key codes
_VK_C           = 0x43
_MOD_CONTROL    = 0x0002
_MOD_SHIFT      = 0x0004
_MOD_NOREPEAT   = 0x4000   # don't fire repeatedly while held
_WM_HOTKEY      = 0x0312
_HOTKEY_ID      = 1


def start_hotkey_listener(callback: Callable) -> None:
    """Register Ctrl+Shift+C and call *callback* each time it is pressed.

    Designed to run in a daemon thread — blocks until the thread is killed.

    Parameters
    ----------
    callback : callable
        Called (with no arguments) when the hotkey fires.
    """
    tid = ctypes.windll.kernel32.GetCurrentThreadId()

    registered = ctypes.windll.user32.RegisterHotKey(
        None,
        _HOTKEY_ID,
        _MOD_CONTROL | _MOD_SHIFT | _MOD_NOREPEAT,
        _VK_C,
    )

    if not registered:
        # Hotkey already claimed by another app — try without NOREPEAT
        registered = ctypes.windll.user32.RegisterHotKey(
            None,
            _HOTKEY_ID,
            _MOD_CONTROL | _MOD_SHIFT,
            _VK_C,
        )

    if not registered:
        return  # Can't register — silently skip

    try:
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                try:
                    callback()
                except Exception:
                    pass
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
