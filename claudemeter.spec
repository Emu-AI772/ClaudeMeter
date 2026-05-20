# -*- mode: python ; coding: utf-8 -*-
# ClaudeMeter - PyInstaller build spec
# Run: pyinstaller claudemeter.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all popup HTML/CSS/JS files
popup_files = [
    ('usage_monitor_for_claude/popup/popup.html',  'usage_monitor_for_claude/popup'),
    ('usage_monitor_for_claude/popup/popup.css',   'usage_monitor_for_claude/popup'),
    ('usage_monitor_for_claude/popup/popup.js',    'usage_monitor_for_claude/popup'),
    ('usage_monitor_for_claude/popup/dev.html',    'usage_monitor_for_claude/popup'),
]

# Collect ALL non-python files from usage_monitor_for_claude (popup HTML/CSS/JS etc)
import glob
locale_files = []
for f in glob.glob('usage_monitor_for_claude/**/*', recursive=True):
    if os.path.isfile(f) and not f.endswith('.py') and not f.endswith('.pyc'):
        dest = os.path.dirname(f)
        locale_files.append((f, dest))
        print(f'  Including package file: {f} -> {dest}')

# Collect locale JSON files from project root locale/ directory
for f in glob.glob('locale/**/*.json', recursive=True):
    if os.path.isfile(f):
        dest = os.path.dirname(f)
        locale_files.append((f, dest))
        print(f'  Including locale: {f} -> {dest}')

if not any('locale' in str(f[0]) for f in locale_files):
    print('WARNING: No locale files found! Check locale/ folder exists in project root.')

a = Analysis(
    ['usage_monitor_for_claude/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=popup_files + locale_files,
    hiddenimports=[
        'usage_monitor_for_claude.splash',
        'usage_monitor_for_claude.hotkey',
        'usage_monitor_for_claude.auto_update',
        'usage_monitor_for_claude.notifications',
        'pystray._win32',
        'PIL._tkinter_finder',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'clr',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ClaudeMeter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window — tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='claudemeter.ico',
    version='version_info.txt',
)
