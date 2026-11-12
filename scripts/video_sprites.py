#!/usr/bin/env python3
"""Inspect a video or export configured actions to an engine-neutral sprite pack."""
# Motion arc-length, loop-pair search and channel-cap despill adapted from
# gary149/h3-game-sprites, Copyright (c) 2026 Victor Mustar, MIT.
# See ../THIRD_PARTY_NOTICES.md for the upstream revision and full license.
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw


MASK_PIPELINE_VERSION = 2


def despill(rgb, alpha, settings):
    """Adapt upstream channel caps; default to the visible silhouette edge."""
    color = settings.get('color')
    scope = settings.get('scope', 'edge')
    strength = float(settings.get('strength', 1))
    radius = int(settings.get('radius', 2))
    cap_scale = float(settings.get('cap_scale', 1.18))
    cap_offset = float(settings.get('cap_offset', 30))
    if color not in ('magenta', 'green') or scope not in ('edge', 'all'):
        raise ValueError('despill needs color=magenta|green and scope=edge|all')
    if (not 0 <= strength <= 1 or radius < 1 or radius > 32 or
            not math.isfinite(cap_scale) or cap_scale < 0 or
            not math.isfinite(cap_offset) or cap_offset < 0):
        raise ValueError('Invalid despill strength/radius/channel cap')
    a = rgb.astype(np.float32)
    r, g, b = (a[..., k].copy() for k in range(3))
    cap = (g if color == 'magenta' else np.maximum(r, b)) * cap_scale + cap_offset
    corrected = a.copy()
    for channel in ((0, 2) if color == 'magenta' else (1,)):
        corrected[..., channel] = np.minimum(a[..., channel], cap)
    affected = alpha > 0
    if scope == 'edge':
        near_clear = cv2.dilate((alpha == 0).astype(np.uint8),
                                np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)) > 0
        affected &= near_clear | (alpha < 255)
    a[affected] += strength * (corrected[affected] - a[affected])
    return np.clip(a, 0, 255).astype(np.uint8)


def probe(source):
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams',
           '-show_frames', '-show_entries',
           'stream=width,height,avg_frame_rate:frame=best_effort_timestamp_time,pkt_duration_time',
           '-of', 'json', str(source)]
    data = json.loads(subprocess.check_output(cmd))
    if not data.get('streams') or not data.get('frames'):
        raise ValueError('No decodable video frames')
    stream, frames = data['streams'][0], data['frames']
    if any('best_effort_timestamp_time' not in f for f in frames):
        raise ValueError('Actual frame timestamps unavailable; do not assume a frame rate')
    times = np.array([float(f['best_effort_timestamp_time']) for f in frames])
    times -= times[0]
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError('Need at least two frames with increasing timestamps')
    last_duration = float(frames[-1].get('pkt_duration_time', 0))
    if last_duration <= 0:
        last_duration = float(np.median(np.diff(times)))
    return {'width': stream['width'], 'height': stream['height'],
            'averageFrameRate': stream.get('avg_frame_rate'), 'frameCount': len(times),
            'timestamps': times.tolist(), 'duration': float(times[-1] + last_duration),
            'lastFrameDuration': last_duration}


def read_frame(cap, index):
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
    ok, frame = cap.read()
    if not ok:
        raise ValueError(f'Cannot decode source frame {index}')
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def inspect(source, work, samples):
    work.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    (work / 'probe.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    cap = cv2.VideoCapture(str(source))
    count = min(samples, info['frameCount'])
    indices = np.linspace(0, info['frameCount'] - 1, count).round().astype(int)
    cols = min(4, count)
    width, height = 320, 220
    board = Image.new('RGB', (width * cols, height * math.ceil(count / cols)), '#252a32')
    draw = ImageDraw.Draw(board)
    try:
        for k, index in enumerate(indices):
            frame = read_frame(cap, index)
            frame.thumbnail((width, height - 26))
            x, y = k % cols * width, k // cols * height
            board.paste(frame, (x + (width - frame.width) // 2, y))
            draw.text((x + 8, y + height - 23),
                      f'{info["timestamps"][index]:.3f}s  frame {index}', fill='white')
    finally:
        cap.release()
    board.save(work / 'contact.jpg', quality=90)
    print(json.dumps({k: v for k, v in info.items() if k != 'timestamps'}, indent=2))


def resolve(base, value):
    return (base / value).resolve()


def box(value, width, height):
    result = tuple(int(v) for v in value)
    if len(result) != 4 or not (0 <= result[0] < result[2] <= width and
                                 0 <= result[1] < result[3] <= height):
        raise ValueError(f'Invalid source rectangle: {result}')
    return result


def fill_holes(mask):
    padded = np.pad(mask.astype(np.uint8) * 255, 1)
    flood = padded.copy()
    cv2.floodFill(flood, None, (0, 0), 255)
    return np.maximum(padded, 255 - flood)[1:-1, 1:-1]


class Masker:
    def __init__(self, cfg, work, base):
        self.cfg, self.session = cfg, None
        self.mode = cfg.get('mode')
        if self.mode not in ('chroma', 'model', 'none'):
            raise ValueError('Choose mask.mode explicitly: chroma, model, none')
        if cfg.get('despill') is not None and (self.mode != 'chroma' or not isinstance(cfg['despill'], dict)):
            raise ValueError('despill is an explicit object supported only for chroma masks')
        if self.mode == 'model':
            import os
            from rembg import new_session
            model_dir = resolve(base, cfg['model_dir']) if cfg.get('model_dir') else work / 'models'
            os.environ['U2NET_HOME'] = str(model_dir)
            self.session = new_session(cfg.get('model', 'u2netp'))
        if self.mode == 'chroma':
            key = cfg.get('key')
            if not isinstance(key, list) or len(key) != 3 or any(not 0 <= v <= 255 for v in key):
                raise ValueError('Chroma key must be an RGB triple')

    def apply(self, image):
        rgb = np.array(image.convert('RGB'))
        height, width = rgb.shape[:2]
        if self.mode == 'none':
            alpha = np.full((height, width), 255, np.uint8)
        elif self.mode == 'chroma':
            distance = np.linalg.norm(rgb.astype(float) - np.array(self.cfg['key']), axis=2)
            softness = float(self.cfg.get('softness', 30))
            if softness <= 0:
                raise ValueError('softness must be positive')
            alpha = (255 * np.clip((distance - float(self.cfg.get('threshold', 70))) / softness, 0, 1)).astype(np.uint8)
        else:
            alpha = np.zeros((height, width), np.uint8)
            for region in self.cfg.get('regions', [{}]):
                rect = box(region.get('box', [0, 0, width, height]), width, height)
                pred = np.array(self.session.predict(image.crop(rect))[0])
                threshold = region.get('threshold')
                part = pred if threshold is None else ((pred > float(threshold)).astype(np.uint8) * 255)
                close = int(region.get('close', 0))
                if close > 0:
                    part = cv2.morphologyEx(part, cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
                if region.get('largest'):
                    n, labels, stats, _ = cv2.connectedComponentsWithStats((part > 0).astype(np.uint8), 8)
                    if n <= 1:
                        raise ValueError(f'Empty mask in region {rect}')
                    part = np.where(labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]), part, 0).astype(np.uint8)
                if region.get('fill_holes'):
                    if threshold is None:
                        raise ValueError('fill_holes requires an explicit binary threshold')
                    part = fill_holes(part > 0)
                x0, y0, x1, y1 = rect
                alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], part)
        inset = int(self.cfg.get('inset', 0))
        if inset < 0:
            raise ValueError('inset must be nonnegative')
        if inset:
            alpha = cv2.erode(alpha, np.ones((2 * inset + 1, 2 * inset + 1), np.uint8))
        if self.cfg.get('despill') is not None:
            rgb = despill(rgb, alpha, self.cfg['despill'])
        # Never fill a predicted hole using already-premultiplied RGB.
        return Image.fromarray(np.dstack((rgb, alpha)))


def interval_frames(move, info):
    times = np.array(info['timestamps'])
    start, end = float(move['start']), float(move['end'])
    count = int(move.get('count', 12))
    if not (0 <= start < end <= info['duration'] + 1e-6) or count < 1:
        raise ValueError('Invalid animation interval/count')
    eligible = np.flatnonzero((times >= start - 1e-8) & (times < end - 1e-8))
    if len(eligible) < count:
        raise ValueError('Interval has fewer source frames than requested')
    return start, end, count, eligible


def unique_quantiles(values, count, endpoint=True):
    """Monotone quantiles with reserved slots: exact count even on plateaus."""
    values = np.asarray(values, dtype=float)
    if count < 1 or count > len(values):
        raise ValueError('Not enough distinct source frames for requested count')
    targets = np.linspace(values[0], values[-1], count, endpoint=endpoint)
    picks, previous = [], -1
    for k, target in enumerate(targets):
        low, high = previous + 1, len(values) - (count - k)
        previous = (len(values) - 1 if endpoint and count > 1 and k == count - 1 else
                    low + int(np.argmin(np.abs(values[low:high + 1] - target))))
        picks.append(previous)
    return picks


def motion_features(rgba, rect):
    """Ignore hidden background RGB, retaining silhouettes and visible detail."""
    tile = rgba.crop(rect)
    tile.thumbnail((64, 64), Image.Resampling.BILINEAR)
    a = np.asarray(tile, dtype=np.float32) / 255
    return np.concatenate((a[..., :3] * a[..., 3:4], a[..., 3:4]), axis=2)


def loop_candidate(features, times, count, settings):
    """Search sustained motion for similar poses and compatible velocities.

    A numeric candidate is not a guarantee of a seamless/semantic gait cycle.
    Bounds are seconds, independent of source frame rate.
    """
    minimum, maximum = float(settings['min_duration']), float(settings['max_duration'])
    window = settings.get('window', [0.2, 0.85])
    activity_floor = float(settings.get('min_motion', 0.001))
    velocity_weight = float(settings.get('velocity_weight', 0.25))
    if (not 0 < minimum <= maximum or not math.isfinite(maximum) or
            len(window) != 2 or not 0 <= window[0] < window[1] <= 1 or
            not math.isfinite(activity_floor) or activity_floor <= 0 or
            not math.isfinite(velocity_weight) or velocity_weight < 0):
        raise ValueError('Invalid loop search duration/window/motion/velocity constraints')
    if count < 2:
        raise ValueError('Loop search needs at least two output frames')
    if len(features) > 1500:
        raise ValueError('Loop search interval too large; narrow to at most 1500 source frames')
    changes = np.mean(np.abs(np.diff(features, axis=0)), axis=(1, 2, 3))
    cumulative = np.r_[0., np.cumsum(changes)]
    extent = times[-1] - times[0]
    candidates = np.flatnonzero((times >= times[0] + extent * window[0] - 1e-8) &
                               (times <= times[0] + extent * window[1] + 1e-8))
    typical_step = float(np.median(np.diff(times)))
    best = None
    for i in candidates:
        for j in candidates:
            duration = times[j] - times[i]
            if j - i < count or duration < minimum - 1e-8 or duration > maximum + 1e-8:
                continue
            activity = (cumulative[j] - cumulative[i]) / (j - i)
            if activity < activity_floor:
                continue
            pose = float(np.abs(features[i] - features[j]).mean())
            v_start = (features[i + 1] - features[i]) / (times[i + 1] - times[i])
            v_end = (features[j] - features[j - 1]) / (times[j] - times[j - 1])
            velocity = float(np.abs(v_start - v_end).mean()) * typical_step
            score = pose + velocity_weight * velocity
            if best is None or score < best['score']:
                best = {'i': int(i), 'j': int(j), 'score': score,
                        'poseDifference': pose, 'velocityDifference': velocity,
                        'meanMotionPerFrame': float(activity)}
    if best is None:
        raise ValueError('No moving loop candidate meets constraints; narrow/change bounds or select indices explicitly')
    return best


def select_frames(move, info, features=None, analysis=None):
    times = np.array(info['timestamps'])
    method = move.get('selection', 'uniform')
    if method not in ('uniform', 'motion', 'loop'):
        raise ValueError('selection must be uniform, motion or loop')
    if 'indices' in move and method != 'uniform':
        raise ValueError('Explicit indices cannot be combined with automatic selection')
    if 'loop_search' in move and method != 'loop':
        raise ValueError('loop_search requires selection=loop')
    timing_end = None
    if 'indices' in move:
        indices = [int(i) for i in move['indices']]
    else:
        start, end, count, eligible = interval_frames(move, info)
        if method == 'uniform':
            targets = np.linspace(start, end, count, endpoint=False)
            indices = [int(eligible[np.argmin(np.abs(times[eligible] - t))]) for t in targets]
            if len(set(indices)) != count:
                raise ValueError('Sampling repeats source frames; reduce count or select indices explicitly')
        else:
            if features is None or len(features) != len(eligible):
                raise ValueError('Masked source features required for automatic selection')
            if method == 'motion':
                energy = np.r_[0., np.mean(np.abs(np.diff(features, axis=0)), axis=(1, 2, 3))]
                arc = np.cumsum(energy)
                static = bool(arc[-1] <= 1e-8)
                positions = unique_quantiles(times[eligible] if static else arc, count)
                indices = eligible[positions].astype(int).tolist()
                timing_end = end
                if analysis is not None:
                    analysis.update({'method': method, 'totalMotion': float(arc[-1]),
                                     'staticFallback': static})
            else:
                if not move.get('loop'):
                    raise ValueError('selection=loop requires loop=true')
                settings = move.get('loop_search')
                if not isinstance(settings, dict) or not {'min_duration', 'max_duration'} <= settings.keys():
                    raise ValueError('selection=loop requires loop_search.min_duration and max_duration in seconds')
                candidate = loop_candidate(features, times[eligible], count, settings)
                i, j = candidate.pop('i'), candidate.pop('j')
                span = times[eligible[i:j]]
                targets = np.linspace(span[0], times[eligible[j]], count, endpoint=False)
                # Reserve enough distinct frames for each remaining target.
                positions, previous = [], -1
                for k, target in enumerate(targets):
                    low, high = previous + 1, len(span) - (count - k)
                    previous = low + int(np.argmin(np.abs(span[low:high + 1] - target)))
                    positions.append(i + previous)
                indices = eligible[positions].astype(int).tolist()
                timing_end = float(times[eligible[j]])
                if analysis is not None:
                    analysis.update({'method': method, 'candidateOnly': True,
                                     'startFrame': int(eligible[i]), 'endFrameExclusive': int(eligible[j]),
                                     'startSeconds': float(times[eligible[i]]), 'endSecondsExclusive': timing_end,
                                     **candidate})
    if not indices or indices != sorted(set(indices)) or indices[0] < 0 or indices[-1] >= len(times):
        raise ValueError('indices must be unique, increasing, and in bounds')
    if 'duration_ms' in move:
        durations = [float(d) for d in move['duration_ms']]
    elif 'duration' in move or ('indices' not in move and method == 'uniform'):
        duration = float(move.get('duration', move.get('end', 0) - move.get('start', 0)))
        durations = [1000 * duration / len(indices)] * len(indices)
    else:
        selected = times[indices]
        if timing_end is None:
            tail = times[indices[-1] + 1] - selected[-1] if indices[-1] + 1 < len(times) else info['lastFrameDuration']
            timing_end = selected[-1] + tail
        durations = (np.diff(np.append(selected, timing_end)) * 1000).tolist()
    if len(durations) != len(indices) or any(not math.isfinite(d) or d <= 0 for d in durations):
        raise ValueError('Need one positive finite duration_ms per frame')
    return indices, durations


def contact(atlas, dest):
    thumb = atlas.copy()
    thumb.thumbnail((1440, 1800))
    bg = Image.new('RGBA', thumb.size, '#deddd8')
    draw = ImageDraw.Draw(bg)
    for y in range(0, bg.height, 16):
        for x in range(0, bg.width, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill='#c6c8c7')
    bg.alpha_composite(thumb)
    bg.convert('RGB').save(dest, quality=90)


def quantize_durations(durations, quantum_ms):
    """Round cumulative boundaries, avoiding one rounding error per frame.

    Encodings cannot hold a positive frame shorter than their minimum quantum;
    these exceptional cases are reflected in previewTimingMs in the report.
    """
    total, emitted, result = 0.0, 0, []
    for duration in durations:
        total += duration
        ticks = max(1, round(total / quantum_ms) - emitted)
        emitted += ticks
        result.append(ticks * quantum_ms)
    return result


def export(config):
    cfg = json.loads(config.read_text(encoding='utf-8-sig'))
    base = config.parent
    source, work, output = (resolve(base, cfg[k]) for k in ('source', 'work', 'output'))
    if work == output or work.is_relative_to(output):
        raise ValueError('Work/cache must not be inside the deliverable folder')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory is not empty; choose a fresh output path')
    info = probe(source)
    width, height = info['width'], info['height']
    crop = box(cfg.get('crop', [0, 0, width, height]), width, height)
    cw, ch = [int(v) for v in cfg.get('canvas', [512, 512])]
    padding = int(cfg.get('padding', 8))
    if padding < 0 or min(cw, ch) <= 2 * padding:
        raise ValueError('Invalid canvas/padding')
    crop_w, crop_h = crop[2] - crop[0], crop[3] - crop[1]
    scale = float(cfg.get('scale', min((cw - 2 * padding) / crop_w, (ch - 2 * padding) / crop_h)))
    rw, rh = max(1, round(crop_w * scale)), max(1, round(crop_h * scale))
    if scale <= 0 or rw > cw - 2 * padding or rh > ch - 2 * padding:
        raise ValueError('Scale does not fit the fixed canvas')
    offset = ((cw - rw) // 2, (ch - rh) // 2)
    # Use effective x/y scale after integer resize rounding for precise pivots.
    px, py = cfg['pivot_source']
    pivot_x = (offset[0] + (px - crop[0]) * rw / crop_w) / cw
    pivot_y = 1 - (offset[1] + (py - crop[1]) * rh / crop_h) / ch
    if not (0 <= pivot_x <= 1 and 0 <= pivot_y <= 1):
        raise ValueError('Reference pivot lies outside the output canvas')
    moves = cfg.get('animations', [])
    names = [m['name'] for m in moves]
    if not names or len(names) != len(set(names)) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', n) for n in names):
        raise ValueError('Animation names must be unique safe identifiers')
    work.mkdir(parents=True, exist_ok=True)
    stat = source.stat()
    identity = {'source': str(source), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'mask': cfg['mask'], 'maskPipelineVersion': MASK_PIPELINE_VERSION}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    cache = work / 'masks' / fingerprint
    cache.mkdir(parents=True, exist_ok=True)
    masker = Masker(cfg['mask'], work, base)
    output.mkdir(parents=True, exist_ok=True)
    for folder in ('frames', 'atlases', 'previews'):
        (output / folder).mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(source))
    def masked(index):
        cached = cache / f'{index:08d}.png'
        if cached.exists():
            with Image.open(cached) as image:
                return image.convert('RGBA')
        rgba = masker.apply(read_frame(cap, index))
        rgba.save(cached)
        return rgba

    manifest = {'version': 1, 'width': cw, 'height': ch, 'pivotX': pivot_x, 'pivotY': pivot_y,
                'pixelsPerUnit': 100, 'maskMode': masker.mode, 'source': {k: v for k, v in info.items() if k != 'timestamps'},
                'transform': {'crop': crop, 'scale': scale, 'resized': [rw, rh], 'offset': offset}, 'animations': []}
    reports, payload = {}, {}
    try:
        for move in moves:
            analysis = {'method': 'indices' if 'indices' in move else 'uniform'}
            features = None
            if move.get('selection', 'uniform') in ('motion', 'loop'):
                if 'indices' in move:
                    raise ValueError('Explicit indices cannot be combined with automatic selection')
                _, _, _, eligible = interval_frames(move, info)
                if move.get('selection') == 'loop' and len(eligible) > 1500:
                    raise ValueError('Loop search interval too large; narrow to at most 1500 source frames')
                rect = box(move.get('analysis_crop', crop), width, height)
                features = np.stack([motion_features(masked(int(i)), rect) for i in eligible])
                analysis.update({'analysisCrop': rect, 'sourceFramesAnalyzed': len(eligible),
                                 'maskedFeatures': True})
            indices, durations = select_frames(move, info, features, analysis)
            name = move['name']
            frame_dir = output / 'frames' / name
            frame_dir.mkdir()
            cols = int(move.get('columns', min(6, len(indices))))
            if cols < 1:
                raise ValueError('columns must be positive')
            atlas = Image.new('RGBA', (cw * cols, ch * math.ceil(len(indices) / cols)))
            frames, files, meta, bounds = [], [], {}, []
            for k, index in enumerate(indices):
                rgba = masked(index)
                tile = rgba.crop(crop).resize((rw, rh), Image.Resampling.LANCZOS)
                frame = Image.new('RGBA', (cw, ch))
                frame.paste(tile, offset)
                filename = f'{name}_{k:04d}.png'
                frame.save(frame_dir / filename)
                files.append(f'frames/{name}/{filename}')
                x, y = k % cols * cw, k // cols * ch
                atlas.paste(frame, (x, y))
                bounds.append(frame.getchannel('A').getbbox())
                meta[filename] = {'frame': {'x': x, 'y': y, 'w': cw, 'h': ch},
                                  'rotated': False, 'trimmed': False,
                                  'spriteSourceSize': {'x': 0, 'y': 0, 'w': cw, 'h': ch},
                                  'sourceSize': {'w': cw, 'h': ch}, 'duration': durations[k],
                                  'sourceFrame': index, 'sourceTimeSeconds': info['timestamps'][index]}
                frames.append(frame)
            image_path = output / 'atlases' / f'{name}.png'
            atlas.save(image_path)
            atlas_data = {'frames': meta, 'meta': {'image': image_path.name, 'format': 'RGBA8888',
                'size': {'w': atlas.width, 'h': atlas.height}, 'scale': '1', 'loop': bool(move.get('loop'))}}
            (image_path.with_suffix('.json')).write_text(json.dumps(atlas_data, indent=2), encoding='utf-8')
            ms = quantize_durations(durations, 1)
            gif_ms = quantize_durations(durations, 10)
            frames[0].save(output / 'previews' / f'{name}.webp', save_all=True, append_images=frames[1:],
                           duration=ms, loop=0 if move.get('loop') else 1, lossless=True)
            gif = []
            for f in frames:
                bg = Image.new('RGBA', f.size, '#27303e')
                bg.alpha_composite(f)
                bg.thumbnail((640, 640))
                gif.append(bg.convert('RGB'))
            kwargs = {'loop': 0} if move.get('loop') else {}
            gif[0].save(output / 'previews' / f'{name}.gif', save_all=True, append_images=gif[1:],
                        duration=gif_ms, disposal=2, **kwargs)
            contact(atlas, output / 'previews' / f'{name}_contact.jpg')
            manifest['animations'].append({'name': name, 'files': files, 'durationMs': durations,
                                          'loop': bool(move.get('loop')), 'sourceFrames': indices,
                                          'selection': analysis})
            reports[name] = {'count': len(frames), 'bounds': bounds,
                'emptyFrames': [k for k, b in enumerate(bounds) if b is None],
                'touchesCanvasEdge': [k for k, b in enumerate(bounds) if b is not None and
                    (b[0] <= 0 or b[1] <= 0 or b[2] >= cw or b[3] >= ch)],
                'durationMs': sum(durations), 'loopRequested': bool(move.get('loop')),
                'previewTimingMs': {'webp': sum(ms), 'gif': sum(gif_ms)},
                'selection': analysis, 'maskPipelineVersion': MASK_PIPELINE_VERSION,
                'despill': cfg['mask'].get('despill'),
                'loopSeamVerified': False, 'maskVisuallyVerified': False}
            payload[name] = {'data': atlas_data, 'image': 'data:image/png;base64,' + base64.b64encode(image_path.read_bytes()).decode()}
            print(f'{name}: {len(frames)} frames, {sum(durations):.2f}ms', flush=True)
    finally:
        cap.release()
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'validation.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    template = (Path(__file__).resolve().parents[1] / 'assets' / 'preview.html').read_text(encoding='utf-8')
    preview = template.replace('__PAYLOAD__', json.dumps(payload)).replace('__MANIFEST__', json.dumps(manifest))
    (output / 'preview.html').write_text(preview, encoding='utf-8')
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect', help='Probe source and write a labeled contact sheet')
    p.add_argument('--video', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--samples', type=int, default=16)
    p = sub.add_parser('export', help='Export configured actions and a self-contained preview')
    p.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'inspect':
        if args.samples < 1:
            parser.error('--samples must be positive')
        inspect(args.video.resolve(), args.work.resolve(), args.samples)
    else:
        export(args.config.resolve())


if __name__ == '__main__':
    main()
