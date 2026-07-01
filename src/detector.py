"""Hybrid Obstacle Detector (Phase 2)

Layered detection combining MOG2 background subtraction, Canny edge density,
and template matching via a configurable weighted voting system.

Author: reconstructed for cookiegame port.
"""
import collections
import json
import os
import shutil
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


DEFAULT_CONFIG: Dict[str, Any] = {
    'config_version': 1,
    'detection': {
        'enabled': True,
        'detection_hz': 10,
        'warmup_seconds': 8,
    },
    'zones': {
        'high': [500, 200, 900, 450],
        'low':  [500, 500, 900, 650],
    },
    'mog2': {
        'history': 500,
        'var_threshold': 25,
        'detect_shadows': False,
        'min_pixels_trigger': 500,
    },
    'canny': {
        'low_threshold': 50,
        'high_threshold': 150,
        'min_edges_trigger': 300,
    },
    'template': {
        'ingame2_threshold': 0.75,
    },
    'voting': {
        'weights': {'template': 3, 'mog2': 2, 'canny': 1},
        'action_threshold': 3,
    },
    'cooldowns': {
        'jump': 0.4,
        'slide': 0.8,
        'double_jump': 0.6,
    },
    'double_jump': {
        'random_probability': 0.30,
        'gap_seconds': 0.12,
    },
    'crash_log': {
        'enabled': True,
        'short_run_threshold_sec': 8,
        'save_last_n_frames': 10,
        'save_decision_log': True,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _read_yaml(path: str) -> Optional[Dict[str, Any]]:
    if not HAS_YAML:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f'[config] อ่าน {path} ไม่ได้: {e}')
        return None


def load_config(user_config_path: str, bundled_config_path: str) -> Tuple[Dict[str, Any], str]:
    """2-tier config loader with fallback.

    Priority order:
      1. User override at user_config_path
      2. Bundled default at bundled_config_path
      3. Hardcoded DEFAULT_CONFIG (last resort)

    First-run behavior: if bundled exists but user doesn't, copy bundled to user path.
    On YAML parse errors: fall back to next tier and continue.

    Returns:
      (merged_config_dict, source_description_string)
    """
    config = dict(DEFAULT_CONFIG)
    source = 'hardcoded default'

    bundled_data = None
    if bundled_config_path and os.path.exists(bundled_config_path):
        bundled_data = _read_yaml(bundled_config_path)
        if bundled_data:
            config = _deep_merge(config, bundled_data)
            source = f'bundled: {bundled_config_path}'

    if user_config_path:
        if os.path.exists(user_config_path):
            user_data = _read_yaml(user_config_path)
            if user_data:
                config = _deep_merge(config, user_data)
                source = f'user override: {user_config_path}'
            else:
                print(f'[config] user config พัง -> fallback bundled')
        elif bundled_config_path and os.path.exists(bundled_config_path):
            try:
                os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
                shutil.copy2(bundled_config_path, user_config_path)
                print(f'[config] first run -> copied default to {user_config_path}')
            except Exception as e:
                print(f'[config] copy default ล้ม: {e}')

    return config, source


class ObstacleDetector:
    """Hybrid MOG2 + Canny + Template + Voting detector.

    Usage:
      detector = ObstacleDetector(config)
      # per round:
      detector.reset_round()
      while running:
          detector.push_frame(screen)
          action, score, votes = detector.detect(screen, template_slide_match=bool(tmpl_hit))
          if action == 'slide': adb_slide()
          elif action == 'jump': adb_tap(...)
      # on crash:
      detector.save_crash_log(crash_dir, run_duration)
    """

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.enabled = config['detection'].get('enabled', True)
        self.warmup_seconds = float(config['detection'].get('warmup_seconds', 8))
        hz = max(1, int(config['detection'].get('detection_hz', 10)))
        self._detect_interval = 1.0 / hz

        m = config['mog2']
        self._mog2_kwargs = dict(
            history=int(m['history']),
            varThreshold=float(m['var_threshold']),
            detectShadows=bool(m['detect_shadows']),
        )
        self.min_mog2_pixels = int(m['min_pixels_trigger'])
        self.mog2_high = cv2.createBackgroundSubtractorMOG2(**self._mog2_kwargs)
        self.mog2_low = cv2.createBackgroundSubtractorMOG2(**self._mog2_kwargs)

        c = config['canny']
        self.canny_low = int(c['low_threshold'])
        self.canny_high = int(c['high_threshold'])
        self.min_canny_edges = int(c['min_edges_trigger'])

        v = config['voting']
        self.w_template = int(v['weights']['template'])
        self.w_mog2 = int(v['weights']['mog2'])
        self.w_canny = int(v['weights']['canny'])
        self.action_threshold = int(v['action_threshold'])

        self.cd_jump = float(config['cooldowns']['jump'])
        self.cd_slide = float(config['cooldowns']['slide'])

        cl = config['crash_log']
        self.crash_log_enabled = bool(cl['enabled'])
        self.short_run_threshold = float(cl['short_run_threshold_sec'])
        self.save_last_n_frames = int(cl['save_last_n_frames'])
        self.save_decision_log = bool(cl['save_decision_log'])

        d = config.get('debug', {}) or {}
        self.debug_enabled = bool(d.get('enabled', False))
        self.log_every_detection = bool(d.get('log_every_detection', False))
        self.log_zone_stats = bool(d.get('log_zone_stats', False))
        self.save_all_runs = bool(d.get('save_all_runs', False))
        self.save_debug_frames = bool(d.get('save_debug_frames', False))

        self.round_start = time.time()
        self.last_detect = 0.0
        self.last_jump = 0.0
        self.last_slide = 0.0
        self._frame_buffer = collections.deque(maxlen=self.save_last_n_frames)
        self._decision_log: list = []
        self.total_detections = 0
        self.cooldown_blocks = 0
        self.action_counts = {'jump': 0, 'slide': 0, 'double_jump': 0}
        self.jump_score_history: list = []
        self.slide_score_history: list = []
        self.first_frame = None
        self.last_frame = None
        self.timing_stats: Dict[str, list] = {
            'screencap_ms': [],
            'template_ms': [],
            'template_result_ms': [],
            'template_relay_ms': [],
            'template_pit_ms': [],
            'template_ingame2_ms': [],
            'crop_ms': [],
            'mog2_ms': [],
            'canny_ms': [],
            'detect_total_ms': [],
            'loop_total_ms': [],
        }
        self._last_timing_print = 0

    def reset_round(self):
        self.round_start = time.time()
        self.last_detect = 0.0
        self.last_jump = 0.0
        self.last_slide = 0.0
        self._frame_buffer.clear()
        self._decision_log.clear()
        self.total_detections = 0
        self.cooldown_blocks = 0
        self.action_counts = {'jump': 0, 'slide': 0, 'double_jump': 0}
        self.jump_score_history = []
        self.slide_score_history = []
        self.first_frame = None
        self.last_frame = None
        for _k in self.timing_stats:
            self.timing_stats[_k] = []
        self._last_timing_print = 0
        self.mog2_high = cv2.createBackgroundSubtractorMOG2(**self._mog2_kwargs)
        self.mog2_low = cv2.createBackgroundSubtractorMOG2(**self._mog2_kwargs)

    def push_frame(self, screen):
        if screen is not None:
            try:
                snapshot = screen.copy()
                if self.first_frame is None:
                    self.first_frame = snapshot
                self.last_frame = snapshot
                self._frame_buffer.append((time.time(), snapshot))
            except Exception:
                pass

    def notify_double_jump(self):
        self.action_counts['double_jump'] += 1

    def _crop_zone(self, screen, zone_key: str):
        z = self.cfg['zones'][zone_key]
        x1, y1, x2, y2 = int(z[0]), int(z[1]), int(z[2]), int(z[3])
        h, w = screen.shape[:2]
        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))
        return screen[y1:y2, x1:x2]

    def _mog2_pixels(self, zone_img, mog2) -> int:
        fg = mog2.apply(zone_img)
        return int(np.count_nonzero(fg))

    def _canny_edges(self, zone_img) -> int:
        if zone_img.ndim == 3:
            gray = cv2.cvtColor(zone_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = zone_img
        edges = cv2.Canny(gray, self.canny_low, self.canny_high)
        return int(np.count_nonzero(edges))

    def detect(self, screen, template_slide_match: bool = False) -> Tuple[Optional[str], int, Dict[str, Any]]:
        """Main entry. Returns (action|None, total_score, votes_debug_dict).

        Args:
          screen: BGR frame from adb_screencap()
          template_slide_match: whether ingame2.png matched (caller pre-computes)
        """
        if not self.enabled or screen is None:
            return None, 0, {'enabled': self.enabled}

        now = time.time()
        elapsed = now - self.round_start

        if now - self.last_detect < self._detect_interval:
            return None, 0, {'throttled': True}
        self.last_detect = now

        _t_detect_start = time.perf_counter()
        _t = time.perf_counter()
        try:
            hz = self._crop_zone(screen, 'high')
            lz = self._crop_zone(screen, 'low')
        except Exception as e:
            return None, 0, {'crop_error': str(e)}
        self.timing_stats['crop_ms'].append((time.perf_counter() - _t) * 1000)

        _t = time.perf_counter()
        mog2_hi_px = self._mog2_pixels(hz, self.mog2_high)
        mog2_lo_px = self._mog2_pixels(lz, self.mog2_low)
        self.timing_stats['mog2_ms'].append((time.perf_counter() - _t) * 1000)

        in_warmup = elapsed < self.warmup_seconds
        _t = time.perf_counter()
        canny_hi_ed = self._canny_edges(hz)
        canny_lo_ed = self._canny_edges(lz)
        self.timing_stats['canny_ms'].append((time.perf_counter() - _t) * 1000)

        self.total_detections += 1

        slide_score = 0
        slide_votes: Dict[str, Any] = {}
        if template_slide_match:
            slide_score += self.w_template
            slide_votes['template'] = True
        if not in_warmup and mog2_lo_px > self.min_mog2_pixels:
            slide_score += self.w_mog2
            slide_votes['mog2_px'] = mog2_lo_px
        if canny_lo_ed > self.min_canny_edges:
            slide_score += self.w_canny
            slide_votes['canny_edges'] = canny_lo_ed

        jump_score = 0
        jump_votes: Dict[str, Any] = {}
        if not in_warmup and mog2_hi_px > self.min_mog2_pixels:
            jump_score += self.w_mog2
            jump_votes['mog2_px'] = mog2_hi_px
        if canny_hi_ed > self.min_canny_edges:
            jump_score += self.w_canny
            jump_votes['canny_edges'] = canny_hi_ed

        self.jump_score_history.append(jump_score)
        self.slide_score_history.append(slide_score)

        cooldown_blocked_slide = False
        cooldown_blocked_jump = False
        chosen_action: Optional[str] = None
        chosen_score = 0
        chosen_votes: Dict[str, Any] = {}

        candidates = []
        if jump_score >= self.action_threshold:
            if (now - self.last_jump) > self.cd_jump:
                candidates.append(('jump', jump_score, jump_votes))
            else:
                cooldown_blocked_jump = True
                self.cooldown_blocks += 1
        if slide_score >= self.action_threshold:
            if (now - self.last_slide) > self.cd_slide:
                candidates.append(('slide', slide_score, slide_votes))
            else:
                cooldown_blocked_slide = True
                self.cooldown_blocks += 1

        if candidates:
            candidates.sort(key=lambda c: (c[1], 1 if c[0] == 'jump' else 0), reverse=True)
            chosen_action, chosen_score, chosen_votes = candidates[0]
            if chosen_action == 'jump':
                self.last_jump = now
                self.action_counts['jump'] += 1
            else:
                self.last_slide = now
                self.action_counts['slide'] += 1

        entry = {
            'time': round(elapsed, 3),
            'ts': now,
            'in_warmup': in_warmup,
            'jump_score': jump_score,
            'slide_score': slide_score,
            'mog2_jump_pixels': mog2_hi_px,
            'mog2_slide_pixels': mog2_lo_px,
            'canny_jump_edges': canny_hi_ed,
            'canny_slide_edges': canny_lo_ed,
            'template_match': bool(template_slide_match) if template_slide_match else None,
            'cooldown_blocked': bool(cooldown_blocked_slide or cooldown_blocked_jump),
            'action': chosen_action,
            'decision': 'ACTION' if chosen_action else ('COOLDOWN' if (cooldown_blocked_slide or cooldown_blocked_jump) else 'SKIP'),
        }
        self._decision_log.append(entry)

        if self.debug_enabled and self.log_every_detection:
            self._print_detect_line(elapsed, jump_score, slide_score,
                                    mog2_hi_px, mog2_lo_px, canny_hi_ed, canny_lo_ed,
                                    bool(template_slide_match), chosen_action,
                                    cooldown_blocked_slide or cooldown_blocked_jump,
                                    in_warmup)

        self.timing_stats['detect_total_ms'].append((time.perf_counter() - _t_detect_start) * 1000)
        self._maybe_print_timing()

        if chosen_action is not None:
            return chosen_action, chosen_score, chosen_votes
        return None, 0, {
            'slide_score': slide_score,
            'jump_score': jump_score,
            'mog2_hi': mog2_hi_px,
            'mog2_lo': mog2_lo_px,
            'canny_hi': canny_hi_ed,
            'canny_lo': canny_lo_ed,
            'cooldown_blocked': cooldown_blocked_slide or cooldown_blocked_jump,
            'warmup': in_warmup,
        }

    def record_external_timing(self, name: str, ms: float):
        if name in self.timing_stats:
            self.timing_stats[name].append(float(ms))

    def _avg(self, xs):
        return round(float(sum(xs) / len(xs)), 2) if xs else 0.0

    def _p95(self, xs):
        if not xs:
            return 0.0
        s = sorted(xs)
        idx = min(int(len(s) * 0.95), len(s) - 1)
        return round(float(s[idx]), 2)

    def get_timing_summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, xs in self.timing_stats.items():
            out[f'avg_{k}'] = self._avg(xs)
            out[f'p95_{k}'] = self._p95(xs)
            out[f'count_{k}'] = len(xs)
        avg_loop = self._avg(self.timing_stats['loop_total_ms'])
        out['effective_detection_hz'] = round(1000.0 / avg_loop, 2) if avg_loop > 0 else 0.0
        return out

    def _maybe_print_timing(self):
        if not (self.debug_enabled and self.log_every_detection):
            return
        if self.total_detections - self._last_timing_print < 10:
            return
        self._last_timing_print = self.total_detections
        tg = self.get_timing_summary()
        print(f'[timing] screencap_ms={tg["avg_screencap_ms"]:.0f} '
              f'template_ms={tg["avg_template_ms"]:.0f} '
              f'crop_ms={tg["avg_crop_ms"]:.1f} '
              f'mog2_ms={tg["avg_mog2_ms"]:.1f} '
              f'canny_ms={tg["avg_canny_ms"]:.1f} '
              f'detect_total_ms={tg["avg_detect_total_ms"]:.1f} '
              f'loop_ms={tg["avg_loop_total_ms"]:.0f} '
              f'effective_hz={tg["effective_detection_hz"]}')

    def _print_detect_line(self, elapsed, jump_score, slide_score,
                           mog2_hi, mog2_lo, canny_hi, canny_lo,
                           tmpl_hit, action, cooldown_blocked, in_warmup):
        prefix = f'[detect] t={elapsed:5.2f}s'
        if in_warmup:
            prefix += ' (warmup)'
        if self.log_zone_stats:
            j_stat = f'mog2={mog2_hi}({"HIT" if mog2_hi > self.min_mog2_pixels else "-"}) '\
                     f'canny={canny_hi}({"HIT" if canny_hi > self.min_canny_edges else "-"})'
            s_stat = f'mog2={mog2_lo}({"HIT" if mog2_lo > self.min_mog2_pixels else "-"}) '\
                     f'canny={canny_lo}({"HIT" if canny_lo > self.min_canny_edges else "-"}) '\
                     f'tmpl={"YES" if tmpl_hit else "-"}'
        else:
            j_stat = ''
            s_stat = ''
        if action == 'jump':
            tag = 'ACTION'
        elif action == 'slide':
            tag = 'ACTION'
        elif cooldown_blocked:
            tag = 'COOLDOWN'
        else:
            tag = 'SKIP'
        need = self.action_threshold
        print(f'{prefix} Jump: {j_stat} score={jump_score} need={need} | '
              f'Slide: {s_stat} score={slide_score} need={need} -> {tag}'
              + (f' ({action.upper()})' if action else ''))

    def save_crash_log(self, crash_dir: str, run_duration: float) -> bool:
        if not self.crash_log_enabled:
            return False
        if run_duration >= self.short_run_threshold:
            return False
        try:
            os.makedirs(crash_dir, exist_ok=True)
            for i, (ts, frame) in enumerate(self._frame_buffer):
                p = os.path.join(crash_dir, f'frame_{i:02d}.png')
                cv2.imwrite(p, frame)
            if self.save_decision_log:
                p = os.path.join(crash_dir, 'decisions.json')
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(self._decision_log, f, indent=2, default=str)
            meta = {
                'run_duration_sec': round(run_duration, 3),
                'crash_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'frames_saved': len(self._frame_buffer),
                'decisions_count': len(self._decision_log),
                'config_snapshot': {
                    'action_threshold': self.action_threshold,
                    'weights': {
                        'template': self.w_template,
                        'mog2': self.w_mog2,
                        'canny': self.w_canny,
                    },
                    'zones': self.cfg['zones'],
                    'mog2': self.cfg['mog2'],
                    'canny': self.cfg['canny'],
                },
            }
            with open(os.path.join(crash_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
            print(f'[crash-log] saved -> {crash_dir} (duration={run_duration:.2f}s)')
            return True
        except Exception as e:
            print(f'[crash-log] save error: {e}')
            return False

    def _draw_roi_overlay(self, frame):
        try:
            view = frame.copy()
            hz = self.cfg['zones']['high']
            lz = self.cfg['zones']['low']
            cv2.rectangle(view, (int(hz[0]), int(hz[1])), (int(hz[2]), int(hz[3])), (0, 255, 255), 2)
            cv2.rectangle(view, (int(lz[0]), int(lz[1])), (int(lz[2]), int(lz[3])), (0, 200, 255), 2)
            cv2.putText(view, 'HIGH (Jump)', (int(hz[0]), int(hz[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(view, 'LOW (Slide)', (int(lz[0]), int(lz[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            return view
        except Exception:
            return frame

    def get_summary(self, run_duration: float, config_path: Optional[str] = None) -> Dict[str, Any]:
        def _avg(xs):
            return round(float(sum(xs) / len(xs)), 3) if xs else 0.0
        tg = self.get_timing_summary()
        return {
            'run_duration': round(float(run_duration), 3),
            'total_detections': int(self.total_detections),
            'actions': dict(self.action_counts),
            'skipped_by_cooldown': int(self.cooldown_blocks),
            'avg_jump_score': _avg(self.jump_score_history),
            'avg_slide_score': _avg(self.slide_score_history),
            'action_threshold': int(self.action_threshold),
            'weights': {'template': self.w_template, 'mog2': self.w_mog2, 'canny': self.w_canny},
            'zones': dict(self.cfg['zones']),
            'config_path': config_path or '',
            'effective_detection_hz': tg.get('effective_detection_hz', 0.0),
            'avg_screencap_ms': tg.get('avg_screencap_ms', 0.0),
            'avg_template_ms': tg.get('avg_template_ms', 0.0),
            'avg_detect_total_ms': tg.get('avg_detect_total_ms', 0.0),
            'avg_loop_total_ms': tg.get('avg_loop_total_ms', 0.0),
        }

    def save_run_log(self, run_dir: str, run_duration: float, config_path: Optional[str] = None) -> bool:
        if not self.save_all_runs:
            return False
        try:
            os.makedirs(run_dir, exist_ok=True)

            if self.save_debug_frames:
                if self.first_frame is not None:
                    cv2.imwrite(os.path.join(run_dir, 'roi_debug_start.png'),
                                self._draw_roi_overlay(self.first_frame))
                if self.last_frame is not None:
                    cv2.imwrite(os.path.join(run_dir, 'roi_debug_last.png'),
                                self._draw_roi_overlay(self.last_frame))

            with open(os.path.join(run_dir, 'decisions.json'), 'w', encoding='utf-8') as f:
                json.dump(self._decision_log, f, indent=2, default=str, ensure_ascii=False)

            summary = self.get_summary(run_duration, config_path)
            with open(os.path.join(run_dir, 'summary.json'), 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            timing_summary = self.get_timing_summary()
            with open(os.path.join(run_dir, 'timing_summary.json'), 'w', encoding='utf-8') as f:
                json.dump(timing_summary, f, indent=2, ensure_ascii=False)

            if config_path and os.path.isfile(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as src, \
                         open(os.path.join(run_dir, 'config_used.yaml'), 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
                except Exception:
                    pass

            print(f'[run-log] saved -> {run_dir} '
                  f'(detections={self.total_detections} '
                  f'actions=J{self.action_counts["jump"]}/S{self.action_counts["slide"]}/DJ{self.action_counts["double_jump"]} '
                  f'duration={run_duration:.2f}s)')
            return True
        except Exception as e:
            print(f'[run-log] save error: {e}')
            return False
