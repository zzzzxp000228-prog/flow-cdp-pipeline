"""台词转录：faster-whisper 词级时间戳，核对演员实际开口内容。

注意：faster-whisper 内置的 av 解码在新版 av 上会报 metadata_errors 参数错误。
绕过办法：用 ffmpeg pipe 输出 f32le，numpy.frombuffer 后直接把 ndarray 传给 transcribe。
"""
import json
import os
import subprocess

import numpy as np


def decode_f32(mp4):
    """用 ffmpeg 解码成 16kHz mono float32，绕开 av 版本兼容问题。"""
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", mp4,
        "-ar", "16000", "-ac", "1", "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1",
    ])
    return np.frombuffer(raw, dtype=np.float32).copy()


def transcribe_clips(mp4_paths, out_json, model_name="small.en", language=None):
    """转录多个片段，返回并保存 {key: {segments:[{s,e,text,words[]}]}}。"""
    from faster_whisper import WhisperModel  # 延迟导入：没装依赖时其它模块仍可用

    print(f"[asr] loading model {model_name} ...", flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)

    report = {}
    if os.path.exists(out_json):
        try:
            with open(out_json, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = {}

    for path in mp4_paths:
        key = os.path.splitext(os.path.basename(path))[0]
        print(f"[asr] transcribing {key}", flush=True)
        audio = decode_f32(path)
        segments, info = model.transcribe(
            audio, language=language, beam_size=5, word_timestamps=True,
            vad_filter=True, vad_parameters=dict(min_silence_duration_ms=250),
        )
        seg_list = []
        for seg in segments:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append({
                        "w": w.word, "s": round(w.start, 2), "e": round(w.end, 2),
                        "p": round(w.probability, 2),
                    })
            seg_list.append({
                "s": round(seg.start, 2), "e": round(seg.end, 2),
                "text": seg.text.strip(), "words": words,
            })
            print(f"  [{seg.start:5.2f}-{seg.end:5.2f}] {seg.text.strip()}", flush=True)
        report[key] = {
            "mp4": path, "language": info.language,
            "duration": round(info.duration, 2), "segments": seg_list,
        }
        os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report
