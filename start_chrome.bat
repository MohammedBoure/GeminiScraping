@echo off
chcp 65001 >nul
echo ========================================================
echo   تشغيل Google Chrome مع تفعيل Remote Debugging Port 9222
echo ========================================================
echo.

set CHROME_BIN=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%LocalAppData%\Google\Chrome\Application\chrome.exe"
)

if "%CHROME_BIN%"=="" (
    echo [خطأ] لم يتم العثور على Google Chrome في المسارات الافتراضية.
    echo يرجى التأكد من تثبيت Chrome.
    pause
    exit /b 1
)

echo تم العثور على Chrome في:
echo "%CHROME_BIN%"
echo.
echo جاري تشغيل المتصفح... يرجى تسجيل الدخول إلى حسابك في Gemini وتركه مفتوحاً.
echo.

start "" "%CHROME_BIN%" --remote-debugging-port=9222 --user-data-dir="C:\chrome-dev-profile" "https://gemini.google.com"

echo تم تشغيل Chrome بنجاح على المنفذ 9222.
timeout /t 3 >nul
