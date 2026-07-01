import socket
import struct
import subprocess
import threading
import time
from typing import Optional

import cv2
import numpy as np


_MINICAP_PORT = 1313
_MINICAP_PATH = '/data/local/tmp/minicap'
_DEFAULT_RES = '1280x720'


def _run_adb(cmd, timeout=5, **kwargs):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, **kwargs)


class MinicapCapture:
    def __init__(self, resolution: str = _DEFAULT_RES, adb_base=None):
        self.resolution = resolution
        self.adb_base = adb_base or ['adb']
        self.process: Optional[subprocess.Popen] = None
        self.socket: Optional[socket.socket] = None
        self.frame_buffer = None
        self.frame_lock = threading.Lock()
        self.reader_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.width = None
        self.height = None
        self.frames_received = 0
        self.last_frame_ts = 0.0

    def check_installed(self) -> bool:
        try:
            r = _run_adb(self.adb_base + ['shell', 'ls', _MINICAP_PATH], timeout=5)
            out = (r.stdout + r.stderr).decode(errors='ignore')
            return 'No such file' not in out and 'not found' not in out and r.returncode == 0
        except Exception:
            return False

    def _kill_existing(self):
        try:
            _run_adb(self.adb_base + ['shell', 'killall', '-9', 'minicap'], timeout=3)
        except Exception:
            pass

    def _setup_port_forward(self) -> bool:
        try:
            r = _run_adb(self.adb_base + ['forward', f'tcp:{_MINICAP_PORT}', 'localabstract:minicap'], timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _start_service(self):
        cmd = self.adb_base + ['shell',
            f'LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/minicap '
            f'-P {self.resolution}@{self.resolution}/0']
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)

    def _recv_exact(self, n: int, timeout: float = 5.0) -> bytes:
        if self.socket is None:
            raise IOError('socket not connected')
        self.socket.settimeout(timeout)
        data = b''
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if not chunk:
                raise IOError('socket closed')
            data += chunk
        return data

    def _read_banner(self):
        data = self._recv_exact(24)
        self.width = struct.unpack('<I', data[14:18])[0]
        self.height = struct.unpack('<I', data[18:22])[0]

    def _reader_loop(self):
        while not self.stop_flag.is_set():
            try:
                header = self._recv_exact(4, timeout=2.0)
                frame_len = struct.unpack('<I', header)[0]
                if frame_len == 0 or frame_len > 20_000_000:
                    continue
                jpeg = self._recv_exact(frame_len, timeout=2.0)
                img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    with self.frame_lock:
                        self.frame_buffer = img
                        self.frames_received += 1
                        self.last_frame_ts = time.time()
            except Exception:
                if not self.stop_flag.is_set():
                    break

    def start(self) -> bool:
        if not self.check_installed():
            return False
        self._kill_existing()
        time.sleep(0.2)
        if not self._setup_port_forward():
            return False
        self._start_service()
        time.sleep(1.2)
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect(('localhost', _MINICAP_PORT))
            self._read_banner()
        except Exception:
            self.stop()
            return False
        self.stop_flag.clear()
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with self.frame_lock:
                if self.frame_buffer is not None:
                    return True
            time.sleep(0.05)
        self.stop()
        return False

    def read(self):
        with self.frame_lock:
            if self.frame_buffer is None:
                return None
            if time.time() - self.last_frame_ts > 3.0:
                return None
            return self.frame_buffer.copy()

    def is_healthy(self) -> bool:
        with self.frame_lock:
            return (self.frame_buffer is not None
                    and time.time() - self.last_frame_ts < 3.0)

    def stop(self):
        self.stop_flag.set()
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        try:
            _run_adb(self.adb_base + ['shell', 'killall', '-9', 'minicap'], timeout=3)
        except Exception:
            pass
