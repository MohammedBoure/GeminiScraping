@echo off
chcp 65001 >nul
echo ========================================================
echo   تشغيل مولد الأسئلة Gemini Web Generator
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [خطأ] البيئة الافتراضية .venv غير موجودة.
    echo يرجى إنشاء البيئة الافتراضية أولاً.
    pause
    exit /b 1
)

echo جاري التحقق من تشغيل Chrome على المنفذ 9222 وتشغيل السكربت...
echo.

".venv\Scripts\python.exe" web_gemini_generator.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [تنبيه] حدث خطأ أثناء تشغيل السكربت. تأكد من فتح المتصفح عبر start_chrome.bat أولاً.
    pause
)
