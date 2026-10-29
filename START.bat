@echo off
chcp 65001 >nul
title MusicUz server
cd /d "%~dp0"

echo ========================================================
echo               MusicUz — Serverni ishga tushirish
echo ========================================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [X] Xatolik: Node.js o'rnatilmagan!
  echo     Iltimos, Node.js ni o'rnating va qayta urinib ko'ring.
  echo.
  pause
  exit /b
)

if not exist "node_modules\express" (
  echo [1/2] Kerakli kutubxonalar o'rnatilmoqda (npm install)...
  echo       Biroz kuting...
  echo.
  call npm install
  if errorlevel 1 (
    echo.
    echo [X] npm install da xatolik yuz berdi!
    pause
    exit /b
  )
)

echo.
echo [2/2] Server ishga tushirilmoqda...
echo       Bu qora oynani YOPMANG!
echo ========================================================
echo.

start "" http://localhost:3000
node server/index.js

if errorlevel 1 (
  echo.
  echo [X] Server to'xtadi!
  pause
)
