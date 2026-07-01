# -*- mode: python ; coding: utf-8 -*-
# CookieGame - PyInstaller spec (cross-platform)
#   macOS    -> dist/CookieGame.app
#   Windows  -> dist/cookiegame.exe   (single-file, windowed)
#   Linux    -> dist/cookiegame       (single-file)
#
# ใช้งาน:  pyinstaller --noconfirm build.spec

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
IS_MAC = sys.platform == 'darwin'
IS_WIN = sys.platform == 'win32'

hidden = [
    'keyboard',
    'ecdsa',
]
hidden += collect_submodules('cv2')

a = Analysis(
    ['src/cookiegame.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('templates', 'templates'),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='cookiegame',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not IS_MAC,               # UPX เสีย code-sign บน Mac
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                # windowed app (ไม่มี terminal)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                    # ใส่ path .ico / .icns ตรงนี้ถ้ามี
)

if IS_MAC:
    app = BUNDLE(
        exe,
        name='CookieGame.app',
        icon=None,
        bundle_identifier='com.gamerael.cookiegame',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '11.0',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
        },
    )
