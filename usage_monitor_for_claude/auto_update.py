"""
Auto Update
============

Checks GitHub releases for a newer version of ClaudeMeter.
Runs once on startup in a daemon thread — never blocks the app.

If a newer version is found:
  - Shows a Windows toast notification
  - Sets a flag so the tray menu can show an "Update available" item
"""
from __future__ import annotations

import json
import threading
import urllib.request
from typing import Callable

from . import __version__

__all__ = ['check_for_update', 'update_available', 'latest_version', 'latest_url']

# GitHub API endpoint for latest release
_GITHUB_API = 'https://api.github.com/repos/Emu-AI772/ClaudeMeter/releases/latest'
_RELEASES_URL = 'https://github.com/Emu-AI772/ClaudeMeter/releases/latest'
_TIMEOUT = 8  # seconds

# Module-level state — set after check completes
update_available: bool = False
latest_version: str = ''
latest_url: str = _RELEASES_URL


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert 'v2.0.0' or '2.0.0' to (2, 0, 0)."""
    v = v.lstrip('v').strip()
    try:
        return tuple(int(x) for x in v.split('.'))
    except Exception:
        return (0,)


def _fetch_latest() -> tuple[str, str] | None:
    """Fetch latest release info from GitHub API.

    Returns (version_str, release_url) or None on failure.
    """
    try:
        req = urllib.request.Request(
            _GITHUB_API,
            headers={
                'Accept': 'application/vnd.github+json',
                'User-Agent': f'ClaudeMeter/{__version__}',
            }
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            tag = data.get('tag_name', '')
            url = data.get('html_url', _RELEASES_URL)
            if tag:
                return tag, url
    except Exception:
        pass
    return None


def check_for_update(
    on_update_found: Callable[[str, str], None] | None = None,
) -> None:
    """Check for a newer release in a background thread.

    Parameters
    ----------
    on_update_found : callable, optional
        Called with (version, url) when a newer version is found.
        Runs in the background thread.
    """
    def _check() -> None:
        global update_available, latest_version, latest_url

        result = _fetch_latest()
        if not result:
            return

        remote_ver, remote_url = result
        current = _parse_version(__version__)
        remote   = _parse_version(remote_ver)

        if remote > current:
            update_available = True
            latest_version   = remote_ver.lstrip('v')
            latest_url       = remote_url
            if on_update_found:
                try:
                    on_update_found(latest_version, latest_url)
                except Exception:
                    pass

    threading.Thread(target=_check, daemon=True).start()
