"""CLI: 台词转录（faster-whisper 词级时间戳）。

依赖: pip install faster-whisper numpy
用法:
  python cli_transcribe.py --glob "clips/candidates/seq*_cand1.mp4"
  python cli_transcribe.py --glob "clips/candidates/seq*_cand1.mp4" --model medium.en
"""
import argparse
import glob
import os

from core.config import load_config
from core.transcribe import transcribe_clips


def main(cfg, pattern, out_json, model, language):
    full = pattern if os.path.isabs(pattern) else os.path.join(cfg.project_root, pattern)
    paths = sorted(glob.glob(full))
    if not paths:
        raise SystemExit(f"没有匹配到文件: {full}")
    if not os.path.isabs(out_json):
        out_json = os.path.join(cfg.project_root, out_json)
    transcribe_clips(paths, out_json, model_name=model, language=language)
    print(f"[asr] -> {out_json}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--glob", required=True)
    ap.add_argument("--out", default="audio/transcript.json")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--language", default=None, help="如 en / zh，留空自动检测")
    args = ap.parse_args()
    main(load_config(args.config), args.glob, args.out, args.model, args.language)
