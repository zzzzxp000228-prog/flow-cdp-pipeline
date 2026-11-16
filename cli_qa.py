"""CLI: 原片质检（scdet 硬切点 + 0.1s RMS）。

用法:
  python cli_qa.py --glob "clips/candidates/seq*_cand1.mp4"
  python cli_qa.py --glob "clips/candidates/seq*_cand1.mp4" --out audio/qa.json
"""
import argparse
import glob
import os

from core.config import load_config
from core.qa import inspect_clip, write_report


def main(cfg, pattern, out_json, threshold):
    full_pattern = pattern if os.path.isabs(pattern) else os.path.join(cfg.project_root, pattern)
    paths = sorted(glob.glob(full_pattern))
    if not paths:
        raise SystemExit(f"没有匹配到文件: {full_pattern}")
    work_wav = cfg.path("audio", "_rms_tmp.wav")
    os.makedirs(os.path.dirname(work_wav), exist_ok=True)

    report = {}
    for path in paths:
        key = os.path.splitext(os.path.basename(path))[0]
        info = inspect_clip(path, work_wav, threshold=threshold)
        report[key] = info
        print(f"\n=== {key} ===", flush=True)
        print(f"  cuts: {info['scdet_cuts']}", flush=True)
        print(f"  peak RMS: {info['peak_rms']:.4f}", flush=True)
        print(f"  speech: {info['speech_spans_sec']}", flush=True)

    if out_json and not os.path.isabs(out_json):
        out_json = os.path.join(cfg.project_root, out_json)
    write_report(report, out_json or cfg.path("audio", "qa.json"))
    print(f"\n[qa] report -> {out_json or cfg.path('audio','qa.json')}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--glob", required=True, help="原片 glob（相对 project_root）")
    ap.add_argument("--out", help="报告 JSON 路径")
    ap.add_argument("--threshold", type=float, default=8.0)
    args = ap.parse_args()
    main(load_config(args.config), args.glob, args.out, args.threshold)
