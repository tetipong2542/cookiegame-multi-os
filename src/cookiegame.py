"""
CookieGame - หน้าต่างควบคุมบอท Cookie Run (LDPlayer)
=====================================================
DEMO BUILD - license_core ถูกแทนที่เป็น demo stub, ทุก key ผ่านหมด
ต้นฉบับระบบ license (ECDSA + HWID lock) อยู่ที่ src/license_core.original.py
"""
import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

import bot
import license_core

APP_NAME = 'CookieGame'


def _license_path():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'license.key')


class QueueWriter:
    """ส่ง print() ของ bot ไปเข้าคิว log ของ GUI"""

    def __init__(self, q):
        self.q = q

    def write(self, text):
        if text:
            self.q.put(text)

    def flush(self):
        pass


class CookieGameApp:

    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()
        self.hwid = license_core.get_hwid()
        self.running = False
        self.licensed = False
        self.bot_thread = None

        self._build_ui()
        self.load_license()

        sys.stdout = QueueWriter(self.log_queue)
        bot.LOG_CALLBACK = self._log
        bot.COIN_CALLBACK = self._update_coins

        self._poll_log()

    def _build_ui(self):
        self.root.title(f'{APP_NAME} v{bot.BOT_VERSION} (DEMO)')
        self.root.geometry('560x720')
        self.root.minsize(520, 660)
        self.root.configure(bg='#2b2b3a')

        head = tk.Label(self.root, text='🍪  CookieGame',
                        font=('Segoe UI', 20, 'bold'),
                        bg='#2b2b3a', fg='#ffd966')
        head.pack(pady=(14, 2))
        tk.Label(self.root, text='By gamerael',
                 font=('Segoe UI', 9, 'italic'),
                 bg='#2b2b3a', fg='#7ec8ff').pack()

        lic = tk.Frame(self.root, bg='#3a3450')
        lic.pack(fill='x', padx=16, pady=(8, 2))
        row2 = tk.Frame(lic, bg='#3a3450')
        row2.pack(fill='x', padx=8, pady=(8, 4))
        tk.Label(row2, text='License key:', bg='#3a3450', fg='#dddde8',
                 font=('Segoe UI', 9)).pack(side='left')
        self.key_var = tk.StringVar(value='demo')
        tk.Entry(row2, textvariable=self.key_var, width=36,
                 font=('Consolas', 8)).pack(side='left', padx=4)
        tk.Button(row2, text='ใช้งาน key', command=self.activate_license,
                  font=('Segoe UI', 8)).pack(side='left')
        self.lic_status = tk.StringVar(value='🔒 ยังไม่ได้ใช้งาน key')
        self.lic_lbl = tk.Label(lic, textvariable=self.lic_status,
                                bg='#3a3450', fg='#ff9e9e',
                                font=('Segoe UI', 9, 'bold'))
        self.lic_lbl.pack(anchor='w', padx=10, pady=(0, 4))
        tk.Label(lic, text=f'(เครื่อง: {self.hwid})',
                 bg='#3a3450', fg='#7a7a90',
                 font=('Segoe UI', 7)).pack(anchor='w', padx=10, pady=(0, 6))

        cfg = tk.Frame(self.root, bg='#34344a')
        cfg.pack(fill='x', padx=16, pady=10)
        tk.Label(cfg, text='ADB path:', bg='#34344a', fg='#dddde8',
                 font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w',
                                             padx=8, pady=6)
        self.adb_var = tk.StringVar(value=bot.ADB_PATH)
        tk.Entry(cfg, textvariable=self.adb_var, width=44,
                 font=('Consolas', 9)).grid(row=0, column=1, padx=4, pady=6)
        tk.Button(cfg, text='หาอัตโนมัติ', command=self.auto_find_adb,
                  font=('Segoe UI', 8)).grid(row=0, column=2, padx=6)
        tk.Label(cfg, text='Device:', bg='#34344a', fg='#dddde8',
                 font=('Segoe UI', 9)).grid(row=1, column=0, sticky='w',
                                             padx=8, pady=6)
        self.dev_var = tk.StringVar(value=bot.ADB_DEVICE)
        tk.Entry(cfg, textvariable=self.dev_var, width=24,
                 font=('Consolas', 9)).grid(row=1, column=1, sticky='w',
                                             padx=4, pady=6)
        tk.Button(cfg, text='ทดสอบเชื่อมต่อ', command=self.test_connection,
                  font=('Segoe UI', 8)).grid(row=1, column=2, padx=6)
        tk.Label(cfg, text='จำนวนรอบ:', bg='#34344a', fg='#dddde8',
                 font=('Segoe UI', 9)).grid(row=2, column=0, sticky='w',
                                             padx=8, pady=6)
        self.loops_var = tk.StringVar(value='0')
        tk.Entry(cfg, textvariable=self.loops_var, width=10,
                 font=('Consolas', 9), justify='center').grid(
                     row=2, column=1, sticky='w', padx=4, pady=6)
        tk.Label(cfg, text='(0 = ไม่จำกัด รันจนกดหยุด)',
                 bg='#34344a', fg='#9a9ab0',
                 font=('Segoe UI', 8)).grid(row=2, column=2, sticky='w', padx=6)

        self.status_var = tk.StringVar(value='● หยุดอยู่')
        self.status_lbl = tk.Label(self.root, textvariable=self.status_var,
                                    font=('Segoe UI', 11, 'bold'),
                                    bg='#2b2b3a', fg='#ff6b6b')
        self.status_lbl.pack(pady=(2, 6))
        self.toggle_btn = tk.Button(self.root, text='▶  เริ่มบอท',
                                     command=self.toggle,
                                     font=('Segoe UI', 14, 'bold'),
                                     bg='#4caf50', fg='white',
                                     activebackground='#43a047',
                                     width=20, height=1, bd=0, cursor='hand2')
        self.toggle_btn.pack(pady=4)

        self.coins_var = tk.StringVar(value='🪙 เหรียญรอบล่าสุด: -    รวม: 0')
        tk.Label(self.root, textvariable=self.coins_var,
                 font=('Segoe UI', 12, 'bold'),
                 bg='#2b2b3a', fg='#ffd966').pack(pady=(2, 6))

        tk.Label(self.root, text='บันทึกการทำงาน (log):',
                 bg='#2b2b3a', fg='#b8b8c8',
                 font=('Segoe UI', 9)).pack(anchor='w', padx=18, pady=(10, 0))
        self.log = scrolledtext.ScrolledText(
            self.root, height=12, font=('Consolas', 9),
            bg='#1e1e28', fg='#d4d4d4',
            insertbackground='white', wrap='word')
        self.log.pack(fill='both', expand=True, padx=16, pady=(2, 14))

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def _apply_license_result(self, ok, info):
        if ok:
            t = info.get('type') if isinstance(info, dict) else None
            if t == 'permanent':
                self.lic_status.set('✅ License: ถาวร')
            elif t == 'rental':
                exp = info.get('exp') if isinstance(info, dict) else '?'
                self.lic_status.set(f'✅ License: เช่า (หมดอายุ {exp})')
            elif t == 'demo':
                self.lic_status.set('✅ DEMO MODE — ทดสอบฟรี ไม่ต้องใส่ key')
            else:
                self.lic_status.set('✅ License ใช้งานได้')
            self.lic_lbl.config(fg='#69f0ae')
            self.licensed = True
        else:
            self.lic_status.set(f'🔒 {info}')
            self.lic_lbl.config(fg='#ff9e9e')
            self.licensed = False

    def load_license(self):
        ok, info = license_core.check_license()
        self._apply_license_result(ok, info)

    def activate_license(self):
        key = self.key_var.get().strip()
        ok, info = license_core.activate(key)
        if ok:
            self._log('[app] ✅ ใช้งาน key สำเร็จ (demo mode)\n')
        else:
            self._log(f'[app] ❌ key ใช้ไม่ได้: {info}\n')
        self._apply_license_result(ok, info)

    def auto_find_adb(self):
        path = bot.find_adb()
        self.adb_var.set(path)
        self._log(f'[app] หา adb อัตโนมัติ: {path}\n')

    def _apply_config(self):
        bot.ADB_PATH = self.adb_var.get().strip()
        dev = self.dev_var.get().strip()
        bot.ADB_DEVICE = dev if dev else None

    def test_connection(self):
        self._apply_config()

        def run():
            try:
                ok = bot.check_connection()
                msg = '✅ เชื่อมต่อ ADB + แคปหน้าจอสำเร็จ' if ok else '❌ เชื่อมต่อไม่ได้ (ตรวจ ADB path/device)'
            except Exception as e:
                msg = f'❌ ทดสอบล้มเหลว: {e}'
            self.root.after(0, lambda: self._log(f'[app] {msg}\n'))

        threading.Thread(target=run, daemon=True).start()

    def toggle(self):
        if not self.running:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        if not self.licensed:
            self._log('[app] ❌ License ยังไม่พร้อม\n')
            return
        if not license_core.acquire_run_lock():
            self._log('[app] ❌ Key นี้กำลังรันอยู่บนอีกจอ\n')
            return
        try:
            loops = int((self.loops_var.get() or '0').strip())
        except ValueError:
            loops = 0
        self._apply_config()
        bot.STOP_FLAG.clear()
        self.running = True
        self.toggle_btn.config(text='■  หยุดบอท', bg='#f44336',
                                activebackground='#e53935')
        self.status_var.set('● กำลังรัน...')
        self.status_lbl.config(fg='#69f0ae')
        loops_disp = str(loops) if loops > 0 else '∞'
        self._log(f'[app] ▶ เริ่มบอท (loops={loops_disp})\n')
        self.bot_thread = threading.Thread(
            target=self._run_bot_thread, args=(loops,), daemon=True)
        self.bot_thread.start()

    def _run_bot_thread(self, loops):
        try:
            bot.run_state_machine(loops, on_loop_done=self._on_loop_done)
        except Exception as e:
            self._log(f'[app] ❌ บอทเจอ error: {e}\n')
        finally:
            self.root.after(0, self._on_bot_stopped)

    def stop_bot(self):
        bot.STOP_FLAG.set()
        self.status_var.set('● กำลังหยุด...')
        self.status_lbl.config(fg='#ffd166')
        self.toggle_btn.config(state='disabled')
        self._log('[app] กำลังหยุด (รอจบ state ปัจจุบัน)...\n')

    def _on_bot_stopped(self):
        license_core.release_run_lock()
        self.running = False
        self.toggle_btn.config(text='▶  เริ่มบอท', bg='#4caf50',
                                activebackground='#43a047', state='normal')
        self.status_var.set('● หยุดอยู่')
        self.status_lbl.config(fg='#ff6b6b')

    def _on_loop_done(self, loops_done):
        self.root.after(0, lambda: self._log(f'[app] จบรอบที่ {loops_done}\n'))

    def _update_coins(self, coins, total):
        self.root.after(
            0,
            lambda: self.coins_var.set(
                f'🪙 เหรียญรอบล่าสุด: {coins}    รวม: {total}'))

    def _log(self, text):
        self.log_queue.put(text)

    def _poll_log(self):
        inserted = False
        try:
            for _ in range(300):
                text = self.log_queue.get_nowait()
                self.log.insert('end', text)
                inserted = True
        except queue.Empty:
            pass
        if inserted:
            try:
                self.log.see('end')
                if int(self.log.index('end-1c').split('.')[0]) > 800:
                    self.log.delete('1.0', '300.0')
            except Exception:
                pass
        self.root.after(150, self._poll_log)

    def on_close(self):
        bot.STOP_FLAG.set()
        time.sleep(0.1)
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    CookieGameApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
