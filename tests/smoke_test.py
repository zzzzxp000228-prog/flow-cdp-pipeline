"""冒烟测试：不连 Chrome、不跑 ffmpeg，验证配置加载与模块导入链。

运行: python tests/smoke_test.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def check(label, fn):
    try:
        result = fn()
        print(f"  PASS  {label}" + (f" -> {result}" if result else ""))
        return True
    except Exception as exc:
        print(f"  FAIL  {label}: {type(exc).__name__}: {exc}")
        return False


def main():
    print("flow-cdp-pipeline smoke test")
    ok = True

    cfg_path = os.path.join(ROOT, "config", "settings.example.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    ok &= check("settings.example.json 是合法 JSON", lambda: f"{len(raw)} keys")

    from core.config import load_config, Config
    cfg = load_config(cfg_path)
    ok &= check("load_config 返回 Config", lambda: type(cfg).__name__)
    ok &= check("project_root 解析为绝对路径", lambda: cfg.project_root)
    ok &= check("assets key 数量", lambda: len(cfg.assets))
    ok &= check("dirs 含 output", lambda: cfg.dirs["output"])

    os.environ["FLOW_PROJECT_ROOT"] = os.path.join(ROOT, "_smoke_proj")
    cfg2 = load_config(cfg_path)
    ok &= check("环境变量覆盖 project_root", lambda: cfg2.project_root.endswith("_smoke_proj"))
    del os.environ["FLOW_PROJECT_ROOT"]

    modules = ["core.cdp", "core.settings", "core.assets", "core.prompt",
               "core.generate", "core.qa", "core.master"]
    for mod in modules:
        ok &= check(f"import {mod}", lambda m=mod: __import__(m).__name__)

    from core.transcribe import decode_f32
    ok &= check("transcribe 模块可导入（延迟加载 faster-whisper）", lambda: decode_f32.__name__)

    # selector 外置：默认值可读、配置可覆盖、生成 JS 花括号平衡
    from core.selectors import Selectors, q
    from core import assets, settings as settings_mod, prompt as prompt_mod
    sel = Selectors()
    ok &= check("Config.sel 已挂载", lambda: type(cfg.sel).__name__)
    ok &= check("Selectors 默认值完整", lambda: f"{len(vars(sel.text))}/{len(vars(sel.dom))}/{len(vars(sel.geometry))}/{len(vars(sel.timing))}")

    def _js_balance():
        frags = [assets.js_chips(sel), assets.js_search(sel), assets.js_rows(sel),
                 settings_mod._trigger_js(sel), prompt_mod._editor_box_js(sel)]
        for js in frags:
            if js.count("{") - js.count("}") != 0:
                raise AssertionError("生成 JS 花括号不平衡")
        return f"{len(frags)} frags"

    ok &= check("动态 JS 花括号平衡", _js_balance)

    def _sel_override():
        over = Selectors({"geometry": {"result_row_min_y": 300}, "text": {"asset_search": "Find assets"}})
        assert "r.y>300" in assets.js_rows(over)
        assert "Find assets" in assets.js_search(over)
        assert sel.geometry.result_row_min_y == 200  # 默认未被污染
        return True

    ok &= check("selector 配置覆盖生效且不污染默认", _sel_override)
    ok &= check("q() 转义中文与引号", lambda: q('a"b\\c中文'))

    plan_path = os.path.join(ROOT, "examples", "build_plan.example.json")
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    ok &= check("build_plan.example.json pieces", lambda: len(plan["pieces"]))

    seq_path = os.path.join(ROOT, "examples", "sequences.example.json")
    with open(seq_path, "r", encoding="utf-8") as f:
        seqs = json.load(f)
    ok &= check("sequences.example.json 镜头数", lambda: len(seqs["sequences"]))

    print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
