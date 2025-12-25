@echo off
chcp 65001 >nul

echo ========================================
echo   Chrome MCP - Port 9222
echo   Profile: chrome-devtools-mcp
echo ========================================
echo.

set PORT=9222
set USER_DATA=C:\Users\asus\AppData\Local\Google\Chrome\User Data
set PROFILE=chrome-devtools-mcp
set CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe

echo [!] This will close ALL Chrome windows.
echo.
pause

echo [1] Killing all Chrome...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 3 >nul

echo [2] Starting Chrome...
echo     Port: %PORT%
echo     Profile: %PROFILE%
echo.

start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%USER_DATA%" --profile-directory="%PROFILE%" about:blank

timeout /t 5 >nul

echo.
echo ========================================
echo   Done! Port %PORT% ready.
echo ========================================
pause
