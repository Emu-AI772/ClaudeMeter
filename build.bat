@echo off
title ClaudeMeter - Build
echo ============================================
echo  ClaudeMeter Build Script
echo ============================================
echo.

:: Check we're in the right folder
if not exist "usage_monitor_for_claude\__main__.py" (
    echo ERROR: Run this script from the project root folder.
    echo Expected: usage-monitor-for-claude-main\
    pause
    exit /b 1
)

:: Activate venv
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run: python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

:: Install/upgrade PyInstaller
echo [1/4] Installing PyInstaller...
pip install pyinstaller --quiet --upgrade
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

:: Check icon exists
if not exist "claudemeter.ico" (
    echo WARNING: claudemeter.ico not found - EXE will use default icon.
    echo          Copy claudemeter.ico to the project root to include it.
)

:: Clean previous build
echo [2/4] Cleaning previous build...
if exist "dist\ClaudeMeter.exe" del /f /q "dist\ClaudeMeter.exe"
if exist "build\ClaudeMeter" rmdir /s /q "build\ClaudeMeter"

:: Build
echo [3/4] Building ClaudeMeter.exe...
pyinstaller claudemeter.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Check output above for details.
    pause
    exit /b 1
)

:: Verify
if not exist "dist\ClaudeMeter.exe" (
    echo ERROR: Build completed but EXE not found in dist\
    pause
    exit /b 1
)

echo [4/4] Build complete!
echo.
echo Output: %CD%\dist\ClaudeMeter.exe
echo.
echo Next step: Run installer\build_installer.bat to create the setup EXE.
echo            Or test directly: dist\ClaudeMeter.exe
echo.
pause
