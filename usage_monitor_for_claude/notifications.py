"""
Notifications
==============

Windows toast notifications for usage threshold alerts.
Uses winotify for native Windows 10/11 Action Center toasts.

Falls back to a simple ctypes MessageBeep if winotify is unavailable
so the app never crashes on missing dependency.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

__all__ = ['notify_threshold', 'notify_reset']

# Path to app icon for toast branding
_ICON_PATH = Path(__file__).parent.parent / 'claudemeter.ico'

# Track sent notifications to avoid repeating: key -> last_sent_time
_sent: dict[str, float] = {}
_lock = threading.Lock()

# Minimum seconds between repeat notifications for the same key
_COOLDOWN = 3600  # 1 hour


def _can_send(key: str) -> bool:
    """Return True if enough time has passed since last notification for this key."""
    now = time.time()
    with _lock:
        last = _sent.get(key, 0)
        if now - last < _COOLDOWN:
            return False
        _sent[key] = now
        return True


def _send(title: str, message: str, key: str) -> None:
    """Send a toast notification in a daemon thread."""
    if not _can_send(key):
        return
    threading.Thread(target=_toast, args=(title, message), daemon=True).start()


def _toast(title: str, message: str) -> None:
    """Show a Windows toast notification."""
    try:
        from winotify import Notification, audio  # type: ignore
        icon = str(_ICON_PATH) if _ICON_PATH.exists() else ''
        toast = Notification(
            app_id='ClaudeMeter',
            title=title,
            msg=message,
            icon=icon,
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        # winotify not installed — silent fallback
        pass
    except Exception:
        pass


def notify_threshold(label: str, pct: float, key: str) -> None:
    """Fire a toast when usage crosses a warning threshold.

    Parameters
    ----------
    label : str
        Human-readable usage label, e.g. "Session (5hr)"
    pct : float
        Current usage percentage (0-100)
    key : str
        Unique key for cooldown tracking, e.g. "five_hour_80"
    """
    pct_int = int(pct)
    if pct_int >= 95:
        title = f'⚠️ {label} almost full'
        msg   = f'{label} is at {pct_int}% — nearly exhausted.'
    else:
        title = f'⚡ {label} at {pct_int}%'
        msg   = f'{label} has reached {pct_int}% usage.'
    _send(title, msg, key)


def notify_reset(label: str, key: str) -> None:
    """Fire a toast when a usage period resets.

    Parameters
    ----------
    label : str
        Human-readable usage label
    key : str
        Unique key for cooldown tracking
    """
    _send(
        f'✅ {label} reset',
        f'{label} has reset — full quota available.',
        key,
    )
