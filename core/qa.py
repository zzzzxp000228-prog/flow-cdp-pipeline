"""原片质检：scdet 硬切点 + 0.1s 音频 RMS 包络。

ffmpeg/ffprobe 全部走 subprocess，不依赖 python 音频库。
"""
import json
import math
import os
import re
import struct
import subprocess
import wave


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def scdet_cuts(path, threshold=8.0):
    """返回 [(秒, score)]，threshold=8.0 是本项目的验证值。"""
    p = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", path,
        "-an", "-vf", f"scdet=threshold={threshold},metadata=print", "-f", "null", "-",
    ])
    if p.returncode != 0:
        raise RuntimeError(f"scdet 失败: {p.stderr[-500:]}")
    blocks = re.split(r"frame:\s*\d+", p.stderr)
    cuts = []
    for block in blocks:
        score = re.search(r"lavfi\.scd\.score=([\d.]+)", block)
        tm = re.search(r"lavfi\.scd\.time=([\d.]+)", block)
        if score and tm:
            t = float(tm.group(1))
            if t >= 0:
                cuts.append((round(t, 3), round(float(score.group(1)), 2)))
    unique = []
    for t, s in cuts:
        if not unique or t - unique[-1][0] > 0.15:
            unique.append((t, s))
    return unique


def rms_envelope(path, work_wav):
    """16kHz mono -> 0.1s RMS 列表。"""
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", path, "-ar", "16000", "-ac", "1", "-f", "wav", work_wav,
    ])
    with wave.open(work_wav, "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = struct.unpack(f"<{len(raw)//2}h", raw)
    window = int(sr * 0.1)
    env = []
    for i in range(0, len(samples), window):
        chunk = samples[i:i + window]
        if not chunk:
            break
        env.append(round(math.sqrt(sum(x * x for x in chunk) / len(chunk)) / 32768.0, 5))
    return env


def speech_spans(env, threshold=0.02, min_run=2):
    """把连续高于阈值的 0.1s 窗口合并成 (起秒, 止秒)。"""
    spans = []
    start = None
    for i, value in enumerate(env):
        if value >= threshold:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_run:
                spans.append((round(start * 0.1, 1), round(i * 0.1, 1)))
            start = None
    if start is not None and len(env) - start >= min_run:
        spans.append((round(start * 0.1, 1), round(len(env) * 0.1, 1)))
    return spans


def inspect_clip(mp4_path, work_wav, threshold=8.0):
    env = rms_envelope(mp4_path, work_wav)
    return {
        "mp4": mp4_path,
        "scdet_cuts": scdet_cuts(mp4_path, threshold=threshold),
        "rms_0_1s": env,
        "speech_spans_sec": speech_spans(env),
        "peak_rms": max(env) if env else 0.0,
    }


def write_report(report, out_json):
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return out_json
