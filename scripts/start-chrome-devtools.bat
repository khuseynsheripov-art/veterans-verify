@echo off

echo ========================================
echo   Chrome MCP - Port 9488
echo   Fixed profile: veterans-chrome-profile
echo ========================================
echo.

set PORT=9488
set USER_DATA=C:\temp\codex-chrome-profile
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"

echo [!] Will close all Chrome windows first
echo.
pause

echo [1] Killing Chrome...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 >nul

echo [2] Creating profile dir if not exists...
if not exist "%USER_DATA%" mkdir "%USER_DATA%"

echo [3] Starting Chrome...
echo     Port: %PORT%
echo     Profile: %USER_DATA%
echo.

start "" %CHROME% --remote-debugging-address=127.0.0.1 --remote-debugging-port=%PORT% --user-data-dir="%USER_DATA%"

timeout /t 3 >nul

echo.
echo ========================================
echo   Done! Debug port: http://127.0.0.1:%PORT%
echo   Profile saved to: %USER_DATA%
echo ========================================
echo.
echo   Extensions/logins will persist in this profile!
echo   Next: Restart Claude Code
echo.
pause
