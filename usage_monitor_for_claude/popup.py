"""
Popup Window
=============

Dark-themed HTML popup window showing account info and usage bars.
Uses pywebview with Edge WebView2 for smooth CSS transitions and
flexible layout.

Extended with:
- Always-on-top toggle
- Anchor/float mode (dock to corner or free-drag)
- Persistent usage history log (~/.claude/usage-monitor-history.jsonl)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import webview  # type: ignore[import-untyped]  # no type stubs available

from . import __version__
from .claude_cli import CHANGELOG_URL, find_installations
from .tray_icon import taskbar_uses_light_theme
from .formatting import elapsed_pct, expand_popup_fields, field_period, format_credits, midnight_positions, popup_label, time_until
from .i18n import T
from .settings import BAR_BG, BAR_DIVIDER, BAR_FG, BAR_FG_WARN, BAR_MARKER, BG, FG, FG_DIM, FG_HEADING, FG_LINK, POPUP_FIELDS

_POPUP_DIR = Path(__file__).parent / 'popup'
_LOG_DIR = Path.home() / '.claude' / 'usage-monitor-logs'
_HISTORY_PATH = _LOG_DIR / 'usage-monitor-history.csv'
_SUMMARY_PATH = _LOG_DIR / 'claudemeter-daily-summary.csv'
_BASELINE_DPI = 96
_GWL_EXSTYLE = -20
_WS_EX_APPWINDOW = 0x00040000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000
_LWA_ALPHA = 0x00000002
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010

# Anchor positions: corner key -> (x_from_right, y_from_bottom)
_ANCHOR_CORNERS = {
    'tray': None,       # default: near tray (original behaviour)
    'tr': (True, False),   # top-right
    'tl': (False, False),  # top-left
    'br': (True, True),    # bottom-right
    'bl': (False, True),   # bottom-left
}

# Prefs file stored next to settings
_PREFS_PATH = Path.home() / '.claude' / 'usage-monitor-prefs.json'


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


__all__ = ['UsagePopup']

if TYPE_CHECKING:
    from .app import UsageMonitorForClaude
    from .cache import CacheSnapshot


# ---------------------------------------------------------------------------
# Prefs helpers
# ---------------------------------------------------------------------------

def _load_prefs() -> dict:
    try:
        if _PREFS_PATH.exists():
            return json.loads(_PREFS_PATH.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def _save_prefs(prefs: dict) -> None:
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_PATH.write_text(json.dumps(prefs, indent=2), encoding='utf-8')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

_history_lock = threading.Lock()


def _current_slot() -> str:
    """Return the current 30-minute slot as a string, e.g. '2026-05-18 15:00'."""
    now = datetime.now()
    slot_min = (now.minute // 30) * 30
    return now.strftime(f'%Y-%m-%d %H:{slot_min:02d}')


def _write_history(usage: list[dict]) -> None:
    """Append a snapshot to the CSV if the current 30-min slot isn't recorded yet."""
    slot = _current_slot()
    with _history_lock:
        try:
            import csv
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            write_header = not _HISTORY_PATH.exists()

            # Check if this slot is already recorded
            if not write_header:
                with _HISTORY_PATH.open('r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0] == slot:
                            return  # slot already written, skip

            with _HISTORY_PATH.open('a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                if write_header:
                    labels = [u['label'] for u in usage]
                    writer.writerow(['Timestamp'] + labels)
                writer.writerow([slot] + [u['pct_text'] for u in usage])
        except Exception:
            pass


def _read_history_last_24h() -> list[dict]:
    """Read the last 24 hours of history from the CSV file."""
    if not _HISTORY_PATH.exists():
        return []
    cutoff = time.time() - 86400  # 24h ago
    records = []
    try:
        import csv
        with _HISTORY_PATH.open('r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get('Timestamp', '')
                    if not ts_str:
                        continue
                    # Parse as local time (CSV is written in local time)
                    ts_dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M')
                    ts = ts_dt.timestamp()  # local naive -> epoch correctly
                    if ts < cutoff:
                        continue
                    # Build usage list from remaining columns
                    usage = [
                        {'label': k, 'pct_text': v, 'fill_pct': _pct_to_float(v), 'warn': _pct_to_float(v) >= 0.8}
                        for k, v in row.items() if k != 'Timestamp'
                    ]
                    records.append({'ts': ts * 1000, 'usage': usage})
                except Exception:
                    continue
    except Exception:
        pass
    return records


def _read_all_history() -> list[dict]:
    """Read all history records from the CSV file."""
    if not _HISTORY_PATH.exists():
        return []
    records = []
    try:
        import csv
        with _HISTORY_PATH.open('r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get('Timestamp', '')
                    if not ts_str:
                        continue
                    ts_dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M')
                    ts    = ts_dt.timestamp()
                    usage = [
                        {'label': k, 'pct_text': v,
                         'fill_pct': _pct_to_float(v),
                         'warn': _pct_to_float(v) >= 0.8}
                        for k, v in row.items() if k != 'Timestamp'
                    ]
                    records.append({'ts': ts * 1000, 'usage': usage})
                except Exception:
                    continue
    except Exception:
        pass
    return records


def _write_daily_summary() -> None:
    """Compute and append yesterday's daily summary to the summary CSV.
    
    Called on startup and from the poll loop. Skips if yesterday is already
    summarised. Thread-safe via _history_lock.
    """
    with _history_lock:
        try:
            import csv
            from datetime import date, timedelta

            yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

            # Check if already summarised
            if _SUMMARY_PATH.exists():
                with _SUMMARY_PATH.open('r', encoding='utf-8', newline='') as f:
                    for row in csv.reader(f):
                        if row and row[0] == yesterday:
                            return  # already done

            # Read yesterday's history rows
            if not _HISTORY_PATH.exists():
                return

            rows_by_label: dict[str, list[float]] = {}
            resets_hit = 0

            with _HISTORY_PATH.open('r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts_str = row.get('Timestamp', '')
                    if not ts_str or not ts_str.startswith(yesterday):
                        continue
                    for label, val in row.items():
                        if label == 'Timestamp':
                            continue
                        pct = _pct_to_float(val) * 100
                        rows_by_label.setdefault(label, []).append(pct)
                        if pct >= 100:
                            resets_hit += 1

            if not rows_by_label:
                return  # no data for yesterday

            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            write_header = not _SUMMARY_PATH.exists()

            with _SUMMARY_PATH.open('a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                if write_header:
                    labels = list(rows_by_label.keys())
                    header = ['Date']
                    for l in labels:
                        header += [f'{l} Peak%', f'{l} Avg%']
                    header.append('Resets Hit')
                    writer.writerow(header)

                row_out = [yesterday]
                for vals in rows_by_label.values():
                    peak = max(vals)
                    avg  = sum(vals) / len(vals)
                    row_out += [f'{peak:.0f}%', f'{avg:.0f}%']
                row_out.append(resets_hit)
                writer.writerow(row_out)

        except Exception:
            pass


def _pct_to_float(pct_text: str) -> float:
    """Convert '54%' -> 0.54"""
    try:
        return float(pct_text.strip('%')) / 100
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _usage_entries(usage: dict[str, Any]) -> list[tuple[str, dict[str, Any] | None, int | None]]:
    fields = expand_popup_fields(POPUP_FIELDS, usage)
    return [(popup_label(key), usage.get(key), field_period(key)) for key in fields]


def _snapshot_to_dict(
    snap: CacheSnapshot, installations: list[dict[str, str]] | None = None, next_poll_time: float | None = None,
) -> dict[str, Any]:
    profile = None
    if snap.profile:
        account = snap.profile.get('account', {})
        org = snap.profile.get('organization', {})
        profile = {
            'email': account.get('email', ''),
            'plan': org.get('organization_type', '').replace('_', ' ').title(),
        }

    usage = []
    if snap.usage:
        for label, entry, period in _usage_entries(snap.usage):
            if not entry or entry.get('utilization') is None:
                continue
            pct = entry.get('utilization', 0) or 0
            resets_at = entry.get('resets_at', '')
            time_pct = elapsed_pct(resets_at, period) if period else None
            warn = pct >= 100 or (time_pct is not None and pct > time_pct)
            marker_rel = max(0.0, min(1.0, time_pct / 100)) if time_pct is not None else None

            usage.append({
                'label': label,
                'pct_text': f'{pct:.0f}%',
                'fill_pct': max(0.0, min(1.0, pct / 100)),
                'warn': warn,
                'reset_text': time_until(resets_at) if resets_at else '',
                'midnights': midnight_positions(resets_at, period) if period else [],
                'marker_rel': marker_rel,
            })

        # Write to history log (throttled)
        if usage:
            threading.Thread(target=_write_history, args=(usage,), daemon=True).start()

    extra = None
    if snap.usage:
        extra_data = snap.usage.get('extra_usage')
        if extra_data and extra_data.get('is_enabled'):
            limit = extra_data.get('monthly_limit', 0) or 0
            if limit > 0:
                used = extra_data.get('used_credits', 0) or 0
                pct = used / limit * 100
                extra = {
                    'pct_text': f'{pct:.0f}%',
                    'fill_pct': max(0.0, min(1.0, pct / 100)),
                    'spent_text': T['extra_usage_spent'].format(
                        used=format_credits(used), limit=format_credits(limit),
                    ),
                }

    if installations is None:
        installations = [{'name': i.name, 'version': i.version} for i in find_installations()]

    if not snap.usage:
        if snap.last_error:
            status: dict[str, Any] = {'text': snap.last_error[:120], 'is_error': True}
        else:
            status = {'text': T['status_refreshing'], 'is_error': False, 'refreshing': True}
    else:
        status = {
            'last_success_time': snap.last_success_time,
            'next_poll_time': next_poll_time,
            'refreshing': snap.refreshing,
            'error': snap.last_error[:120] if snap.last_error else None,
        }

    return {
        'profile': profile,
        'usage': usage,
        'extra': extra,
        'installations': installations,
        'status': status,
    }


def _build_usage_for_history(usage_data: dict) -> list[dict]:
    """Build a minimal usage list suitable for _write_history from raw API data."""
    from .formatting import expand_popup_fields, field_period, popup_label, elapsed_pct
    fields = expand_popup_fields(POPUP_FIELDS, usage_data)
    result = []
    for key in fields:
        entry = usage_data.get(key)
        if not entry or entry.get('utilization') is None:
            continue
        pct = entry.get('utilization', 0) or 0
        resets_at = entry.get('resets_at', '')
        period = field_period(key)
        time_pct = elapsed_pct(resets_at, period) if period else None
        warn = pct >= 100 or (time_pct is not None and pct > time_pct)
        result.append({
            'label': popup_label(key),
            'pct_text': f'{pct:.0f}%',
            'fill_pct': max(0.0, min(1.0, pct / 100)),
            'warn': warn,
        })
    return result


def _init_config(snap: CacheSnapshot, next_poll_time: float | None = None, prefs: dict | None = None) -> dict[str, Any]:
    if prefs is None:
        prefs = _load_prefs()
    return {
        'colors': {
            # Default brand colours — warm dark with Claude orange
            # These are overridden by JS theme system after load
            'bg': '#1c1c1e', 'fg': '#cccccc', 'fg_dim': '#888888',
            'fg_heading': '#ffffff', 'fg_link': '#d97757',
            'bar_bg': '#2c2c2e', 'bar_fg': '#d97757',
            'bar_fg_warn': BAR_FG_WARN, 'bar_divider': BAR_DIVIDER, 'bar_marker': BAR_MARKER,
        },
        't': {
            'title': T['popup_title'], 'account': T['account'], 'email': T['email'], 'plan': T['plan'],
            'usage': T['usage'], 'extra_usage': T['extra_usage'],
            'claude_code': T['claude_code'], 'changelog': T['changelog'],
            'status_updated_s': T['status_updated_s'], 'status_updated': T['status_updated'],
            'status_next_update': T['status_next_update'], 'status_refreshing': T['status_refreshing'],
            'duration_hm': T['duration_hm'], 'duration_m': T['duration_m'], 'duration_s': T['duration_s'],
        },
        'app_version': __version__,
        'data': _snapshot_to_dict(snap, next_poll_time=next_poll_time),
        'prefs': prefs,
        'custom_theme': prefs.get('custom_theme', {}),
        'system_theme': 'light' if taskbar_uses_light_theme() else 'dark',
        'history_path': str(_HISTORY_PATH),
    }


# ---------------------------------------------------------------------------
# JS-callable API
# ---------------------------------------------------------------------------

class _PopupApi:
    """Methods exposed to JavaScript via pywebview's JS bridge."""

    def __init__(self, popup: UsagePopup) -> None:
        self._popup = popup

    def close(self) -> None:
        self._popup._close()

    def open_url(self) -> None:
        webbrowser.open(CHANGELOG_URL)

    def get_yesterday_summary(self) -> dict:
        """Return yesterday's peak and average usage from the summary CSV."""
        try:
            import csv
            from datetime import date, timedelta
            yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
            if not _SUMMARY_PATH.exists():
                return {}
            with _SUMMARY_PATH.open('r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('Date') == yesterday:
                        # Return all columns except Date
                        return {k: v for k, v in row.items() if k != 'Date' and k != 'Resets Hit'} |                                {'date': yesterday, 'resets': row.get('Resets Hit', '0')}
            return {}
        except Exception:
            return {}

    def save_notify_prefs(self, session_pct: int, weekly_pct: int, on_reset: bool) -> None:
        """Save notification threshold preferences and reset tracking so new
        thresholds fire immediately if already exceeded."""
        prefs = _load_prefs()
        prefs['notify_session_pct'] = max(1, min(99, int(session_pct)))
        prefs['notify_weekly_pct']  = max(1, min(99, int(weekly_pct)))
        prefs['notify_on_reset']    = bool(on_reset)
        _save_prefs(prefs)
        # Reset threshold tracking and trigger immediate check
        try:
            app = self._popup.app
            app._notified_thresholds.clear()
            # Fire check immediately against current data
            if app._last_response:
                threading.Thread(
                    target=app._check_threshold_alerts,
                    args=(app._last_response,),
                    daemon=True
                ).start()
        except Exception:
            pass

    def test_notification(self) -> None:
        """Send a test Windows toast notification."""
        try:
            from .notifications import _toast
            _toast(
                'ClaudeMeter — Test Notification',
                'Notifications are working correctly! You will be alerted at 80% and 95% usage.'
            )
        except Exception as e:
            pass

    def set_autostart(self, enabled: bool) -> None:
        """Enable or disable start with Windows via registry."""
        try:
            from .autostart import set_autostart as _set
            _set(enabled)
        except Exception:
            pass

    def get_autostart(self) -> bool:
        """Return current autostart state from registry."""
        try:
            from .autostart import is_autostart_enabled
            return is_autostart_enabled()
        except Exception:
            return False

    def set_custom_theme(self, colors: dict) -> None:
        """Persist a custom RGB theme to prefs."""
        try:
            prefs = _load_prefs()
            prefs['theme'] = 'custom'
            prefs['custom_theme'] = colors
            _save_prefs(prefs)
        except Exception:
            pass

    def set_theme(self, name: str) -> None:
        """Persist selected theme name."""
        allowed = {'default', 'traffic', 'neon', 'minimal', 'system', 'custom'}
        if name in allowed:
            prefs = _load_prefs()
            prefs['theme'] = name
            _save_prefs(prefs)

    def save_pref(self, key: str, value: Any) -> None:
        """Save a single preference value (called from JS for display_mode, view, etc.)"""
        allowed = {'display_mode', 'view', 'compact', 'theme'}
        if key in allowed:
            prefs = _load_prefs()
            prefs[key] = value
            _save_prefs(prefs)

    def open_history_file(self) -> None:
        """Open the CSV in Notepad (avoids Excel association issues)."""
        try:
            import subprocess
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            if _HISTORY_PATH.exists():
                subprocess.Popen(['notepad.exe', str(_HISTORY_PATH)])
            else:
                subprocess.Popen(['explorer', str(_LOG_DIR)])
        except Exception:
            pass

    def export_history_csv(self, from_date: str | None, to_date: str | None) -> dict:
        """Export history rows filtered by date range to a new CSV file."""
        import csv as _csv
        from datetime import datetime as _dt
        try:
            if not _HISTORY_PATH.exists():
                return {'ok': False, 'path': None, 'error': 'No history file found'}

            # Parse filter dates
            from_ts = _dt.strptime(from_date, '%Y-%m-%d').timestamp() if from_date else 0
            to_ts   = _dt.strptime(to_date,   '%Y-%m-%d').timestamp() + 86399 if to_date else float('inf')

            # Read source CSV
            rows = []
            headers = []
            with _HISTORY_PATH.open('r', encoding='utf-8', newline='') as f:
                reader = _csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        headers = row
                        continue
                    if not row:
                        continue
                    try:
                        ts = _dt.strptime(row[0], '%Y-%m-%d %H:%M').timestamp()
                        if from_ts <= ts <= to_ts:
                            rows.append(row)
                    except Exception:
                        continue

            if not rows:
                return {'ok': False, 'path': None, 'error': 'No data in selected range'}

            # Build export filename
            suffix = f'{from_date or "all"}_to_{to_date or "latest"}'
            export_path = _LOG_DIR / f'claudemeter-export-{suffix}.csv'
            _LOG_DIR.mkdir(parents=True, exist_ok=True)

            with export_path.open('w', encoding='utf-8', newline='') as f:
                writer = _csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)

            return {'ok': True, 'path': str(export_path), 'rows': len(rows)}

        except Exception as e:
            return {'ok': False, 'path': None, 'error': str(e)}

    def open_export_file(self, path: str) -> None:
        """Select exported file in Explorer."""
        try:
            import subprocess
            subprocess.Popen(['explorer', '/select,', path])
        except Exception:
            pass

    def open_summary_file(self) -> None:
        """Open the daily summary CSV in Notepad, or log folder if not yet created."""
        try:
            import subprocess
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            if _SUMMARY_PATH.exists():
                subprocess.Popen(['notepad.exe', str(_SUMMARY_PATH)])
            else:
                subprocess.Popen(['explorer', str(_LOG_DIR)])
        except Exception:
            pass

    def open_log_folder(self) -> None:
        """Open the log directory in Explorer."""
        try:
            import subprocess
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(['explorer', str(_LOG_DIR)])
        except Exception:
            pass

    def report_height(self, height: int) -> None:
        if height and height != self._popup._last_height:
            self._popup._last_height = height
            self._popup._resize_and_position(height)
            if not self._popup._shown:
                self._popup._show_window()

    def set_always_on_top(self, enabled: bool) -> None:
        """Toggle always-on-top via Win32."""
        prefs = _load_prefs()
        prefs['always_on_top'] = enabled
        _save_prefs(prefs)
        self._popup._always_on_top = enabled
        hwnd = self._popup._popup_hwnd
        if hwnd:
            flag = _HWND_TOPMOST if enabled else _HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0,
                                               _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)

    def set_force_open(self, force: bool) -> None:
        """Force the popup to stay open (used by history view)."""
        self._popup._force_open = force

    def set_anchor(self, anchor: str) -> None:
        """Set anchor corner and reposition. anchor: 'tray'|'tr'|'tl'|'br'|'bl'|'float'"""
        prefs = _load_prefs()
        prefs['anchor'] = anchor
        _save_prefs(prefs)
        self._popup._anchor = anchor
        # Enable/disable drag based on float mode
        self._popup._float_mode = (anchor == 'float')
        # Reposition immediately
        self._popup._resize_and_position(self._popup._last_height)

    def set_float_position(self, x: int, y: int) -> None:
        """Save the user-dragged float position."""
        prefs = _load_prefs()
        prefs['float_x'] = x
        prefs['float_y'] = y
        _save_prefs(prefs)

    def get_history(self) -> list:
        """Return all history records — JS filters by selected range."""
        return _read_all_history()

    def move_window(self, dx: int, dy: int) -> None:
        """Move the window by a delta (called from JS drag handler)."""
        popup = self._popup
        hwnd = popup._popup_hwnd
        if not hwnd:
            return
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        new_x = rect.left + int(dx)
        new_y = rect.top + int(dy)
        popup._float_x = new_x
        popup._float_y = new_y
        # Use pywebview's move which handles DPI scaling correctly
        try:
            popup._window.move(new_x, new_y)
        except Exception:
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, new_x, new_y, 0, 0,
                _SWP_NOSIZE | _SWP_NOACTIVATE | 0x0004,
            )

    def save_window_position(self) -> None:
        """Persist the current window position to prefs after a drag."""
        popup = self._popup
        hwnd = popup._popup_hwnd
        if not hwnd:
            return
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        prefs = _load_prefs()
        prefs['float_x'] = rect.left
        prefs['float_y'] = rect.top
        _save_prefs(prefs)
        popup._float_x = rect.left
        popup._float_y = rect.top


# ---------------------------------------------------------------------------
# Popup window
# ---------------------------------------------------------------------------

class UsagePopup:
    """Dark-themed HTML popup window showing account info and usage bars."""

    WIDTH = 340
    _CHECK_MS = 2000

    def __init__(self, app: UsageMonitorForClaude) -> None:
        self.app = app
        self._running = True
        self._closed = threading.Event()
        self._popup_hwnd = 0
        initial_height = 400
        self._last_height = initial_height
        snap = app.cache.snapshot
        self._last_version = snap.version

        # Load saved prefs
        prefs = _load_prefs()
        self._anchor = prefs.get('anchor', 'tray')
        self._float_mode = (self._anchor == 'float')
        self._always_on_top = prefs.get('always_on_top', True)
        self._force_open = False
        self._float_x = prefs.get('float_x', None)
        self._float_y = prefs.get('float_y', None)

        api = _PopupApi(self)

        self._window = webview.create_window(
            '', url=str(_POPUP_DIR / 'popup.html'),
            width=self.WIDTH, height=initial_height,
            resizable=False, frameless=True, shadow=False,
            easy_drag=False,
            on_top=True,  # always create topmost; JS toggle adjusts after load
            hidden=True,
            background_color=BG,
            js_api=api,
        )
        self._shown = False
        self._window.events.loaded += self._on_loaded
        self._window.events.closed += self._on_window_closed
        if not self._float_mode:
            # Only auto-dismiss in non-float mode
            threading.Thread(target=self._dismiss_watch, daemon=True).start()
        self._closed.wait()

    def _on_loaded(self) -> None:
        prefs = _load_prefs()
        config = _init_config(self.app.cache.snapshot, next_poll_time=self.app._next_poll_time, prefs=prefs)
        self._window.evaluate_js(f'init({json.dumps(config)})')

        self._popup_hwnd = self._window.native.Handle.ToInt32()

        # Apply saved always-on-top preference via Win32 immediately after load
        flag = _HWND_TOPMOST if self._always_on_top else _HWND_NOTOPMOST
        ctypes.windll.user32.SetWindowPos(
            self._popup_hwnd, flag, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
        )

        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            self._popup_hwnd, _GWL_EXSTYLE,
            (ex_style | _WS_EX_TOOLWINDOW | _WS_EX_LAYERED) & ~_WS_EX_APPWINDOW,
        )

        ctypes.windll.user32.SetLayeredWindowAttributes(self._popup_hwnd, 0, 0, _LWA_ALPHA)
        self._window.show()

    def _show_window(self) -> None:
        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE, ex_style & ~_WS_EX_LAYERED)
        self._shown = True
        threading.Thread(target=self._update_loop, daemon=True).start()
        threading.Thread(target=self._hotkey_watch, daemon=True).start()

    def _dismiss_watch(self) -> None:
        """Close popup on click-outside, Escape, or focus change (non-float mode only)."""
        this_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        WM_QUIT = 0x0012

        def _post_quit() -> None:
            if self._shown:
                ctypes.windll.user32.PostThreadMessageW(this_thread, WM_QUIT, 0, 0)

        _call_next = ctypes.windll.user32.CallNextHookEx
        _call_next.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
        _call_next.restype = ctypes.c_long

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [('pt', ctypes.wintypes.POINT), ('mouseData', ctypes.wintypes.DWORD),
                         ('flags', ctypes.wintypes.DWORD), ('time', ctypes.wintypes.DWORD),
                         ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        def mouse_proc(code, wparam, lparam):
            if code >= 0 and wparam == 0x0201:  # WM_LBUTTONDOWN
                if _should_stay_open():
                    return _call_next(None, code, wparam, lparam)
                popup_hwnd = self._popup_hwnd
                if popup_hwnd:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(popup_hwnd, ctypes.byref(rect))
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if not (rect.left <= info.pt.x <= rect.right and rect.top <= info.pt.y <= rect.bottom):
                        _post_quit()
            return _call_next(None, code, wparam, lparam)

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [('vkCode', ctypes.wintypes.DWORD), ('scanCode', ctypes.wintypes.DWORD),
                         ('flags', ctypes.wintypes.DWORD), ('time', ctypes.wintypes.DWORD),
                         ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        def kb_proc(code, wparam, lparam):
            if code >= 0 and wparam == 0x0100:  # WM_KEYDOWN
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.vkCode == 0x1B:  # VK_ESCAPE
                    _post_quit()
            return _call_next(None, code, wparam, lparam)

        WINEVENT_CALLBACK = ctypes.WINFUNCTYPE(
            None, ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.HWND,
            ctypes.wintypes.LONG, ctypes.wintypes.LONG, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
        )

        _fg_timer: threading.Timer | None = None

        def _should_stay_open() -> bool:
            """Return True if popup ignores focus-loss."""
            if self._force_open:
                return True
            # Always-on-top means stay open on any anchor (including tray)
            if self._always_on_top:
                return True
            return self._float_mode

        def _delayed_fg_check() -> None:
            if _should_stay_open():
                return
            popup_hwnd = self._popup_hwnd
            if not popup_hwnd or not self._shown:
                return
            fg = ctypes.windll.user32.GetForegroundWindow()
            if fg == popup_hwnd:
                return
            if ctypes.windll.user32.IsChild(popup_hwnd, fg):
                return
            if ctypes.windll.user32.GetAncestor(fg, 3) == popup_hwnd:
                return
            _post_quit()

        @WINEVENT_CALLBACK
        def fg_proc(_hook, _event, hwnd, _id_obj, _id_child, _thread, _time):
            nonlocal _fg_timer
            if _should_stay_open():
                return
            popup_hwnd = self._popup_hwnd
            if not popup_hwnd:
                return
            if ctypes.windll.user32.IsChild(popup_hwnd, hwnd):
                return
            if ctypes.windll.user32.GetAncestor(hwnd, 3) == popup_hwnd:
                return
            if _fg_timer is not None:
                _fg_timer.cancel()
            _fg_timer = threading.Timer(0.2, _delayed_fg_check)
            _fg_timer.daemon = True
            _fg_timer.start()

        mouse_hook = ctypes.windll.user32.SetWindowsHookExW(14, mouse_proc, None, 0)
        kb_hook = ctypes.windll.user32.SetWindowsHookExW(13, kb_proc, None, 0)
        fg_hook = ctypes.windll.user32.SetWinEventHook(0x0003, 0x0003, None, fg_proc, 0, 0, 0x0002)

        try:
            msg = ctypes.wintypes.MSG()
            while self._running and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            if _fg_timer is not None:
                _fg_timer.cancel()
            ctypes.windll.user32.UnhookWindowsHookEx(mouse_hook)
            ctypes.windll.user32.UnhookWindowsHookEx(kb_hook)
            ctypes.windll.user32.UnhookWinEvent(fg_hook)

        self._close()

    def _on_window_closed(self) -> None:
        self._running = False
        self._closed.set()

    def _close(self) -> None:
        self._running = False
        try:
            self._window.destroy()
        except Exception:
            pass
        self._closed.set()

    def _update_loop(self) -> None:
        cached_installations = [{'name': i.name, 'version': i.version} for i in find_installations()]
        last_next_poll_time = self.app._next_poll_time
        # Watch for hotkey close signal from app
        close_event = getattr(self.app, '_popup_close_event', None)
        while self._running:
            # Check if hotkey requested close
            if close_event and close_event.is_set():
                self._close()
                return
            time.sleep(self._CHECK_MS / 1000)
            if not self._running:
                break
            try:
                snap = self.app.cache.snapshot
                next_poll_time = self.app._next_poll_time
                if snap.version == self._last_version and next_poll_time == last_next_poll_time:
                    continue
                if snap.version != self._last_version:
                    self._last_version = snap.version
                    cached_installations = [{'name': i.name, 'version': i.version} for i in find_installations()]
                last_next_poll_time = next_poll_time
                data = _snapshot_to_dict(snap, installations=cached_installations, next_poll_time=next_poll_time)
                self._window.evaluate_js(f'updateData({json.dumps(data)})')
            except Exception:
                break

    def _hotkey_watch(self) -> None:
        """Watch for hotkey close signal — checks every 100ms so response is fast."""
        close_event = getattr(self.app, '_popup_close_event', None)
        if not close_event:
            return
        while self._running:
            if close_event.wait(timeout=0.1):
                if self._running:
                    self._close()
                return

    def _tray_position(self, physical_width: int, physical_height: int) -> tuple[int, int]:
        tray_hwnd = ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None)
        hmon = ctypes.windll.user32.MonitorFromWindow(tray_hwnd, 2)

        mon_info = _MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info))
        mon = mon_info.rcMonitor
        work = mon_info.rcWork

        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / _BASELINE_DPI

        margin = 12

        if work.left > mon.left:
            x = work.left + margin
        else:
            x = work.right - physical_width - margin

        if work.top > mon.top:
            y = work.top + margin
        else:
            y = work.bottom - physical_height - margin

        return int(x / scale), int(y / scale)

    def _anchor_position(self, physical_width: int, physical_height: int, anchor: str) -> tuple[int, int]:
        """Calculate position for a given anchor corner."""
        hmon = ctypes.windll.user32.MonitorFromWindow(
            self._popup_hwnd or ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None), 2
        )
        mon_info = _MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info))
        work = mon_info.rcWork

        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / _BASELINE_DPI
        margin = 12

        right, bottom = _ANCHOR_CORNERS.get(anchor, (True, True))

        x = (work.right - physical_width - margin) if right else (work.left + margin)
        y = (work.bottom - physical_height - margin) if bottom else (work.top + margin)

        return int(x / scale), int(y / scale)

    def _resize_and_position(self, height: int) -> None:
        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / _BASELINE_DPI
        physical_width = int(self.WIDTH * scale)
        physical_height = int(height * scale)

        # Cap height to 88% of work area so popup never exceeds screen
        hmon = ctypes.windll.user32.MonitorFromWindow(self._popup_hwnd, 2)
        mon_info = _MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info))
        work = mon_info.rcWork
        work_h = work.bottom - work.top
        work_w = work.right - work.left
        max_physical_h = int(work_h * 0.88)
        if physical_height > max_physical_h:
            physical_height = max_physical_h
            height = int(max_physical_h / scale)

        self._window.resize(self.WIDTH, height)

        if self._float_mode and self._float_x is not None and self._float_y is not None:
            self._window.move(self._float_x, self._float_y)
        elif self._anchor in _ANCHOR_CORNERS and self._anchor != 'tray':
            x, y = self._anchor_position(physical_width, physical_height, self._anchor)
            self._window.move(x, y)
        else:
            x, y = self._tray_position(physical_width, physical_height)
            self._window.move(x, y)

        # Clamp: ensure window never goes above top or below bottom of work area
        if self._popup_hwnd:
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(self._popup_hwnd, ctypes.byref(rect))
            new_x = int(rect.left / scale)
            new_y = int(rect.top  / scale)
            changed = False
            if rect.top < work.top + 8:
                new_y = int((work.top + 8) / scale)
                changed = True
            if rect.bottom > work.bottom - 8:
                new_y = int((work.bottom - physical_height - 8) / scale)
                changed = True
            if changed:
                self._window.move(new_x, new_y)
