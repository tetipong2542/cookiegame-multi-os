@echo off
REM CookieGame - Windows build script
REM ต้องมี Python 3.12 (Add to PATH) + Visual C++ Redistributable

setlocal
cd /d "%~dp0"

REM ---- setup venv ----
if not exist ".venv\Scripts\python.exe" (
    echo [setup] สร้าง virtualenv ครั้งแรก...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] สร้าง venv ไม่สำเร็จ - เช็คว่าติดตั้ง Python 3.12 + PATH หรือยัง
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM ---- install deps + PyInstaller ----
echo [setup] ติดตั้ง dependencies + PyInstaller...
python -m pip install --upgrade pip >NUL
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 (
    echo [ERROR] ติดตั้งไม่สำเร็จ
    pause
    exit /b 1
)

REM ---- clean previous build ----
if exist "build"  rmdir /s /q build
if exist "dist"   rmdir /s /q dist

REM ---- build ----
echo [build] เริ่ม build .exe...
pyinstaller --noconfirm build.spec
if errorlevel 1 (
    echo [ERROR] build ล้มเหลว
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SUCCESS
echo   ไฟล์อยู่ที่:  dist\cookiegame.exe
echo ============================================================
echo.
pause
