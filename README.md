# ClaudeMeter

A Windows system tray application that monitors your Claude API usage in real-time.

![ClaudeMeter](https://img.shields.io/badge/version-2.0.0-orange)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- 🟠 **System tray icon** with live usage percentage and coloured bars
- 📊 **Three display modes** — Basic bars, Dials, and LED column view
- 📈 **Usage history** with 24h sparkline charts and CSV export
- 🔔 **Toast notifications** at configurable usage thresholds
- ⌨️ **Global hotkey** — Ctrl+Shift+C to open/close from anywhere
- 🎨 **Five colour themes** — Default (Claude orange), System, Traffic, Neon, Minimal
- 🖼️ **Custom RGB colour picker** for full personalisation
- 📅 **Daily usage summary** written to log automatically
- 🪟 **Compact mode** showing only key metrics
- 📌 **Anchor/float modes** — dock to any corner or drag freely
- 🚀 **Splash screen** on startup
- 🔄 **Start with Windows** toggle
- 🌗 **Auto dark/light theme** following Windows system setting

## Requirements

- Windows 10 or 11
- Microsoft Edge WebView2 Runtime (included with Windows 10/11)
- Claude Code CLI installed and logged in (for authentication)

## Installation

1. Download `ClaudeMeterSetup_v2.0.0.exe` from the [Releases](https://github.com/Emu-AI772/ClaudeMeter/releases) page
2. Run the installer
3. ClaudeMeter will appear in your system tray

## Authentication

ClaudeMeter uses the OAuth token stored by Claude Code CLI. You need to:

1. Install [Claude Code](https://claude.ai/download)
2. Run `claude` in a terminal and log in
3. ClaudeMeter will authenticate automatically

## Usage

- **Left-click** tray icon — open usage popup
- **Right-click** tray icon — menu (About, Restart, Quit)
- **Ctrl+Shift+C** — toggle popup open/close from anywhere
- **⚙️ gear icon** — settings (themes, notifications, window position)
- **— button** — compact/minimal view

## Log Files

Usage history and daily summaries are stored in:
```
C:\Users\<username>\.claude\usage-monitor-logs\
```

- `usage-monitor-history.csv` — 30-minute snapshots
- `claudemeter-daily-summary.csv` — daily peak and average per metric

## Building from Source

```bash
git clone https://github.com/Emu-AI772/ClaudeMeter.git
cd ClaudeMeter
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m usage_monitor_for_claude
```

To build the installer:
```bash
build.bat
cd installer
build_installer.bat
```

## Credits

Built on [usage-monitor-for-claude](https://github.com/jens-duttke/usage-monitor-for-claude)
by [jens-duttke](https://github.com/jens-duttke) (v1.15.1).

Extended and repackaged as ClaudeMeter by Wayne O ([@Emu-AI772](https://github.com/Emu-AI772)).

## License

MIT License — see [LICENSE](LICENSE) for details.
