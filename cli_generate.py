"""CLI: 批量生成镜头（单连接复用，x1 省积分锁，720p 下载 + 20 宫格 QA）。

用法:
  python cli_generate.py --plan examples/sequences.example.json --seqs 1,2,3
  python cli_generate.py --plan examples/sequences.example.json --seqs 1 --force
"""
import argparse
import asyncio
import json
import os

from core.cdp import FlowCDP
from core.config import load_config
from core.generate import generate_sequence


async def main(cfg, plan_path, seqs, force):
    with open(plan_path, "r", encoding="utf-8") as f:
        sequences = json.load(f)["sequences"]
    cfg.ensure_dirs()

    pending = []
    for s in seqs:
        out_mp4 = cfg.path("candidates", f"seq{s:02d}_cand1.mp4")
        if not force and os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 100_000:
            print(f"[skip] seq{s:02d} 已存在 ({os.path.getsize(out_mp4)//1024} KB)", flush=True)
        else:
            pending.append(s)
    if not pending:
        print("没有待生成镜头", flush=True)
        return

    async with FlowCDP(cfg) as flow:
        for idx, num in enumerate(pending):
            seq = sequences.get(str(num))
            if not seq:
                raise KeyError(f"sequences 里没有编号 {num}")
            out_mp4 = cfg.path("candidates", f"seq{num:02d}_cand1.mp4")
            sheet = cfg.path("frames", f"seq{num:02d}_cand1_sheet.png")
            print(f"\n=== [{idx+1}/{len(pending)}] {seq['name']} ===", flush=True)
            generate_info = await generate_sequence(flow, cfg, seq, out_mp4, sheet)
            print(f"[done] seq{num:02d}: {out_mp4}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="settings.json 路径")
    ap.add_argument("--plan", required=True, help="sequences JSON 路径")
    ap.add_argument("--seqs", default="1", help="逗号分隔的镜头编号，如 1,2,3")
    ap.add_argument("--force", action="store_true", help="即使已存在也重新生成")
    args = ap.parse_args()
    nums = [int(x.strip()) for x in args.seqs.split(",") if x.strip()]
    asyncio.run(main(load_config(args.config), args.plan, nums, args.force))
