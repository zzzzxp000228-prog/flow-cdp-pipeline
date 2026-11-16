"""设置锁定：Video / Ingredients / 9:16 / 分辨率 / 时长 / 出图数量。

关键点：count 必须是 x1（省积分），并主动拒绝 x2/x3/x4 误触，避免一次扣多倍积分。
"""
import asyncio
import json

from .cdp import FlowCDP


async def ensure_settings(flow, target_res="720p", target_dur="10", target_count="x1", allowed_counts=None):
    """打开设置浮层，逐项锁定并回读校验。返回 cost_info。"""
    allowed_counts = allowed_counts or ["x1", "x2", "x3", "x4"]
    if target_count not in allowed_counts:
        raise ValueError(f"target_count={target_count} 不在允许列表 {allowed_counts}")
    await flow.esc()
    await asyncio.sleep(0.3)

    trigger = await flow.js(
        """(() => {
            const b = [...document.querySelectorAll('button')].find(x => /设置触发器|Settings trigger/i.test(x.getAttribute('aria-label') || ''));
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return { x: r.left + r.width/2, y: r.top + r.height/2 };
        })()"""
    )
    if not trigger:
        raise RuntimeError("找不到 Settings trigger 按钮")
    await flow.tap(trigger["x"], trigger["y"])
    await asyncio.sleep(0.7)

    # 浮层里的按钮按文案匹配，中英文都覆盖
    patterns = [r"^(?:videocam\s*)?(?:视频|Video)$", r"(?:原料|Ingredients)$", r"9:16$", target_res, f"^{target_count}$"]
    for pat in patterns:
        btn = await flow.js(
            f"""(() => {{
                const rx = new RegExp({json.dumps(pat)}, 'i');
                const popBtns = [...document.querySelectorAll('button')].filter(b => {{
                    const r = b.getBoundingClientRect();
                    return r.y > 450 && r.y < 965 && r.width > 15;
                }});
                const m = popBtns.find(b => rx.test((b.innerText || '').trim()));
                if (!m) return null;
                const r = m.getBoundingClientRect();
                return {{ x: r.left + r.width/2, y: r.top + r.height/2 }};
            }})()"""
        )
        if btn:
            await flow.tap(btn["x"], btn["y"])
            await asyncio.sleep(0.25)

    # 时长滑杆：aria-valuenow 映射到秒数。默认 8s=idx5, 10s=idx7。
    for _ in range(15):
        cur = await flow.js(
            """(() => {
                const b = [...document.querySelectorAll('button')].find(x => /设置触发器|Settings trigger/i.test(x.getAttribute('aria-label') || ''));
                return b ? b.innerText : '';
            })()"""
        )
        if f"{target_dur}s" in cur or f"{target_dur}秒" in cur:
            break
        val = await flow.js(
            """(() => {
                const s = document.querySelector('[role="slider"], input[type="range"]');
                if (!s) return null;
                s.focus();
                return parseInt(s.getAttribute('aria-valuenow') || s.value || '5', 10);
            })()"""
        )
        target_idx = 7 if str(target_dur) == "10" else 5
        if val is None:
            break
        key, vk = ("ArrowRight", 39) if val < target_idx else ("ArrowLeft", 37)
        await flow.key(key, vk)
        await asyncio.sleep(0.25)

    cost = await flow.js(
        """(() => {
            const b = [...document.querySelectorAll('button')].find(x => /设置触发器|Settings trigger/i.test(x.getAttribute('aria-label') || ''));
            const creditEl = [...document.querySelectorAll('div, span, p, a')].find(x => x.children.length === 0 && /消耗|积分|credits/i.test(x.innerText || ''));
            const cntBtns = [...document.querySelectorAll('button')].filter(x => {
                const r = x.getBoundingClientRect();
                return r.y > 450 && r.y < 965 && /^x[1-4]$/i.test((x.innerText || '').trim());
            }).map(x => ({ txt: (x.innerText || '').trim() }));
            return { trigger: b ? b.innerText : '', creditMsg: creditEl ? creditEl.innerText : '', countButtons: cntBtns };
        })()"""
    )
    await flow.esc()
    await asyncio.sleep(0.35)

    print(f"[settings] {target_count}: {json.dumps(cost, ensure_ascii=False)}", flush=True)
    if target_res not in cost["trigger"]:
        raise RuntimeError(f"分辨率校验失败: {cost['trigger']}")
    # 拒绝误触多倍出图：只允许目标 count 出现在 trigger
    for multi in allowed_counts:
        if multi != target_count and multi in cost["trigger"]:
            raise RuntimeError(f"拒绝执行：trigger 仍是 {multi} 而不是 {target_count}: {cost['trigger']}")
    return cost
