"""
license_core.py — DEMO STUB (สำหรับผู้ใช้กลุ่มทดสอบรอบแรก)
===========================================================
ถอดระบบ license จริงออก — ทุก key ผ่านหมด (หรือไม่ใส่ key ก็ได้)

ต้นฉบับ ECDSA + HWID lock อยู่ที่:  license_core.original.py
เมื่อพร้อมเปิดขาย ให้กลับไปใช้ไฟล์นั้น + ซ่อมส่วน decompile ที่ยังไม่ครบ
"""
import platform
import sys

DEMO_TYPE = 'demo'
DEMO_EXPIRY = 'unlimited'


def get_hwid():
    try:
        return f"DEMO-{platform.node() or 'anon'}-{sys.platform}"
    except Exception:
        return "DEMO-UNKNOWN"


def _demo_ok():
    return True, {
        'type': DEMO_TYPE,
        'exp': DEMO_EXPIRY,
        'message': 'Demo mode — ไม่มีการตรวจ license',
    }


def check_license():
    """เรียกตอนเปิดแอป — โหมด demo ผ่านเสมอ"""
    return _demo_ok()


def verify_key(key_string):
    return _demo_ok()


def activate(key_string):
    """เรียกตอนกดปุ่ม 'ใช้งาน key' — โหมด demo ผ่านเสมอ (key ว่างก็ผ่าน)"""
    return _demo_ok()


def acquire_run_lock():
    """เรียกตอนกดเริ่มบอท — โหมด demo ไม่ล็อก"""
    return True


def release_run_lock():
    """เรียกตอนบอทหยุด — โหมด demo ไม่ต้องทำอะไร"""
    return None
