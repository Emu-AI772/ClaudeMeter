@echo off
title ClaudeMeter - Build Installer
echo ============================================
echo  ClaudeMeter Installer Builder
echo ============================================
echo.

:: Always run from the installer\ subfolder
cd /d "%~dp0"
echo Working directory: %CD%
echo.

:: ── Find Inno Setup ISCC.exe ──────────────────────────────────────────
set "ISCC="

if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    goto :found_iscc
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
    goto :found_iscc
)
if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    goto :found_iscc
)

where ISCC.exe >nul 2>&1
if not errorlevel 1 (
    set "ISCC=ISCC.exe"
    goto :found_iscc
)

echo ERROR: Inno Setup compiler (ISCC.exe) not found.
echo.
echo Checked:
echo   C:\Program Files (x86)\Inno Setup 6\ISCC.exe
echo   C:\Program Files\Inno Setup 6\ISCC.exe
echo.
echo Please install Inno Setup 6 from:
echo   https://jrsoftware.org/isinfo.php
echo.
pause
exit /b 1

:found_iscc
echo Found Inno Setup: %ISCC%
echo.

:: ── Check ClaudeMeter.exe was built ───────────────────────────────────
set "DIST_EXE=%~dp0..\dist\ClaudeMeter.exe"

if not exist "%DIST_EXE%" (
    echo ERROR: ClaudeMeter.exe not found.
    echo Expected: %DIST_EXE%
    echo.
    echo Please run build.bat from the project root first.
    echo.
    pause
    exit /b 1
)
echo Found: %DIST_EXE%
echo.

:: ── Check .iss file exists ────────────────────────────────────────────
if not exist "%~dp0claudemeter.iss" (
    echo ERROR: claudemeter.iss not found in %~dp0
    pause
    exit /b 1
)

:: ── Create output directory ───────────────────────────────────────────
set "OUT_DIR=%~dp0..\installer_output"
if not exist "%OUT_DIR%" (
    mkdir "%OUT_DIR%"
    echo Created output folder: %OUT_DIR%
)

:: ── Run Inno Setup ────────────────────────────────────────────────────
echo Building installer...
echo.
"%ISCC%" "%~dp0claudemeter.iss"

if errorlevel 1 (
    echo.
    echo ============================================
    echo  BUILD FAILED
    echo ============================================
    echo Check the output above for error details.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  SUCCESS!
echo ============================================
echo.
echo Installer created:
echo   %OUT_DIR%\ClaudeMeterSetup_v2.0.0.exe
echo.
echo Ready to distribute!
echo.
pause
