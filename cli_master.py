"""CLI: FFmpeg 后期总成（三版本成片 + QA 拼图）。

用法:
  python cli_master.py --plan examples/build_plan.example.json
"""
import argparse
import os

from core.config import load_config
from core.master import build_master


def main(cfg, plan_path):
    if not os.path.isabs(plan_path) and not os.path.exists(plan_path):
        plan_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), plan_path)
    result = build_master(plan_path, cfg)
    print("\n[master] outputs:", flush=True)
    for key, value in result.items():
        print(f"  {key}: {value}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--plan", required=True, help="build plan JSON 路径")
    args = ap.parse_args()
    main(load_config(args.config), args.plan)
