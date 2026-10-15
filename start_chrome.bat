@echo off
echo ========================================================
echo   Launching Google Chrome with Remote Debugging (9222)
echo ========================================================
echo.

set "CHROME_BIN="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%LocalAppData%\Google\Chrome\Application\chrome.exe"
)

if "%CHROME_BIN%"=="" (
    echo [ERROR] Google Chrome was not found in standard directories.
    echo Please make sure Google Chrome is installed.
    pause
    exit /b 1
)

echo Found Chrome at: "%CHROME_BIN%"
echo Starting browser with remote debugging on port 9222...

start "" "%CHROME_BIN%" --remote-debugging-port=9222 --user-data-dir="C:\chrome-dev-profile" "https://gemini.google.com"

echo.
echo [OK] Chrome launched. Please keep the window open and make sure you are signed into Gemini.
