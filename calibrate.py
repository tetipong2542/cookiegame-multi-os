import argparse
import os
import sys
import json

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
from detector import load_config


def _crop_zone(img, zone):
    x1, y1, x2, y2 = int(zone[0]), int(zone[1]), int(zone[2]), int(zone[3])
    h, w = img.shape[:2]
    x1 = max(0, min(x1, w))
    y1 = max(0, min(y1, h))
    x2 = max(x1, min(x2, w))
    y2 = max(y1, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]


def _mog2_pixels_once(zone_img, cfg):
    mog2 = cv2.createBackgroundSubtractorMOG2(
        history=int(cfg['mog2']['history']),
        varThreshold=float(cfg['mog2']['var_threshold']),
        detectShadows=bool(cfg['mog2']['detect_shadows']),
    )
    for _ in range(5):
        mog2.apply(zone_img)
    fg = mog2.apply(zone_img)
    return int(np.count_nonzero(fg))


def _canny_edges(zone_img, cfg):
    gray = cv2.cvtColor(zone_img, cv2.COLOR_BGR2GRAY) if zone_img.ndim == 3 else zone_img
    edges = cv2.Canny(gray, int(cfg['canny']['low_threshold']), int(cfg['canny']['high_threshold']))
    return int(np.count_nonzero(edges))


def _template_match(img, tmpl_path, threshold):
    if not os.path.isfile(tmpl_path):
        return None
    tmpl = cv2.imread(tmpl_path, cv2.IMREAD_COLOR)
    if tmpl is None:
        return None
    result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return {'score': float(max_val), 'hit': bool(max_val >= threshold)}


def analyze_frame(img, cfg, label='frame'):
    hz = _crop_zone(img, cfg['zones']['high'])
    lz = _crop_zone(img, cfg['zones']['low'])
    if hz is None or lz is None:
        print(f'  [{label}] zone crop failed (image too small?)')
        return None

    mog2_hi = _mog2_pixels_once(hz, cfg)
    mog2_lo = _mog2_pixels_once(lz, cfg)
    canny_hi = _canny_edges(hz, cfg)
    canny_lo = _canny_edges(lz, cfg)

    min_mog2 = int(cfg['mog2']['min_pixels_trigger'])
    min_canny = int(cfg['canny']['min_edges_trigger'])
    w_tmpl = int(cfg['voting']['weights']['template'])
    w_mog2 = int(cfg['voting']['weights']['mog2'])
    w_canny = int(cfg['voting']['weights']['canny'])
    thr = int(cfg['voting']['action_threshold'])

    tmpl_result = _template_match(img, 'templates/ingame2.png', float(cfg['template']['ingame2_threshold']))

    slide_score = 0
    if tmpl_result and tmpl_result['hit']:
        slide_score += w_tmpl
    if mog2_lo > min_mog2:
        slide_score += w_mog2
    if canny_lo > min_canny:
        slide_score += w_canny

    jump_score = 0
    if mog2_hi > min_mog2:
        jump_score += w_mog2
    if canny_hi > min_canny:
        jump_score += w_canny

    report = {
        'label': label,
        'shape': list(img.shape[:2]),
        'zones': {
            'high': cfg['zones']['high'],
            'low': cfg['zones']['low'],
        },
        'jump': {
            'mog2_pixels': mog2_hi,
            'mog2_hit': mog2_hi > min_mog2,
            'canny_edges': canny_hi,
            'canny_hit': canny_hi > min_canny,
            'score': jump_score,
            'decision': 'JUMP' if jump_score >= thr else 'NO JUMP',
        },
        'slide': {
            'mog2_pixels': mog2_lo,
            'mog2_hit': mog2_lo > min_mog2,
            'canny_edges': canny_lo,
            'canny_hit': canny_lo > min_canny,
            'template': tmpl_result,
            'score': slide_score,
            'decision': 'SLIDE' if slide_score >= thr else 'NO SLIDE',
        },
        'thresholds': {
            'min_mog2_pixels': min_mog2,
            'min_canny_edges': min_canny,
            'action_threshold': thr,
        },
    }
    return report


def print_report(report):
    print(f'\n=== {report["label"]} ({report["shape"][1]}x{report["shape"][0]}) ===')
    j = report['jump']
    s = report['slide']
    print(f'Jump Zone {report["zones"]["high"]}:')
    print(f'  MOG2 pixels : {j["mog2_pixels"]:>6}  {"HIT" if j["mog2_hit"] else "MISS"}')
    print(f'  Canny edges : {j["canny_edges"]:>6}  {"HIT" if j["canny_hit"] else "MISS"}')
    print(f'  Score       : {j["score"]}  -> {j["decision"]}')
    print(f'Slide Zone {report["zones"]["low"]}:')
    print(f'  MOG2 pixels : {s["mog2_pixels"]:>6}  {"HIT" if s["mog2_hit"] else "MISS"}')
    print(f'  Canny edges : {s["canny_edges"]:>6}  {"HIT" if s["canny_hit"] else "MISS"}')
    if s['template'] is not None:
        t = s['template']
        print(f'  Template    : score={t["score"]:.3f}  {"HIT" if t["hit"] else "MISS"}')
    else:
        print(f'  Template    : (skipped - ingame2.png missing)')
    print(f'  Score       : {s["score"]}  -> {s["decision"]}')


def save_overlay(img, cfg, out_path):
    view = img.copy()
    hz = cfg['zones']['high']
    lz = cfg['zones']['low']
    cv2.rectangle(view, (int(hz[0]), int(hz[1])), (int(hz[2]), int(hz[3])), (0, 255, 255), 2)
    cv2.rectangle(view, (int(lz[0]), int(lz[1])), (int(lz[2]), int(lz[3])), (0, 200, 255), 2)
    cv2.putText(view, 'HIGH (Jump)', (int(hz[0]), int(hz[1]) - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(view, 'LOW (Slide)', (int(lz[0]), int(lz[1]) - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
    cv2.imwrite(out_path, view)
    print(f'  overlay saved -> {out_path}')


def main():
    p = argparse.ArgumentParser(description='Calibrate ObstacleDetector against real frames')
    p.add_argument('--input', help='single frame to analyze')
    p.add_argument('--safe', help='screenshot of safe background (no obstacle)')
    p.add_argument('--jump', help='screenshot with jump-required obstacle')
    p.add_argument('--slide', help='screenshot with slide-required obstacle')
    p.add_argument('--config', default='config.yaml', help='path to config.yaml (default: config.yaml)')
    p.add_argument('--overlay', action='store_true', help='save ROI overlay PNG next to input(s)')
    p.add_argument('--json', help='write full report as JSON to this path')
    args = p.parse_args()

    cfg, source = load_config(args.config, args.config)
    print(f'Config source: {source}')
    print(f'Zones: HIGH={cfg["zones"]["high"]}  LOW={cfg["zones"]["low"]}')
    print(f'Voting weights: template={cfg["voting"]["weights"]["template"]}  '
          f'mog2={cfg["voting"]["weights"]["mog2"]}  canny={cfg["voting"]["weights"]["canny"]}')
    print(f'Action threshold: {cfg["voting"]["action_threshold"]}')

    inputs = []
    if args.input:
        inputs.append(('input', args.input))
    if args.safe:
        inputs.append(('safe', args.safe))
    if args.jump:
        inputs.append(('jump_expected', args.jump))
    if args.slide:
        inputs.append(('slide_expected', args.slide))

    if not inputs:
        p.error('provide at least --input or --safe/--jump/--slide')

    reports = []
    for label, path in inputs:
        if not os.path.isfile(path):
            print(f'  [{label}] not found: {path}')
            continue
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            print(f'  [{label}] failed to read: {path}')
            continue
        rep = analyze_frame(img, cfg, label=label)
        if rep is not None:
            print_report(rep)
            reports.append(rep)
        if args.overlay:
            out_path = os.path.splitext(path)[0] + '_overlay.png'
            save_overlay(img, cfg, out_path)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(reports, f, indent=2)
        print(f'\nJSON report saved -> {args.json}')


if __name__ == '__main__':
    main()
