# Source Generated with Decompyle++
# File: license_core.pyc (Python 3.12)

'''
ระบบ License Key (ECDSA) — ฝั่งบอท (แบบ activate-on-first-use)
- ลูกค้าแค่วาง key -> โปรแกรมล็อก key กับเครื่องนี้เองตอนใช้ครั้งแรก (ไม่ต้องส่ง HWID)
- หลังล็อกแล้ว ก๊อป license.key ไปเครื่องอื่นใช้ไม่ได้ (HWID ไม่ตรง)
- รองรับ key เช่า (มีวันหมดอายุ) และ ถาวร
'''
import os
import sys
import json
import base64
import hashlib
from datetime import date
import ecdsa
PUBLIC_KEY_HEX = 'f2c7836e980d03286b4641db41bce4cf40c6f24530dc1240905be93f4dc0be25bb68844c52a52d6f5adb80c52a320d813d7459c0908dab779d57bc6aec95bea2'
_SALT = 'cg-bind-v1-7Hq2pLx9'

def get_hwid():
    '''รหัสเครื่อง (สั้น) — อิง Windows MachineGuid (คงที่ต่อการลง Windows 1 ครั้ง)'''
    raw = ''
    
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Microsoft\\Cryptography')
        raw = winreg.QueryValueEx(k, 'MachineGuid')[0]
        winreg.CloseKey(k)
        h = hashlib.sha256(('cookiegame|' + raw).encode()).hexdigest().upper()
        return '-'.join([
            h[0:4],
            h[4:8],
            h[8:12],
            h[12:16]])
    except Exception:
        import uuid
        raw = str(uuid.getnode())
        continue



def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return None.path.dirname(os.path.abspath(__file__))


def _license_file():
    return os.path.join(_base_dir(), 'license.key')


def _state_path():
    return os.path.join(_base_dir(), '.cg_state')


def _bind_hash(key_string, hwid):
    return hashlib.sha256((key_string + '|' + hwid + '|' + _SALT).encode()).hexdigest()


def _clock_ok():
    '''กันหมุนนาฬิกาเครื่องย้อนหลัง (สำหรับ key เช่า)'''
    today = date.today().isoformat()
    p = _state_path()
    
    try:
        last = open(p, encoding = 'utf-8').read().strip() if os.path.exists(p) else ''
        if last and today < last:
            return False
            
            try:
                if today >= last:
                    open(p, 'w', encoding = 'utf-8').write(today)
                return True
            except Exception:
                return True




def verify_key(key_string):
    '''
    ตรวจ "ลายเซ็น + ประเภท + วันหมดอายุ" ของ key (ยังไม่ผูกเครื่อง)
    คืน (ok: bool, info: dict | str)
    '''
    if not key_string:
        key_string
    key_string = ''
    for ch in ('﻿', '\r', '\n', '\t', ' ', '​', '\xc2\xa0'):
        key_string = key_string.replace(ch, '')
    key_string = key_string.strip()
    if key_string or '.' not in key_string:
        return (False, 'รูปแบบ key ไม่ถูกต้อง')
    
    try:
        (msg_b64, sig_b64) = key_string.split('.', 1)
        msg = base64.urlsafe_b64decode(msg_b64 + '==')
        sig = base64.urlsafe_b64decode(sig_b64 + '==')
        vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(PUBLIC_KEY_HEX), curve = ecdsa.NIST256p)
        vk.verify(sig, msg)
        data = json.loads(msg.decode())
        if data.get('type') == 'rental':
            exp = data.get('exp')
            if not exp:
                return (False, 'key เช่าไม่มีวันหมดอายุ')
            if not _clock_ok():
                return (False, 'ตรวจพบการตั้งเวลาเครื่องผิดปกติ')
            if date.today().isoformat() > exp:
                return (False, f'''key หมดอายุแล้ว (หมด {exp})''')
            return (None, {
                'type': data.get('type'),
                'exp': data.get('exp'),
                'id': data.get('id', ''),
                'name': data.get('name', '') })
        except Exception:
            return (False, 'key ไม่ถูกต้อง (ลายเซ็นไม่ผ่าน)')



def activate(key_string):
    '''ใช้งาน key ครั้งแรก: ตรวจ key แล้วล็อกกับเครื่องนี้ (เซฟ license.key) — ไม่ต้องใช้ HWID จากภายนอก'''
    (ok, info) = verify_key(key_string)
    if not ok:
        return (False, info)
    for ch in None:
        key_string = key_string.replace(ch, '')
    key_string = key_string.strip()
    hwid = get_hwid()
    rec = {
        'key': key_string,
        'bind': _bind_hash(key_string, hwid) }
    
    try:
        open(_license_file(), 'w', encoding = 'utf-8').write(json.dumps(rec))
        return (True, info)
    except Exception:
        return (True, info)


_run_lock_handle = None

def _run_lock_name(key_string):
    h = hashlib.sha256((key_string + '|run|' + _SALT).encode()).hexdigest()[:40]
    return 'cookiegame_run_' + h


def acquire_run_lock():
    """จองสิทธิ์ 'กำลังรัน' ของคีย์นี้. คืน True = เริ่มได้ / False = คีย์นี้กำลังรันอยู่บนอีกจอ"""
    global _run_lock_handle
    if _run_lock_handle:
        return True
    if os.name != 'nt':
        return True
    
    try:
        key = json.loads(open(_license_file(), encoding = 'utf-8').read()).get('key', '')
        if not key:
            return True
        
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CreateMutexW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_bool,
                ctypes.c_wchar_p]
            k32.CloseHandle.argtypes = [
                ctypes.c_void_p]
            handle = k32.CreateMutexW(None, False, _run_lock_name(key))
            err = k32.GetLastError()
            if not handle:
                return True
                
                try:
                    if err == 183:
                        k32.CloseHandle(handle)
                        return False
                        
                        try:
                            _run_lock_handle = handle
                            return True
                            except Exception:
                                key = ''
                                continue
                        except Exception:
                            return True






def release_run_lock():
    '''ปล่อยสิทธิ์รัน (เรียกตอนบอทหยุด/ปิดโปรแกรม) — เอาคีย์ไปใช้จออื่นต่อได้'''
    global _run_lock_handle, _run_lock_handle, _run_lock_handle
    if _run_lock_handle and os.name == 'nt':
        
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.CloseHandle.argtypes = [
                ctypes.c_void_p]
            k32.CloseHandle(_run_lock_handle)
            _run_lock_handle = None
            return None
            _run_lock_handle = None
            return None
        except Exception:
            _run_lock_handle = None
            return None



def check_license():
    '''ตรวจ license ที่ล็อกไว้กับเครื่องนี้ (เรียกตอนเปิดโปรแกรม/ก่อนเริ่มบอท). คืน (ok, info|str)'''
    p = _license_file()
    if not os.path.exists(p):
        return (False, 'ยังไม่ได้ใช้งาน key')
    
    try:
        rec = json.loads(open(p, encoding = 'utf-8').read())
        key = rec.get('key', '')
        bind = rec.get('bind', '')
        (ok, info) = verify_key(key)
        if not ok:
            return (False, info)
        if None != _bind_hash(key, get_hwid()):
            return (False, 'key นี้ถูกใช้งานบนเครื่องอื่น (ย้ายเครื่องไม่ได้)')
        return (True, info)
    except Exception:
        return (False, 'ไฟล์ license เสียหาย')


