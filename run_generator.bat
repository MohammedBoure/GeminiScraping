@echo off
echo ========================================================
echo   Running Gemini Web Generator
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv was not found.
    pause
    exit /b 1
)

echo Starting web_gemini_generator.py...
echo.

".venv\Scripts\python.exe" web_gemini_generator.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Execution failed. Ensure Chrome is running with start_chrome.bat or start_chrome.ps1 first.
    pause
)
