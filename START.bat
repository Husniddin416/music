@echo off
chcp 65001 >nul
title MusicUz — Python/FastAPI

cd /d "%~dp0"

echo.
echo  ==============================
echo   MusicUz — Python backend
echo  ==============================
echo.

:: Python borligini tekshirish
python --version >nul 2>&1
if errorlevel 1 (
    echo [XATO] Python topilmadi!
    echo Python o'rnatish uchun: https://www.python.org/downloads/
    echo o'rnatishda "Add Python to PATH" ni belgilang!
    pause
    exit /b
)

:: Virtual muhit
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Virtual muhit yaratilmoqda...
    python -m venv .venv
)

echo [2/3] Kutubxonalar o'rnatilmoqda...
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

echo [3/3] Server ishga tushirilmoqda...
echo.
python main.py

pause
