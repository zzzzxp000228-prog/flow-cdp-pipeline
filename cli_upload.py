"""CLI: 上传本地素材到 Flow 并写入 manifest。

用法:
  python cli_upload.py
  python cli_upload.py --config /path/to/settings.json
"""
import argparse
import asyncio
import json
import os

from core.cdp import FlowCDP
from core.config import load_config


async def main(cfg):
    manifest = {}
    if os.path.exists(cfg.manifest_path):
        with open(cfg.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    uploaded = manifest.setdefault("assets", {})

    async with FlowCDP(cfg) as flow:
        await flow.ensure_all_media_view()
        for key, filename in cfg.assets.items():
            if key in uploaded:
                print(f"[upload] skip {key}, already in manifest", flush=True)
                continue
            fpath = cfg.path("assets", filename)
            if not os.path.exists(fpath):
                raise FileNotFoundError(f"素材文件不存在: {fpath}")
            src = await flow.upload_asset(key, fpath)
            uploaded[key] = {
                "path": fpath,
                "filename": filename,
                "src_sample": src[:120],
            }
            os.makedirs(os.path.dirname(cfg.manifest_path) or ".", exist_ok=True)
            with open(cfg.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[upload] all assets done", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="settings.json 路径")
    args = ap.parse_args()
    asyncio.run(main(load_config(args.config)))
