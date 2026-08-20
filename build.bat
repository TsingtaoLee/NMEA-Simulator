@echo off
chcp 65001 >nul
echo ============================================
echo   NMEA Simulator - EXE Build Script
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Installing dependencies...
pip install pyinstaller -q
pip install -r requirements.txt -q
echo Dependencies installed.
echo.

echo [2/3] Cleaning old build...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo Cleaned.
echo.

echo [3/3] Building EXE...
pyinstaller build.spec --noconfirm
echo.

if exist "dist\NMEA-Simulator.exe" (
    echo ============================================
    echo   Build successful!
    echo   Output: dist\NMEA-Simulator.exe
    echo ============================================
    echo.
    echo Note: The database file nmea_sim.db will be
    echo created next to the EXE on first run.
) else (
    echo Build FAILED - check errors above.
)

pause
