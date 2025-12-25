@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

echo ========================================
echo   Veterans-Verify Chrome DevTools
echo   MCP 专用调试实例（持久化配置）
echo ========================================
echo.

set "PORT=9222"
REM 使用默认 Chrome 配置（保留代理插件等）
set "USER_DATA_DIR=%USERPROFILE%\AppData\Local\Google\Chrome\User Data"
set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME_EXE%" set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME_EXE%" (
    echo [错误] 未找到 Chrome 浏览器
    pause
    exit /b 1
)

if not exist "%USER_DATA_DIR%" (
    echo [提示] 创建数据目录: "%USER_DATA_DIR%"
    mkdir "%USER_DATA_DIR%" >nul 2>&1
)

echo [配置] Chrome: "%CHROME_EXE%"
echo [配置] 数据目录: "%USER_DATA_DIR%"
echo [配置] 调试端口: http://127.0.0.1:%PORT%
echo.
echo ----------------------------------------
echo   用途：开发调试，记录页面选择器
echo   注意：实际批量执行用 Camoufox
echo ----------------------------------------
echo.

REM 检查端口
netstat -ano | findstr ":%PORT%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [提示] Chrome 已在运行，端口 %PORT%
    echo        直接使用 Claude Code 连接即可
    pause
    exit /b 0
)

echo 启动 Chrome...
start "" "%CHROME_EXE%" ^
    --remote-debugging-address=127.0.0.1 ^
    --remote-debugging-port=%PORT% ^
    --user-data-dir="%USER_DATA_DIR%" ^
    --no-first-run ^
    "about:blank"

timeout /t 2 /nobreak >nul
echo.
echo Chrome 已启动！现在可以用 Claude Code 了
pause
endlocal
