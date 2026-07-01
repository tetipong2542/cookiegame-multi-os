# Source Generated with Decompyle++
# File: bot.pyc (Python 3.12)

"""
LDPlayer Game Bot - State Machine
=================================
บอทอัตโนมัติสำหรับรันบน Emulator (LDPlayer) ผ่าน ADB + OpenCV

โครงสร้างการทำงาน 3 สถานะ (State Machine):
  STATE 1 (REROLL) : สุ่มไอเทมจนกว่าจะเจอไอเทมที่ต้องการ แล้วกด Play
  STATE 2 (RUN)    : รันคำสั่งตามเวลา (Time-based Macro) จนกว่าจะเจอหน้าผลลัพธ์
  STATE 3 (RESULT) : กดปุ่ม OK เพื่อกลับล็อบบี้ แล้ววนกลับไป STATE 1

ปุ่มฉุกเฉิน: กด 'q' เพื่อหยุดสคริปต์ทันที (ทำงานได้แม้โฟกัสอยู่หน้าต่างอื่น)

ต้องติดตั้งก่อนใช้งาน:
    pip install opencv-python numpy keyboard
"""
import subprocess
import os
import time
import sys
import random
import threading
import datetime
import json
import traceback
from enum import Enum, auto
import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

LOG_CALLBACK = None
_builtin_print = print


def print(*args, **kwargs):
    # TODO: verify against disasm — reconstructed with best effort
    try:
        text = ' '.join(str(a) for a in args) + kwargs.get('end', '\n')
    except Exception:
        text = ''
    try:
        _builtin_print(*args, **kwargs)
    except Exception:
        pass
    cb = LOG_CALLBACK
    if cb is not None:
        try:
            cb(text)
        except Exception:
            pass


def resource_path(rel):
    '''คืน path ของไฟล์ที่ bundle มากับ .exe (PyInstaller) หรือโฟลเดอร์ของสคริปต์'''
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0


def _run(cmd, **kw):
    '''
    เรียก subprocess.run โดยซ่อนหน้าต่าง console
    *** สำคัญ: redirect stdout/stderr เสมอ ไม่งั้นตอน build เป็น .exe แบบ windowed
        (ไม่มี console) คำสั่งที่ไม่ได้ระบุ stdout จะล้มเหลว (handle ไม่ valid) ***
    '''
    kw.setdefault('stdin', subprocess.DEVNULL)
    kw.setdefault('stdout', subprocess.DEVNULL)
    kw.setdefault('stderr', subprocess.DEVNULL)
    if _NO_WINDOW:
        kw.setdefault('creationflags', _NO_WINDOW)
    return subprocess.run(cmd, **kw)

_IS_WIN = sys.platform == 'win32'
_IS_MAC = sys.platform == 'darwin'
_ADB_EXE = 'adb.exe' if _IS_WIN else 'adb'

if _IS_WIN:
    _DEFAULT_ADB = 'D:\\LDPlayer\\LDPlayer14\\adb.exe'
elif _IS_MAC:
    _DEFAULT_ADB = '/opt/homebrew/bin/adb'
else:
    _DEFAULT_ADB = '/usr/bin/adb'


def find_adb():
    '''หา adb อัตโนมัติ:
       Windows -> ตำแหน่ง LDPlayer ที่พบบ่อย -> adb ใน PATH
       Mac     -> Homebrew (arm/intel) -> Android SDK -> adb ใน PATH
    '''
    cands = [_DEFAULT_ADB]
    if _IS_WIN:
        roots = [
            'D:\\LDPlayer',
            'C:\\LDPlayer',
            'E:\\LDPlayer',
            'C:\\Program Files\\LDPlayer',
            'C:\\Program Files (x86)\\LDPlayer',
            'D:\\Program Files\\LDPlayer',
            'C:\\ChangZhi',
            'D:\\ChangZhi',
        ]
        subs = ['LDPlayer14', 'LDPlayer9', 'LDPlayer64', 'LDPlayer4', '']
        for r in roots:
            for s in subs:
                cands.append(os.path.join(r, s, 'adb.exe'))
    elif _IS_MAC:
        home = os.path.expanduser('~')
        cands.extend([
            '/opt/homebrew/bin/adb',
            '/usr/local/bin/adb',
            os.path.join(home, 'Library/Android/sdk/platform-tools/adb'),
            '/Applications/Android Studio.app/Contents/plugins/android/lib/platform-tools/adb',
        ])
    else:
        cands.extend([
            '/usr/bin/adb',
            '/usr/local/bin/adb',
            os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
        ])
    cands.append(_ADB_EXE)
    for c in cands:
        if c == _ADB_EXE or os.path.exists(c):
            return c
    return _DEFAULT_ADB

ADB_PATH = find_adb()
ADB_DEVICE = 'emulator-5554'
BOT_VERSION = '2'
PREVENT_INACTIVE = BOT_VERSION == '2.1'
try:
    from detector import ObstacleDetector, load_config as _load_detector_config
    _HAS_DETECTOR = True
except ImportError as _e:
    print(f'[detector] import failed: {_e}')
    _HAS_DETECTOR = False
    ObstacleDetector = None
    _load_detector_config = None

_CFG = None
_DETECTOR = None
_DETECTOR_INITIALIZED = False
_ROUND_NUMBER = 0

MATCH_THRESHOLD = 0.85
IMG_TARGET_ITEM = 'templates/target_item.png'
IMG_OK_BUTTON = 'templates/ok_button.png'
IMG_RESULT = 'templates/result_screen.png'
IMG_RELAY = 'templates/relay_prompt.png'
IMG_BOOST_SCREEN = 'templates/boost_screen.png'
IMG_LOBBY_PLAY = 'templates/lobby_play.png'
IMG_FRIEND_POPUP = 'templates/friend_popup.png'
IMG_MODE_POPUP = 'templates/mode_popup.png'
IMG_SENDLIFE_POPUP = 'templates/sendlife_popup.png'
DISMISS_POPUPS = [
    {
        'name': "Friend's Info",
        'img': IMG_FRIEND_POPUP,
        'x': (1080, 68),
        'th': 0.8,
    },
    {
        'name': 'Select a Mode',
        'img': IMG_MODE_POPUP,
        'x': (1240, 90),
        'th': 0.8,
    },
    {
        'name': 'Send Life',
        'img': IMG_SENDLIFE_POPUP,
        'x': (485, 458),
        'th': 0.8,
    },
]
BTN_BOX = (540, 560)
BTN_BUY = (925, 292)
BTN_BUY_CONFIRM = (785, 448)
BTN_PLAY = (955, 615)
BTN_LOBBY_PLAY = (1012, 668)
BTN_POPUP_CONFIRM = (625, 585)
BTN_POPUP_CONFIRM_LOW = (630, 620)
BTN_CLOSE_X = (1080, 68)
BTN_MULTI = (1097, 200)
BTN_MULTI_BUY = (635, 588)
BTN_MULTI_CLOSE = (1043, 82)
MULTI_SELECT_TARGETS = [(285, 176)]
MULTIBUY_TIMEOUT = 20
IMG_MULTI_CHECK = 'templates/multi_check.png'
MULTI_CHECK_THRESHOLD = 0.7
BTN_JUMP = (80, 670)
BTN_SLIDE = (1200, 670)
BTN_RELAY = (644, 335)
JUMP_DELAY_MIN = 0
JUMP_DELAY_MAX = 0.75
DOUBLE_JUMP_PROB = 0.30
DOUBLE_JUMP_GAP_SEC = 0.12
JUMP_TAP_POINTS = [
    (80, 670),
    (170, 650),
    (300, 668),
    (430, 648),
    (560, 665),
]
RELAY_THRESHOLD = 0.6
TAP_JITTER = 7
JUMP_JITTER = 28
SLIDE_HOLD_SEC = 0.35
IMG_INGAME = 'templates/ingame.png'
INGAME_THRESHOLD = 0.72
IMG_INGAME2 = 'templates/ingame2.png'
INGAME2_THRESHOLD = 0.75
SLIDE_COOLDOWN = 0.8
PATTERN_FILE = 'pattern.json'
REPLAY_PATTERN = None

BOOST_START_ENABLED = True
BOOST_START_DELAY_SEC = 3.5   # เริ่ม spam tap ที่วินาทีนี้ (หลัง Play)
BOOST_END_DELAY_SEC = 6.0     # หยุด spam tap ที่วินาทีนี้
BOOST_TAP_INTERVAL_SEC = 0.5  # spam ทุกกี่วิ (5 ครั้งใน window 2.5 วิ)
BOOST_DEBUG_SAVE_SCREEN = False   # เซฟภาพหน้าจอตอน tap ครั้งแรก -> ตรวจว่ากดถูกจังหวะ
BOOST_START_TAP = (640, 350)   # LDPlayer 1280x720 — ปรับถ้า resolution ต่าง
IMG_BOOST_START = 'templates/boost_start.png'
BOOST_START_THRESHOLD = 0.7

PIT_LIFT_AVOID = True
IMG_PIT_LIFT = 'templates/pit_lift.png'   # ต้องครอปจากหน้าจอเอง (ดู README)
PIT_LIFT_THRESHOLD = 0.7
BOOST_ITEMS = [
    {
        'name': 'Potion',
        'tap': (210, 430),
        'check_img': 'templates/chk_potion.png',
        'check_roi': (240, 455, 320, 515),
    },
    {
        'name': 'Stopwatch',
        'tap': (365, 430),
        'check_img': 'templates/chk_stopwatch.png',
        'check_roi': (392, 455, 472, 515),
    },
    {
        'name': 'Star x2',
        'tap': (515, 430),
        'check_img': 'templates/chk_star.png',
        'check_roi': (545, 455, 625, 515),
    },
]
CHECK_THRESHOLD = 0.75
DELAY_AFTER_REROLL = 2
DELAY_AFTER_PLAY = 3
LOOP_SLEEP = 0.3
RESULT_CHECK_INTERVAL = 0.5
RUN_STATE_TIMEOUT = 300
BTN_INACTIVE_CONFIRM = (640, 490)
FREEZE_SECS = 8
FREEZE_DIFF = 3
STOP_FLAG = threading.Event()


def watch_emergency_key():
    """เฝ้าฟังปุ่ม 'q' เพื่อสั่งหยุด (รันใน background thread) — โหลด keyboard แบบ lazy"""
    # TODO: verify against disasm — reconstructed with best effort
    try:
        import keyboard
        keyboard.add_hotkey('q', lambda: STOP_FLAG.set())
        while not STOP_FLAG.is_set():
            time.sleep(0.2)
    except Exception:
        pass


def _adb_base():
    '''สร้างคำสั่ง adb พื้นฐาน (รวมการระบุ device ถ้ามี)'''
    cmd = [ADB_PATH]
    if ADB_DEVICE:
        cmd += ['-s', ADB_DEVICE]
    return cmd


def list_online_devices():
    '''คืนรายชื่อ device ที่ออนไลน์ (status = device)'''
    try:
        r = _run([ADB_PATH, 'devices'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
        devs = []
        for ln in r.stdout.decode(errors='ignore').splitlines()[1:]:
            parts = ln.split('\t')
            if len(parts) != 2:
                continue
            if parts[1].strip() != 'device':
                continue
            devs.append(parts[0].strip())
        return devs
    except Exception:
        return []


def auto_select_device():
    '''ถ้า device ที่ตั้งไว้ไม่ออนไลน์ -> เลือก device ออนไลน์ตัวแรกอัตโนมัติ (เผื่อพอร์ตเปลี่ยน)'''
    global ADB_DEVICE
    online = list_online_devices()
    if not online:
        return False
    if ADB_DEVICE not in online:
        print(f"[adb] device '{ADB_DEVICE}' ไม่ออนไลน์ -> เปลี่ยนเป็น '{online[0]}'")
        ADB_DEVICE = online[0]
    return True


def adb_screencap():
    '''
    แคปหน้าจอผ่าน ADB แล้วแปลงเป็นภาพ OpenCV (BGR)
    ใช้ exec-out screencap -p เพื่อรับข้อมูล PNG ทาง stdout โดยตรง (เร็วและไม่ต้องเซฟไฟล์)
    คืนค่า: numpy array (ภาพ) หรือ None ถ้าล้มเหลว
    '''
    cmd = _adb_base() + ['exec-out', 'screencap', '-p']
    try:
        result = _run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if not result.stdout:
            print('[ERR] แคปหน้าจอไม่ได้:', result.stderr.decode(errors='ignore'))
            return None
        img_array = np.frombuffer(result.stdout, dtype=np.uint8)
        screen = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return screen
    except subprocess.TimeoutExpired:
        print('[ERR] ADB screencap timeout')
        return None
    except Exception as e:
        print(f'[ERR] adb_screencap: {e}')
        return None


def adb_tap(x, y, jitter=None):
    '''
    แตะหน้าจอที่ (x, y) + สุ่มเยื้องตำแหน่งเล็กน้อย (กันกดซ้ำจุดเดิมจนดูเป็นบอท)
    jitter = รัศมีสุ่ม (px); ถ้าไม่ระบุใช้ TAP_JITTER
    '''
    # TODO: verify against disasm — reconstructed with best effort
    if jitter is None:
        jitter = TAP_JITTER
    jx = x + random.randint(-jitter, jitter)
    jy = y + random.randint(-jitter, jitter)
    _run(_adb_base() + ['shell', 'input', 'tap', str(jx), str(jy)])


def adb_hold(x, y, duration_sec):
    '''แตะค้างที่ (x, y) เป็นเวลา duration_sec วินาที (ใช้ swipe จุดเดิม)'''
    ms = int(duration_sec * 1000)
    _run(_adb_base() + [
        'shell',
        'input',
        'swipe',
        str(x),
        str(y),
        str(x),
        str(y),
        str(ms),
    ])


def adb_swipe(x1, y1, x2, y2, duration_ms=300):
    '''ปัดจาก (x1,y1) ไป (x2,y2)'''
    _run(_adb_base() + [
        'shell',
        'input',
        'swipe',
        str(x1),
        str(y1),
        str(x2),
        str(y2),
        str(duration_ms),
    ])


def adb_slide(jitter=None):
    '''สไลด์ = กดค้างที่ปุ่ม Slide (แตะเฉยๆ ไม่สไลด์ในเกม). มี jitter ตำแหน่งกันกดจุดเดิม'''
    # TODO: verify against disasm — reconstructed with best effort
    if jitter is None:
        jitter = TAP_JITTER
    x = 1200 + random.randint(-jitter, jitter)
    y = 670 + random.randint(-jitter, jitter)
    adb_hold(x, y, SLIDE_HOLD_SEC)

_TEMPLATE_CACHE = {}


def _imread_unicode(path, flags=cv2.IMREAD_COLOR):
    '''cv2.imread ทดแทน รองรับ path ที่มีตัวอักษร Unicode (Thai/CJK)
       — Windows: cv2.imread เจอ path ภาษาไทยจะคืน None แต่ np.fromfile เขียน
    '''
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        try:
            return cv2.imread(path, flags)
        except Exception:
            return None


def load_template(path):
    if path in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[path]
    tmpl = _imread_unicode(resource_path(path))
    _TEMPLATE_CACHE[path] = tmpl
    return tmpl


def find_template(screen, template_path, threshold=MATCH_THRESHOLD):
    '''
    ค้นหา template ในภาพ screen ด้วย cv2.matchTemplate
    คืนค่า: (found: bool, center: (x, y) หรือ None, score: float)
    '''
    # TODO: verify against disasm — reconstructed with best effort
    if screen is None:
        return (False, None, 0.0)
    tmpl = load_template(template_path)
    if tmpl is None:
        return (False, None, 0.0)
    try:
        result = cv2.matchTemplate(screen, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
    except Exception:
        return (False, None, 0.0)
    if max_val >= threshold:
        h, w = tmpl.shape[:2]
        center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
        return (True, center, float(max_val))
    return (False, None, float(max_val))


def find_in_roi(screen, template_path, roi, threshold=MATCH_THRESHOLD):
    '''
    ค้นหา template เฉพาะในกรอบ roi = (x1, y1, x2, y2) เท่านั้น
    เหมาะกับการเช็คเครื่องหมายถูกของแต่ละไอเทมที่ตำแหน่งตายตัว
    คืนค่า: (found: bool, score: float)
    '''
    # TODO: verify against disasm — reconstructed with best effort
    if screen is None:
        return (False, 0.0)
    tmpl = load_template(template_path)
    if tmpl is None:
        return (False, 0.0)
    x1, y1, x2, y2 = roi
    crop = screen[y1:y2, x1:x2]
    try:
        result = cv2.matchTemplate(crop, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
    except Exception:
        return (False, 0.0)
    return (max_val >= threshold, float(max_val))


def ensure_boosts_selected():
    '''
    เปิดใช้ boost ทั้ง 3 ไอเทมก่อนเริ่มเกม:
    - ถ้าไอเทมไหน "ไม่เห็นเครื่องหมายถูกเขียว" -> กดที่ไอเทมนั้น (ติ๊กใช้/ซื้อ)
    - ถ้าเห็นถูกแล้ว -> ข้าม (กันการกดซ้ำที่จะ toggle ปิด)
    เช็คซ้ำได้สูงสุด 3 รอบ เผื่อกดแล้วต้องรอแอนิเมชัน
    '''
    # TODO: verify against disasm — reconstructed with best effort
    print('[*] ตรวจสอบ Boost 3 ไอเทม...')
    for attempt in range(3):
        if STOP_FLAG.is_set():
            return False
        screen = adb_screencap()
        if screen is None:
            time.sleep(0.5)
            continue
        all_ok = True
        for item in BOOST_ITEMS:
            found, score = find_in_roi(screen, item['check_img'], item['check_roi'], CHECK_THRESHOLD)
            if found:
                print(f"  [OK] {item['name']} ติ๊กแล้ว (score={score:.3f})")
            else:
                all_ok = False
                print(f"  [-] {item['name']} ไม่ติ๊ก -> กด")
                adb_tap(*item['tap'])
                time.sleep(0.5)
        if all_ok:
            return True
    return False


class State(Enum):
    REROLL = auto()
    RUN = auto()
    RESULT = auto()


def ensure_on_boost_screen(max_tries=15):
    '''
    นำทางให้ไปอยู่ "หน้าเตรียมตัว" (Buy some Boosts) ก่อนเริ่มสุ่ม
    จัดการสถานการณ์: อยู่ล็อบบี้ -> กด Play, ป็อปอัพรางวัลบัง -> กดปุ่มกลางล่าง,
    ค้างหน้า Result -> กด OK. (ไม่ใช้ปุ่ม Back เพราะที่ล็อบบี้จะเด้ง "Exit game?")
    คืนค่า True ถ้าถึงหน้าเตรียมตัว
    '''
    # TODO: verify against disasm — reconstructed with best effort
    x_close_tries = 0
    for i in range(max_tries):
        if STOP_FLAG.is_set():
            return False
        screen = adb_screencap()
        if screen is None:
            time.sleep(0.5)
            continue
        found, _, _ = find_template(screen, IMG_BOOST_SCREEN, 0.75)
        if found:
            return True
        dismissed = False
        for p in DISMISS_POPUPS:
            f, _, _ = find_template(screen, p['img'], p['th'])
            if f:
                print(f"[nav] popup '{p['name']}' -> close")
                adb_tap(*p['x'])
                time.sleep(1.0)
                dismissed = True
                break
        if dismissed:
            continue
        f, ok_center, _ = find_template(screen, IMG_OK_BUTTON, 0.75)
        if f and ok_center is not None:
            r, _, _ = find_template(screen, IMG_RESULT, 0.75)
            if r:
                print('[nav] result screen -> OK')
                adb_tap(*ok_center)
                time.sleep(1.5)
                continue
        f, _, _ = find_template(screen, IMG_LOBBY_PLAY, 0.75)
        if f:
            print('[nav] lobby -> Play')
            adb_tap(*BTN_LOBBY_PLAY)
            time.sleep(2.0)
            continue
        if x_close_tries < 3:
            adb_tap(*BTN_CLOSE_X)
            x_close_tries += 1
            time.sleep(0.8)
        else:
            time.sleep(1.0)
    return False


def multibuy_until_target():
    '''
    ใช้ระบบ "Multi-Buy" ในตัวเกมสุ่มหาบูสต์เป้าหมาย (แทนการกดสุ่มเองทีละครั้งแบบเดิม):
      1) กดปุ่ม Multi เปิดหน้า "Pick desired Boosts!"
      2) ติ๊กบูสต์ที่ยอมรับ (MULTI_SELECT_TARGETS)
      3) กด Multi-Buy -> เกมสุ่มซื้อเองวนจนได้บูสต์ที่ติ๊ก แล้วหยุด+ปิดหน้าให้เอง
    ทุกการกดใช้ adb_tap (มี jitter สุ่มเยื้องตำแหน่งทุกครั้ง กันกดจุดเดิมซ้ำจนดูเป็นบอท)
    คืนค่า True ถ้าเจอ Double Coins banner บนหน้าเตรียมตัว
    '''
    # TODO: verify against disasm — reconstructed with best effort
    print('[reroll] เลือกกล่อง Random Boost ก่อน')
    adb_tap(*BTN_BOX)
    time.sleep(0.4)
    print('[reroll] เปิดหน้า Multi-Buy')
    adb_tap(*BTN_MULTI)
    time.sleep(0.6)
    for tgt in MULTI_SELECT_TARGETS:
        adb_tap(*tgt)
        time.sleep(0.15)
    print('[reroll] กดปุ่ม Multi-Buy')
    adb_tap(*BTN_MULTI_BUY)
    start = time.time()
    while time.time() - start < MULTIBUY_TIMEOUT:
        if STOP_FLAG.is_set():
            return False
        screen = adb_screencap()
        if screen is None:
            time.sleep(0.2)
            continue
        found, _, score = find_template(screen, IMG_TARGET_ITEM, 0.75)
        if found:
            print(f'[OK] เจอ Double Coins (score={score:.3f})')
            return True
        time.sleep(0.25)
    print('[WARN] multi-buy timeout')
    return False


def state_reroll():
    '''
    STATE 1: ตรวจให้อยู่หน้าเตรียมตัวก่อน แล้วใช้ Multi-Buy หา Double Coins แล้วกด Play
    คืนค่า: State ถัดไป
    '''
    print('\n===== [STATE 1] REROLL — Multi-Buy หา Double Coins =====')
    if not ensure_on_boost_screen():
        print('[WARN] นำทางยังไม่สำเร็จ -> รอแล้ววนลองใหม่ (ไม่หยุดบอท)')
        time.sleep(3)
        return State.REROLL
    screen = adb_screencap()
    (found, _, score) = find_template(screen, IMG_TARGET_ITEM, 0.75)
    if found:
        print(f'[OK] มี Double Coins อยู่แล้ว (score={score:.3f}) -> ข้ามการสุ่ม')
    elif not multibuy_until_target():
        print('[WARN] Multi-Buy ไม่สำเร็จ -> วนกลับมานำทาง/ลองใหม่ (ไม่หยุดบอท)')
        return State.REROLL
    ensure_boosts_selected()
    print('[OK] -> กด Play เริ่มวิ่ง')
    time.sleep(DELAY_AFTER_PLAY)
    adb_tap(*BTN_PLAY)
    _tap_fast_start_boost()
    return State.RUN


def _tap_fast_start_boost():
    if not BOOST_START_ENABLED or STOP_FLAG.is_set():
        return
    time.sleep(BOOST_START_DELAY_SEC)
    if STOP_FLAG.is_set():
        return

    tmpl = load_template(IMG_BOOST_START)
    if tmpl is not None:
        end_time = time.time() + (BOOST_END_DELAY_SEC - BOOST_START_DELAY_SEC)
        while time.time() < end_time and not STOP_FLAG.is_set():
            screen = adb_screencap()
            if screen is not None:
                bf, bc, bs = find_template(screen, IMG_BOOST_START, BOOST_START_THRESHOLD)
                if bf and bc is not None:
                    print(f'[boost] เจอ Fast Start Boost (score={bs:.3f}) -> กด {bc}')
                    adb_tap(*bc)
                    return
            time.sleep(0.3)
        print('[boost] template ไม่เจอในเวลา window')
        return

    if BOOST_DEBUG_SAVE_SCREEN:
        screen = adb_screencap()
        if screen is not None:
            try:
                path = os.path.join(_writable_dir(), f'boost_debug_{int(time.time())}.png')
                cv2.imwrite(path, screen)
                print(f'[boost-debug] saved -> {path}')
            except Exception as e:
                print(f'[boost-debug] save failed: {e}')

    end_time = time.time() + (BOOST_END_DELAY_SEC - BOOST_START_DELAY_SEC)
    tap_count = 0
    print(f'[boost] spam tap ที่ {BOOST_START_TAP} ระหว่าง {BOOST_START_DELAY_SEC}s-{BOOST_END_DELAY_SEC}s (ทุก {BOOST_TAP_INTERVAL_SEC}s)')
    while time.time() < end_time and not STOP_FLAG.is_set():
        adb_tap(*BOOST_START_TAP)
        tap_count += 1
        time.sleep(BOOST_TAP_INTERVAL_SEC)
    print(f'[boost] จบ spam tap รวม {tap_count} ครั้ง')


def _pattern_path():
    return os.path.join(_writable_dir(), PATTERN_FILE)


def load_pattern():
    '''โหลด pattern (list ของ [t, action]) จากไฟล์ คืน list หรือ None'''
    # TODO: verify against disasm — reconstructed with best effort
    path = _pattern_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('events')
    except Exception:
        return None


def save_pattern(events):
    '''เซฟ pattern (list ของ [t, action]) ลงไฟล์'''
    with open(_pattern_path(), 'w', encoding='utf-8') as f:
        json.dump({'events': events}, f)


def wait_ingame(timeout=20):
    '''รอจนเข้าหน้าวิ่ง (intro BONUSTIME — เจอปุ่ม Jump) ใช้เป็นจุด t=0. คืน True ถ้าเจอ'''
    start = time.time()
    while time.time() - start < timeout:
        if STOP_FLAG.is_set():
            return False
        (f, _, _) = find_template(adb_screencap(), IMG_INGAME, INGAME_THRESHOLD)
        if f:
            return True
        time.sleep(0.12)
    return False


def _frame_signature(screen):
    '''ย่อเฟรมเป็น grayscale 64x36 ใช้เทียบว่า "หน้าจอนิ่ง" หรือไม่ (สำหรับตรวจป๊อปอัป/ค้าง)'''
    small = cv2.resize(screen, (64, 36))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


def state_run():
    '''
    STATE 2: วิ่งในด่าน
      - โหมดปกติ: กดปุ่ม Jump เรื่อยๆ สุ่มดีเลย์ JUMP_DELAY_MIN..MAX วินาที
      - โหมด pattern (REPLAY_PATTERN ถูกตั้ง): เล่นซ้ำการกด Jump/Slide ตามเวลาที่อัดไว้
      - คอยตรวจ "นินจา Cookie Relay Boost" ถ้าเจอให้กดเพื่อวิ่งต่อ
      - คอยตรวจหน้า "Result" ถ้าเจอ -> ไป STATE 3
    คืนค่า: State ถัดไป
    '''
    # TODO: verify against disasm — reconstructed with best effort
    print('\n===== [STATE 2] RUN — วิ่งในด่าน =====')
    if not wait_ingame():
        print('[WARN] ไม่พบหน้าวิ่งภายใน timeout')
        try:
            _dbg = adb_screencap()
            if _dbg is not None:
                _ts = time.strftime('%H%M%S')
                _path = os.path.join(_writable_dir(), f'ingame_fail_{_ts}.png')
                cv2.imwrite(_path, _dbg)
                print(f'[debug] เซฟหน้าจอ ingame_fail -> {_path}')
        except Exception as _e:
            print(f'[debug] เซฟ ingame_fail ล้ม: {_e}')
        return State.RESULT
    t_start = time.time()
    global _ROUND_NUMBER
    _ROUND_NUMBER += 1
    detector = _get_detector()
    if detector is not None:
        detector.reset_round()
    print(f'[round] #{_ROUND_NUMBER:03d} start')
    last_sig = None
    last_change_time = time.time()
    pattern = REPLAY_PATTERN
    pat_i = 0
    last_jump_time = 0.0
    last_slide_time = 0.0
    next_jump_delay = random.uniform(JUMP_DELAY_MIN, JUMP_DELAY_MAX)
    while not STOP_FLAG.is_set():
        now = time.time()
        if now - t_start > RUN_STATE_TIMEOUT:
            print('[WARN] RUN state timeout')
            _maybe_save_crash_log(t_start, 'timeout')
            return State.RESULT
        _loop_t0 = time.perf_counter()
        _t = _loop_t0
        screen = adb_screencap()
        if detector is not None:
            detector.record_external_timing('screencap_ms', (time.perf_counter() - _t) * 1000)
        if screen is None:
            time.sleep(LOOP_SLEEP)
            continue

        # === Pit Lift avoidance: เจอหน้า "5 for 1 Pit Lift" -> หยุดกดทุกปุ่ม ===
        if PIT_LIFT_AVOID:
            pl, _, _ = find_template(screen, IMG_PIT_LIFT, PIT_LIFT_THRESHOLD)
            if pl:
                print('[pit-lift] เจอหน้า Save the Cookie / Pit Lift -> รอ auto-decline (ไม่กด)')
                time.sleep(1.0)
                continue

        f, _, _ = find_template(screen, IMG_RESULT, 0.75)
        if f:
            print('[OK] เจอหน้า Result -> STATE 3')
            _maybe_save_run_log(t_start, 'result')
            return State.RESULT
        f, _, _ = find_template(screen, IMG_RELAY, RELAY_THRESHOLD)
        if f:
            print('[relay] กด Relay')
            adb_tap(*BTN_RELAY)
            time.sleep(0.5)
            continue

        if detector is not None and _CFG is not None and _CFG['detection'].get('enabled', True):
            detector.push_frame(screen)
            _tt = time.perf_counter()
            _sf, _, _ = find_template(screen, IMG_INGAME2, INGAME2_THRESHOLD)
            detector.record_external_timing('template_ms', (time.perf_counter() - _tt) * 1000)
            _action, _score, _votes = detector.detect(screen, template_slide_match=bool(_sf))
            if _action == 'slide':
                print(f'[hybrid] SLIDE score={_score} votes={_votes}')
                adb_slide()
                continue
            if _action == 'jump':
                print(f'[hybrid] JUMP score={_score} votes={_votes}')
                pt = random.choice(JUMP_TAP_POINTS)
                adb_tap(pt[0], pt[1], JUMP_JITTER)
                if random.random() < _CFG['double_jump']['random_probability']:
                    time.sleep(_CFG['double_jump']['gap_seconds'])
                    adb_tap(pt[0], pt[1], JUMP_JITTER)
                continue
        else:
            sf, _, _ = find_template(screen, IMG_INGAME2, INGAME2_THRESHOLD)
            if sf and (now - last_slide_time) > SLIDE_COOLDOWN:
                print('[slide] เจอ ingame2 -> Slide')
                adb_slide()
                last_slide_time = now
                continue

        if pattern and pat_i < len(pattern):
            t, action = pattern[pat_i]
            if now - t_start >= t:
                if action == 'jump':
                    pt = random.choice(JUMP_TAP_POINTS)
                    adb_tap(pt[0], pt[1], JUMP_JITTER)
                elif action == 'slide':
                    adb_slide()
                pat_i += 1
        else:
            if now - last_jump_time >= next_jump_delay:
                pt = random.choice(JUMP_TAP_POINTS)
                adb_tap(pt[0], pt[1], JUMP_JITTER)
                if random.random() < DOUBLE_JUMP_PROB:
                    time.sleep(DOUBLE_JUMP_GAP_SEC)
                    pt2 = random.choice(JUMP_TAP_POINTS)
                    adb_tap(pt2[0], pt2[1], JUMP_JITTER)
                    if detector is not None:
                        detector.notify_double_jump()
                last_jump_time = now
                next_jump_delay = random.uniform(JUMP_DELAY_MIN, JUMP_DELAY_MAX)
        try:
            sig = _frame_signature(screen)
            if last_sig is not None:
                diff = float(np.abs(sig - last_sig).mean())
                if diff < FREEZE_DIFF:
                    if now - last_change_time > FREEZE_SECS:
                        print('[WARN] freeze detected')
                        _maybe_save_crash_log(t_start, 'freeze')
                        return State.RESULT
                else:
                    last_change_time = now
            last_sig = sig
        except Exception:
            pass
        if detector is not None:
            detector.record_external_timing('loop_total_ms', (time.perf_counter() - _loop_t0) * 1000)
        time.sleep(LOOP_SLEEP)
    _maybe_save_run_log(t_start, 'stopped')
    return State.RESULT

COIN_LOG_ROI = (945, 383, 1118, 430)
(_DIG_GW, _DIG_GH) = (24, 36)
_DIGIT_TEMPLATES = None
COIN_CALLBACK = None
COIN_TOTAL = 0


def _dir_writable(d):
    '''ทดสอบว่าเขียนไฟล์ในโฟลเดอร์ได้จริง (Program Files มัก block ด้วย UAC)'''
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, '.cookiegame_write_test')
        with open(test, 'wb') as f:
            f.write(b'x')
        os.remove(test)
        return True
    except Exception:
        return False


def _user_data_dir():
    '''โฟลเดอร์ user data ต่อ OS สำหรับ fallback เมื่อโฟลเดอร์หลักเขียนไม่ได้'''
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~\\AppData\\Local')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'CookieGame')


_WRITABLE_DIR_CACHE = None


def _get_detector():
    '''Lazy-init hybrid ObstacleDetector. Returns None if disabled/unavailable.'''
    global _CFG, _DETECTOR, _DETECTOR_INITIALIZED
    if _DETECTOR_INITIALIZED:
        return _DETECTOR
    _DETECTOR_INITIALIZED = True
    if not _HAS_DETECTOR:
        return None
    try:
        bundled = resource_path('config.yaml')
        user = os.path.join(_user_data_dir(), 'config.yaml')
        _CFG, source = _load_detector_config(user, bundled)
        print(f'[config] source: {source}')
        print(f'[config] version: {_CFG.get("config_version", "?")}')
        _DETECTOR = ObstacleDetector(_CFG)
        print(f'[detector] initialized (enabled={_CFG["detection"]["enabled"]})')
    except Exception as e:
        print(f'[detector] init error: {e}')
        _DETECTOR = None
        _CFG = None
    return _DETECTOR


def _config_source_path():
    try:
        p = os.path.join(_writable_dir(), 'config.yaml')
        if os.path.isfile(p):
            return p
    except Exception:
        pass
    try:
        return resource_path('config.yaml')
    except Exception:
        return None


def _maybe_save_run_log(t_start, reason):
    if _DETECTOR is None or _CFG is None:
        return
    try:
        run_duration = time.time() - t_start
        ts = time.strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(_writable_dir(), 'logs', 'runs',
                               f'{ts}_round_{_ROUND_NUMBER:03d}_{reason}')
        _DETECTOR.save_run_log(run_dir, run_duration, _config_source_path())
    except Exception as e:
        print(f'[run-log] error: {e}')


def _maybe_save_crash_log(t_start, reason):
    if _DETECTOR is None or _CFG is None:
        return
    try:
        run_duration = time.time() - t_start
        if run_duration < _CFG['crash_log']['short_run_threshold_sec']:
            ts = time.strftime('%Y%m%d_%H%M%S')
            crash_dir = os.path.join(_writable_dir(), 'crash_log',
                                     f'{ts}_round_{_ROUND_NUMBER:03d}_{reason}')
            _DETECTOR.save_crash_log(crash_dir, run_duration)
    except Exception as e:
        print(f'[crash-log] error: {e}')
    _maybe_save_run_log(t_start, reason)


def _writable_dir():
    '''โฟลเดอร์เขียนไฟล์ได้ (pattern.json, coins.csv, license.key):
       Frozen: ข้าง .exe ก่อน — ถ้าเขียนไม่ได้ (Program Files + UAC) fallback ไป user data
       Dev:    โฟลเดอร์สคริปต์
    '''
    global _WRITABLE_DIR_CACHE
    if _WRITABLE_DIR_CACHE is not None:
        return _WRITABLE_DIR_CACHE
    if getattr(sys, 'frozen', False):
        primary = os.path.dirname(sys.executable)
        if _dir_writable(primary):
            _WRITABLE_DIR_CACHE = primary
        else:
            fallback = _user_data_dir()
            os.makedirs(fallback, exist_ok=True)
            _WRITABLE_DIR_CACHE = fallback
    else:
        _WRITABLE_DIR_CACHE = os.path.dirname(os.path.abspath(__file__))
    return _WRITABLE_DIR_CACHE


def _load_digit_templates():
    '''โหลด template ตัวเลข 0-9 (templates/dig/{d}.png) แบบ grayscale + cache'''
    # TODO: verify against disasm — reconstructed with best effort
    global _DIGIT_TEMPLATES
    if _DIGIT_TEMPLATES is not None:
        return _DIGIT_TEMPLATES
    templates = {}
    for d in range(10):
        path = resource_path(f'templates/dig/{d}.png')
        img = _imread_unicode(path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            templates[d] = img
    _DIGIT_TEMPLATES = templates
    return templates


def _segment_digits(crop):
    '''แยก glyph ตัวเลขในกรอบ (ตัดคอมมา/จุดออกด้วยความสูง) คืน (th, boxes เรียงซ้าย->ขวา)'''
    # TODO: verify against disasm — reconstructed with best effort
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    (_, th) = cv2.threshold(g, 110, 255, cv2.THRESH_BINARY_INV)
    cols = th.sum(axis=0)
    start = 0
    inrun = False
    groups = []
    for x, v in enumerate(cols):
        if v > 0 and not inrun:
            inrun = True
            start = x
        elif v == 0 and inrun:
            groups.append((start, x))
            inrun = False
    if inrun:
        groups.append((start, len(cols)))
    boxes = []
    for x0, x1 in groups:
        rows = np.where(th[:, x0:x1].sum(axis=1) > 0)[0]
        if not len(rows):
            continue
        boxes.append([x0, rows[0], x1, rows[-1] + 1])
    if not boxes:
        return (th, [])
    maxh = max(b[3] - b[1] for b in boxes)
    boxes = [b for b in boxes if (b[3] - b[1]) >= maxh * 0.6]
    return (th, boxes)


def read_coins(screen):
    '''อ่านเลขเหรียญจากแถว Coins บนหน้า Result -> int (หรือ None ถ้าอ่านไม่ได้)'''
    # TODO: verify against disasm — reconstructed with best effort
    if screen is None:
        return None
    x1, y1, x2, y2 = COIN_LOG_ROI
    try:
        crop = screen[y1:y2, x1:x2]
    except Exception:
        return None
    templates = _load_digit_templates()
    if not templates:
        return None
    th, boxes = _segment_digits(crop)
    if not boxes:
        return None
    digits = []
    for box in boxes:
        gx0, gy0, gx1, gy1 = box
        glyph = th[gy0:gy1, gx0:gx1]
        if glyph.size == 0:
            continue
        best_d = -1
        best_score = -1.0
        for d, tmpl in templates.items():
            try:
                resized = cv2.resize(glyph, (tmpl.shape[1], tmpl.shape[0]))
                res = cv2.matchTemplate(resized, tmpl, cv2.TM_CCOEFF_NORMED)
                _, mx, _, _ = cv2.minMaxLoc(res)
                if mx > best_score:
                    best_score = mx
                    best_d = d
            except Exception:
                continue
        if best_d >= 0:
            digits.append(str(best_d))
    if not digits:
        return None
    try:
        return int(''.join(digits))
    except Exception:
        return None


def record_result_coins(screen):
    '''อ่านเลขเหรียญรอบนี้ -> log ลง coins.csv + ส่งค่าให้ GUI (COIN_CALLBACK). อ่านพลาดค่อยเซฟภาพไว้ดู'''
    # TODO: verify against disasm — reconstructed with best effort
    global COIN_TOTAL
    coins = read_coins(screen)
    if coins is None:
        try:
            fail_path = os.path.join(_writable_dir(), f'coins_fail_{int(time.time())}.png')
            cv2.imwrite(fail_path, screen)
        except Exception:
            pass
        print('[coins] อ่านเหรียญไม่ได้ -> บันทึกภาพไว้ดู')
        return
    COIN_TOTAL += coins
    try:
        csv_path = os.path.join(_writable_dir(), 'coins.csv')
        with open(csv_path, 'a', encoding='utf-8') as f:
            f.write(f'{datetime.datetime.now().isoformat()},{coins},{COIN_TOTAL}\n')
    except Exception:
        pass
    print(f'[coins] +{coins} (รวม {COIN_TOTAL})')
    cb = COIN_CALLBACK
    if cb is not None:
        try:
            cb(coins, COIN_TOTAL)
        except Exception:
            pass


def state_result():
    '''
    STATE 3: หาปุ่ม OK/ตกลง แล้วกดเพื่อกลับล็อบบี้ -> กลับไป STATE 1
    คืนค่า: State ถัดไป
    '''
    # TODO: verify against disasm — reconstructed with best effort
    print('\n===== [STATE 3] RESULT — กำลังหาปุ่ม OK =====')
    attempts = 0
    MAX_ATTEMPTS = 40
    recorded = False
    while attempts < MAX_ATTEMPTS and not STOP_FLAG.is_set():
        screen = adb_screencap()
        if screen is None:
            time.sleep(RESULT_CHECK_INTERVAL)
            attempts += 1
            continue
        if not recorded:
            try:
                record_result_coins(screen)
            except Exception as e:
                print(f'[ERR] record_result_coins: {e}')
            recorded = True
        found, center, _ = find_template(screen, IMG_OK_BUTTON, 0.75)
        if found and center is not None:
            print('[OK] กด OK -> กลับล็อบบี้')
            adb_tap(*center)
            time.sleep(1.5)
            return State.REROLL
        time.sleep(RESULT_CHECK_INTERVAL)
        attempts += 1
    print('[WARN] state_result timeout -> กลับไป REROLL')
    return State.REROLL


def check_connection():
    '''ทดสอบเชื่อมต่อ ADB/แคปหน้าจอ คืน True ถ้าใช้งานได้'''
    auto_select_device()
    return adb_screencap() is not None


def run_state_machine(max_loops=0, on_loop_done=None):
    '''
    ลูป State Machine หลัก (ใช้ได้ทั้ง CLI และหน้าต่างแอป) — หยุดด้วย STOP_FLAG
    max_loops = 0  -> วนไม่จำกัด
    max_loops > 0  -> หยุดอัตโนมัติเมื่อเล่นจบครบจำนวนรอบ (1 รอบ = จบ 1 เกม)
    on_loop_done(loops_done) -> callback เรียกหลังจบแต่ละรอบ (ไว้ให้ GUI นับถอยหลัง)
    '''
    # TODO: verify against disasm — reconstructed with best effort
    global COIN_TOTAL
    COIN_TOTAL = 0
    current_state = State.REROLL
    loops_done = 0
    err_streak = 0
    STOP_FLAG.clear()
    while not STOP_FLAG.is_set():
        try:
            if current_state == State.REROLL:
                current_state = state_reroll()
            elif current_state == State.RUN:
                current_state = state_run()
            elif current_state == State.RESULT:
                current_state = state_result()
                loops_done += 1
                if on_loop_done is not None:
                    try:
                        on_loop_done(loops_done)
                    except Exception:
                        pass
                if max_loops > 0 and loops_done >= max_loops:
                    print(f'[OK] ครบ {loops_done} รอบ -> หยุด')
                    break
            err_streak = 0
        except Exception as e:
            err_streak += 1
            print(f'[ERR] state loop: {e}')
            traceback.print_exc()
            if err_streak > 5:
                print('[FATAL] ข้อผิดพลาดต่อเนื่อง -> หยุด')
                break
            time.sleep(2)


def main():
    # TODO: verify against disasm — reconstructed with best effort
    print('============================================================')
    print(' LDPlayer Game Bot - State Machine')
    print(" กดปุ่ม 'q' ได้ตลอดเวลาเพื่อหยุดบอท")
    print('============================================================')
    try:
        import keyboard  # noqa: F401
        watcher = threading.Thread(target=watch_emergency_key, daemon=True)
        watcher.start()
    except Exception:
        print(" [หมายเหตุ] ไม่พบ library 'keyboard' -> ปุ่ม q ทำงานเฉพาะเมื่อโฟกัสที่หน้าต่างนี้")
        print('            แนะนำติดตั้ง:  pip install keyboard')
    if not check_connection():
        print("[FATAL] เชื่อมต่อ ADB/แคปหน้าจอไม่ได้ — ตรวจ ADB_DEVICE และคำสั่ง 'adb devices'")
        return
    run_state_machine()


if __name__ == '__main__':
    main()
