# CookieGame — Multi-OS

**Download**: https://github.com/tetipong2542/cookiegame-multi-os/releases

| OS | ไฟล์ | วิธีใช้ |
|---|---|---|
| Windows | `cookiegame.exe` | ดับเบิลคลิก |
| macOS   | `CookieGame-macOS.zip` | unzip → ลากเข้า Applications → เปิด |

Build อัตโนมัติจาก [GitHub Actions](https://github.com/tetipong2542/cookiegame-multi-os/actions) ทุกครั้งที่ push tag `v*`

---

# Source (recovered from `cookiegame.exe`)

Python source ที่ได้จากการถอด `cookiegame.exe` (PyInstaller + Python 3.12) กลับมา
สำหรับพัฒนาต่อบน **macOS**

- ต้นฉบับ: `cookiegame.exe` (58.8 MB, PyInstaller 2.1+, Python 3.12)
- Bot ควบคุมเกม **Cookie Run** ผ่าน **LDPlayer** (Android emulator) ด้วย **ADB + OpenCV**
- GUI Tkinter (ภาษาไทย) + ระบบ License Key (ECDSA)
- Author: `gamerael`, BOT_VERSION `2`

---

## โครงสร้าง

```
cookiegame/
├── src/
│   ├── cookiegame.py     # GUI หลัก (Tkinter) — entry point
│   ├── bot.py            # State machine + ADB/OpenCV automation
│   └── license_core.py   # ระบบ License Key (ECDSA + HWID binding)
├── templates/            # ภาพ template สำหรับ OpenCV matching
│   ├── dig/              # ตัวเลข 0-9 สำหรับอ่านเหรียญบนหน้า Result
│   └── *.png             # ภาพหน้าจอเกม (lobby, ingame, result ฯลฯ)
├── disasm/               # bytecode disassembly (สำหรับดูจุดที่ decompile ไม่ครบ)
│   ├── cookiegame.disasm
│   ├── bot.disasm
│   ├── license_core.disasm
│   └── decompile_errors.log
├── requirements.txt
├── run.sh                # ตัวช่วยรันบน Mac
└── README.md
```

---

## การรันบน Mac

```sh
# 1) ติดตั้ง Python 3.12 + tkinter
brew install python@3.12 python-tk@3.12

# 2) สร้าง venv + ติดตั้ง dependencies
cd cookiegame
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) ติดตั้ง ADB (สำหรับควบคุม Android emulator/device)
brew install android-platform-tools
which adb   # ควรได้ /opt/homebrew/bin/adb

# 4) รัน GUI
python src/cookiegame.py
```

`run.sh` ทำขั้นตอน 2 + 4 ให้อัตโนมัติ

---

## สถานะ Source ที่ Decompile ได้

| ไฟล์               | บรรทัด | จุดที่ decompile ไม่ครบ | สถานะ                    |
| ------------------ | ------ | ----------------------- | ------------------------ |
| `cookiegame.py`    | 243    | 5 จุด                   | ใช้งานได้เกือบทั้งหมด    |
| `bot.py`           | 584    | 21 จุด                  | ต้องซ่อมหลายจุด           |
| `license_core.py`  | 233    | 0 จุด                   | ใช้งานได้ (แก้บั๊กเล็กน้อย)|

จุดที่ decompile ไม่ครบจะมี comment `# WARNING: Decompyle incomplete` กำกับไว้
**ต้องเปิด `disasm/*.disasm` (Python bytecode) ประกบเพื่อเขียนโค้ดเติมด้วยตัวเอง**

---

## จุดที่รู้แล้วว่าต้องซ่อม (Mac port)

### `license_core.py`
- **บรรทัด 45**: `return None.path.dirname(...)` → `return os.path.dirname(...)`
- **บรรทัด 91**: `if key_string or '.' not in key_string:` → `if not key_string or '.' not in key_string:`
- **บรรทัด 109**: `return (None, {...})` → `return (True, {...})`
- **บรรทัด 124-127**: for-loop ลบอักขระ zero-width หลุด flow — ก๊อปจาก `verify_key` (บรรทัด 88-90)
- **บรรทัด 195**: `global _run_lock_handle, _run_lock_handle, _run_lock_handle` → ประกาศ 1 ครั้งพอ
- **บรรทัด 227**: `if None != _bind_hash(...)` → `if bind != _bind_hash(...)`
- **`get_hwid()`**: ใช้ `winreg` อ่าน MachineGuid — บน Mac ให้ใช้:
  ```py
  import subprocess
  raw = subprocess.check_output(
      ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice']
  ).decode()
  # หา 'IOPlatformUUID'
  ```
- **`acquire_run_lock()` / `release_run_lock()`**: ใช้ Windows Named Mutex (kernel32) —
  บน Mac ใช้ `fcntl.flock()` บนไฟล์ lock แทน

### `bot.py`
- **บรรทัด 466**: `return None.path.dirname(...)` → `return os.path.dirname(...)`
- **บรรทัด 498**: `th[(:, x0:x1)]` → `th[:, x0:x1]`
- **บรรทัด 508**: lambda เสีย — ดู bytecode `disasm/bot.disasm` เพื่อเขียนใหม่
- **`find_adb()`**: hard-code path แบบ Windows (`D:\LDPlayer\...`) — บน Mac ให้ default:
  ```py
  _DEFAULT_ADB = '/opt/homebrew/bin/adb'  # หรือ '/usr/local/bin/adb'
  ```
- **`_NO_WINDOW`**: `subprocess.CREATE_NO_WINDOW` เป็น flag Windows เท่านั้น — โค้ดเดิมจัดการดีอยู่แล้ว
  (fallback เป็น `0` บน non-Windows)
- **21 ฟังก์ชันมี `pass` + WARNING**: ต้องเขียนตัวเนื้อฟังก์ชันเอง โดยอ้างจาก:
  - docstring ในไฟล์ (ยังอยู่ครบ)
  - `disasm/bot.disasm` (bytecode instructions)
  - ตรรกะ flow จากค่าคงที่ที่โผล่อยู่ (`BTN_*`, `IMG_*`, threshold ต่างๆ)

  ฟังก์ชันที่กระทบหลัก:
  `print()`, `_run()`, `watch_emergency_key()`, `adb_tap()`, `adb_slide()`,
  `load_template()`, `find_template()`, `find_in_roi()`, `ensure_boosts_selected()`,
  `ensure_on_boost_screen()`, `multibuy_until_target()`, `state_reroll()`,
  `state_run()`, `load_pattern()`, `_load_digit_templates()`, `_segment_digits()`,
  `read_coins()`, `record_result_coins()`, `state_result()`, `run_state_machine()`

### `cookiegame.py`
- ทั้งหมด 5 จุด (WARNING) รวม `__init__` ของ `CookieGameApp` — เนื้อ UI/logic
  ที่ decompile ได้ยังอ่านออกดี ต้องเขียน constructor, event handler ไม่กี่ตัวเพิ่ม

---

## LDPlayer บน Mac?

LDPlayer ไม่มีเวอร์ชัน macOS ทางเลือก:
- **BlueStacks Air / BlueStacks 5 for Mac** — เปิด ADB บน `localhost:5555` ได้
- **Android Studio Emulator** — ADB มากับ Android SDK
- **มือถือ Android จริง** ต่อ USB + เปิด USB debugging

หลังต่อได้แล้ว ใน GUI ให้:
- **ADB path**: `/opt/homebrew/bin/adb`
- **Device**: ผลจาก `adb devices` (เช่น `emulator-5554` หรือ `127.0.0.1:5555`)

---

## หมายเหตุเรื่อง License

`PUBLIC_KEY_HEX` ใน `license_core.py` เป็น **public key ของผู้ออก** —
ใช้ verify signature ของ key ที่ลูกค้าใส่เท่านั้น (private key ไม่ได้อยู่ในไฟล์นี้)
โครงการที่พัฒนาต่อบน Mac ยังต้องใช้ private key ตัวเดิม (เก็บไว้แยก) เพื่อออก key ใหม่

---

## ที่มาของโฟลเดอร์นี้

```sh
# 1) แตก PyInstaller archive
python3.12 pyinstxtractor.py cookiegame.exe
# ได้: cookiegame.exe_extracted/{cookiegame.pyc, PYZ.pyz_extracted/{bot.pyc, license_core.pyc, ...}}

# 2) Decompile Python 3.12 bytecode → source
pycdc cookiegame.pyc      > src/cookiegame.py
pycdc bot.pyc             > src/bot.py
pycdc license_core.pyc    > src/license_core.py

# 3) Disassemble (สำหรับดูจุดที่ decompile ไม่ครบ)
pycdas <file>.pyc         > disasm/<file>.disasm
```

Tools: [`pyinstxtractor`](https://github.com/extremecoders-re/pyinstxtractor),
[`pycdc/pycdas`](https://github.com/zrax/pycdc) (Decompyle++)
