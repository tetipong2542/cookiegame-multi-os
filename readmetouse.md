# CookieGame — คู่มือทดสอบ (Demo)

รอบทดสอบนี้เป็น **โหมด demo**
> ไม่ต้องใส่ license key จริง — ใส่อะไรก็ผ่าน หรือกดเริ่มเลยได้เลย

---

## Phase 1 — Windows + LDPlayer (รอบแรก)

### 🎯 สิ่งที่จะทดสอบในรอบนี้

1. GUI เปิดได้/แสดงผลถูกต้อง
2. ADB เชื่อมต่อ LDPlayer ได้
3. ปุ่มเริ่ม/หยุดตอบสนอง
4. Log แสดงการทำงานแบบเรียลไทม์

> ⚠️ ฟังก์ชันเล่นบอทเต็มรูปแบบ (state machine, image matching, multi-buy)
> ยังมี 26 จุดที่ decompile ไม่ครบ ต้องซ่อมก่อน — รอบนี้ทดสอบ flow ก่อน

---

### 1) เตรียมเครื่อง (ทำครั้งเดียว)

**a. ติดตั้ง LDPlayer**
- โหลดจาก: <https://www.ldplayer.net/>
- แนะนำ LDPlayer 9 หรือ LDPlayer 14 (path default ใน bot คือ `D:\LDPlayer\LDPlayer14\adb.exe`)
- เปิด LDPlayer → โหลดเกม Cookie Run → login ให้เรียบร้อย

**b. ติดตั้ง Python 3.12 (ถ้ายังไม่มี)**
- โหลด: <https://www.python.org/downloads/windows/>
- ตอนติดตั้ง **ต้อง tick ช่อง `Add python.exe to PATH`** ✅
- ตรวจ: เปิด `cmd` แล้วพิมพ์ `python --version` ต้องขึ้น `Python 3.12.x`

**c. ตรวจ ADB**
- ADB ของ LDPlayer อยู่ที่ `D:\LDPlayer\LDPlayer14\adb.exe` (หรือใน folder ที่ติดตั้ง LDPlayer)
- ถ้าติดตั้ง LDPlayer ที่ path อื่น — จำ path ไว้ ใช้กรอกในแอป

---

### 2) รันแอป (วิธี Best Practice)

เปิด **Command Prompt** (ไม่ใช่ PowerShell — บาง venv activate ไม่ทำงาน) แล้ว:

```cmd
:: ไปที่โฟลเดอร์ cookiegame
cd path\to\cookiegame

:: สร้าง virtual environment (ครั้งแรกเท่านั้น)
python -m venv .venv

:: activate venv
.venv\Scripts\activate

:: ติดตั้ง dependencies (ครั้งแรกเท่านั้น)
pip install -r requirements.txt

:: รันแอป
cd src
python cookiegame.py
```

รอบต่อไปแค่:
```cmd
cd path\to\cookiegame
.venv\Scripts\activate
cd src
python cookiegame.py
```

**หรือถ้าอยากให้ง่ายกว่านั้น** — สร้างไฟล์ `run.bat` ในโฟลเดอร์ cookiegame:
```bat
@echo off
cd /d "%~dp0"
if not exist ".venv" (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
cd src
python cookiegame.py
pause
```
ดับเบิลคลิก `run.bat` ก็รันได้เลย

---

### 3) เริ่มทดสอบ

1. เปิด LDPlayer → เข้าเกม Cookie Run → หน้าล็อบบี้
2. เปิดแอป CookieGame (`python cookiegame.py` หรือ `run.bat`)
3. **License key**: ปล่อยว่าง หรือใส่คำว่า `demo` ก็ได้ → กดปุ่ม `ใช้งาน key`
   - ควรขึ้น: `✅ License: ถาวร` หรือ `Demo mode`
4. **ADB path**: กด `หาอัตโนมัติ` → ถ้าไม่เจอ → กรอก path ADB ของ LDPlayer เอง เช่น
   ```
   D:\LDPlayer\LDPlayer14\adb.exe
   ```
5. **Device**: default = `emulator-5554` (ใช้ได้กับ LDPlayer 1 instance)
   - ถ้าเปิดหลาย instance → กด `ทดสอบเชื่อมต่อ` เพื่อดู device ID จริง
6. **จำนวนรอบ**: 0 = ไม่จำกัด / ใส่เลขก็หยุดตามจำนวนรอบ
7. กดปุ่ม **▶ เริ่มบอท** → ดู log ที่ด้านล่าง
8. กด **■ หยุด** เมื่อต้องการหยุด (หรือปุ่ม `q` บน keyboard)

---

### 4) รายงานผลการทดสอบ

รบกวนช่วยเช็คและรายงานกลับ:

- [ ] แอปเปิดได้ปกติหรือไม่
- [ ] License แสดงว่าใช้งานได้หรือไม่ (ต้องขึ้น ✅ สีเขียว)
- [ ] `หาอัตโนมัติ` เจอ ADB ไหม (ถ้าไม่เจอ — แจ้ง path ที่ติดตั้ง LDPlayer)
- [ ] `ทดสอบเชื่อมต่อ` ผ่านไหม
- [ ] Log ขึ้นเวลาเริ่มบอท
- [ ] ปุ่มหยุดใช้งานได้

**Screenshot** GUI + Log ที่แสดง error (ถ้ามี) จะช่วยแก้เร็วขึ้นมาก

---

### 🔧 Troubleshooting

| ปัญหา | สาเหตุ / วิธีแก้ |
|---|---|
| `'python' is not recognized` | ตอนติดตั้ง Python ไม่ได้ tick `Add to PATH` → reinstall แล้ว tick |
| `ModuleNotFoundError: No module named 'cv2'` | ไม่ได้ activate venv หรือยังไม่ได้ `pip install -r requirements.txt` |
| `_tkinter.TclError: no display name` | ระบบไม่มี GUI runtime — ใช้ Windows ปกติไม่น่าเจอ |
| `[FATAL] เชื่อมต่อ ADB/แคปหน้าจอไม่ได้` | LDPlayer ยังไม่เปิด / ADB path ผิด / device ID ผิด (`adb devices` เช็คก่อน) |
| แอปเปิดแล้วปิดทันที | รันจาก cmd แทน double-click จะเห็น error — copy มาแจ้ง |
| ปุ่มเริ่มบอทกดแล้วไม่ทำอะไร | คือ **สถานะปกติของรอบนี้** — ฟังก์ชัน state machine ยัง decompile ไม่ครบ ต้องซ่อมก่อน |

---

## Phase 2 — Mac (รอบถัดไป)

จะรองรับ Mac หลัง Phase 1 ผ่านการทดสอบแล้ว
รายละเอียดที่ต้องทำอยู่ใน [README.md](README.md)

สรุปสั้น ๆ:
- LDPlayer ไม่มีบน Mac → ต้องเปลี่ยนเป็น Genymotion / BlueStacks Air / มือถือจริง
- `winreg` (HWID) ต้องเปลี่ยนเป็น `ioreg`
- `keyboard` library ต้องเปลี่ยนเป็น `pynput` (หรือ Tkinter binding)
- ADB path เปลี่ยนเป็น `/opt/homebrew/bin/adb`

---

## สำหรับ dev — สร้าง .exe demo แจกให้ tester

ถ้าอยากแจก .exe ให้ tester ไม่ต้องติดตั้ง Python — build ด้วย PyInstaller บน **Windows**:

```cmd
:: ที่โฟลเดอร์ cookiegame
.venv\Scripts\activate
pip install pyinstaller
cd src

pyinstaller cookiegame.py ^
  --onefile ^
  --windowed ^
  --name cookiegame_demo ^
  --add-data "..\templates;templates" ^
  --hidden-import bot ^
  --hidden-import license_core

:: ผลลัพธ์อยู่ที่  src\dist\cookiegame_demo.exe
```

แจก `cookiegame_demo.exe` ให้ tester ใช้ได้เลย ไม่ต้องติดตั้งอะไรเพิ่ม
(ต้องมี LDPlayer เท่านั้น)
