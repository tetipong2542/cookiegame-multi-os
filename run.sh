#!/usr/bin/env bash
# CookieGame launcher for macOS
# Usage: ./run.sh

set -e
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3.12}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "❌ ไม่พบ $PYTHON — ติดตั้งด้วย: brew install python@3.12 python-tk@3.12"
    exit 1
fi

if [ ! -d .venv ]; then
    echo "📦 สร้าง virtualenv (.venv)..."
    "$PYTHON" -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -r requirements.txt
else
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

if ! command -v adb >/dev/null 2>&1; then
    echo "⚠️  ไม่พบ adb — ติดตั้งด้วย: brew install android-platform-tools"
fi

echo "🍪 เปิด CookieGame..."
exec python src/cookiegame.py "$@"
