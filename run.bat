@echo off
REM Windows launcher for CookieGame (demo build)
REM ต้องมี Python 3.12 ติดตั้งพร้อม "Add to PATH" ก่อน

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [setup] สร้าง virtualenv ครั้งแรก...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] สร้าง venv ไม่สำเร็จ - เช็คว่าติดตั้ง Python 3.12 พร้อม PATH หรือยัง
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] ติดตั้ง dependencies ไม่สำเร็จ
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
)

cd src
python cookiegame.py
if errorlevel 1 pause
