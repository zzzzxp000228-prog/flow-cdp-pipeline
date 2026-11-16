"""参考图挂载：适配 Flow 2026-11 搜索驱动 picker。

新版 UI 把旧的滚动列表 + "Add to prompt" 换成了搜索浮层：
点 plus -> 搜文件名 -> 点结果行 -> chip 直接进 prompt box。
本模块内置超时保护（asyncio.wait_for），避免 CDP 偶发 hang 拖死整批。
"""
import asyncio

from .cdp import FlowCDP

# JS 片段：中英文界面都匹配
JS_CHIPS = """(() => {
    const box = document.querySelector('flow-base-prompt-box');
    if (!box) return -1;
    return [...box.querySelectorAll('img')].filter(im => /Ingredient image/i.test(im.alt||'')).length;
})()"""

JS_SEARCH = """(() => {
    const el = [...document.querySelectorAll('input')].find(x =>
        /搜索资产|Search assets/i.test(x.getAttribute('placeholder')||'') ||
        /搜索资产|Search assets/i.test(x.getAttribute('aria-label')||''));
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), v: el.value };
})()"""

JS_PLUS = """(() => {
    const b = [...document.querySelectorAll('button')].find(x =>
        /在提示框中输入配料|Add ingredients/i.test(x.getAttribute('aria-label')||''));
    if (!b) return null;
    const r = b.getBoundingClientRect();
    return { x: r.left+r.width/2, y: r.top+r.height/2 };
})()"""

JS_ROWS = """(() => [...document.querySelectorAll('button')].filter(b => {
    const r = b.getBoundingClientRect();
    const t = (b.innerText||'').trim();
    return r.width>60 && r.height>18 && r.y>200 && r.y<620 && /(图像|Image|图片)$/i.test(t);
}).map(b => {
    const r = b.getBoundingClientRect();
    return { x: r.left+Math.min(60,r.width/2), y: r.top+r.height/2, t:(b.innerText||'').trim().replace(/\\n/g,'|') };
}))()"""

JS_CLEAR_TEXT = """(() => {
    const el = [...document.querySelectorAll('input')].find(x =>
        /搜索资产|Search assets/i.test(x.getAttribute('placeholder')||'') ||
        /搜索资产|Search assets/i.test(x.getAttribute('aria-label')||''));
    if (el) { el.focus(); el.select(); }
})()"""


async def js(flow, expr, timeout=8):
    return await asyncio.wait_for(flow.js(expr), timeout)


async def call(flow, method, params, timeout=8):
    return await asyncio.wait_for(flow.call(method, params, sid=flow.sid), timeout)


async def tap(flow, x, y):
    await call(flow, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": float(x), "y": float(y)})
    await call(flow, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": float(x), "y": float(y), "button": "left", "clickCount": 1})
    await call(flow, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": float(x), "y": float(y), "button": "left", "clickCount": 1})


async def chip_count(flow):
    return await js(flow, JS_CHIPS)


async def clear_chips(flow):
    """点 Clear prompt 直到 chip 清零（切镜头时复用同一 prompt box）。"""
    for _ in range(20):
        if await chip_count(flow) <= 0:
            return
        btn = await js(flow, """(() => {
            const b = [...document.querySelectorAll('button')].find(x => /Clear prompt|清除提示/i.test(x.getAttribute('aria-label')||''));
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return { x: r.left+r.width/2, y: r.top+r.height/2 };
        })()""")
        if not btn:
            return
        await tap(flow, btn["x"], btn["y"])
        await asyncio.sleep(0.4)


async def open_picker(flow):
    """打开搜索浮层；plus 首次点击可能只出 tooltip，需要重试。"""
    await call(flow, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "windowsVirtualKeyCode": 27})
    await call(flow, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "windowsVirtualKeyCode": 27})
    await asyncio.sleep(0.5)
    for _ in range(8):
        search = await js(flow, JS_SEARCH)
        if search:
            return search
        plus = await js(flow, JS_PLUS)
        if plus:
            await tap(flow, plus["x"], plus["y"])
        await asyncio.sleep(1.1)
    return None


async def attach_one(flow, filename, expected_count, retries=4):
    """挂载单个素材；返回是否成功。"""
    for attempt in range(retries):
        try:
            search = await open_picker(flow)
            if not search:
                continue
            await tap(flow, search["x"] + 30, search["y"] + 15)
            await asyncio.sleep(0.25)
            # 用真实 Delete 键清空残留文本：只 insertText 会在 Angular input 里累加
            await js(flow, JS_CLEAR_TEXT)
            await asyncio.sleep(0.15)
            await call(flow, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Delete", "windowsVirtualKeyCode": 46})
            await call(flow, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Delete", "windowsVirtualKeyCode": 46})
            await asyncio.sleep(0.4)
            await call(flow, "Input.insertText", {"text": filename})
            await asyncio.sleep(2.2)

            rows = await js(flow, JS_ROWS)
            if not rows:
                continue
            row = next((r for r in rows if filename.lower() in r["t"].lower()), rows[0])
            await tap(flow, row["x"], row["y"])
            await asyncio.sleep(1.4)
            if await chip_count(flow) >= expected_count:
                return True
        except asyncio.TimeoutError:
            print(f"    [assets] {filename} 第 {attempt+1} 次超时，重试", flush=True)
            try:
                await call(flow, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "windowsVirtualKeyCode": 27})
                await call(flow, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "windowsVirtualKeyCode": 27})
            except Exception:
                pass
    return False


async def mount_refs(flow, ref_keys, key_to_filename, max_refs=3):
    """按 key 列表挂载参考图，最多 max_refs 张。"""
    keys = ref_keys[:max_refs]
    await clear_chips(flow)
    for i, key in enumerate(keys):
        fname = key_to_filename.get(key)
        if not fname:
            raise RuntimeError(f"未配置的素材 key: {key}（请在 config 的 assets 里补充）")
        if not await attach_one(flow, fname, i + 1):
            raise RuntimeError(f"挂载失败: {key} ({fname})")
        print(f"  [assets] attached [{i+1}/{len(keys)}]: {key} ({fname})", flush=True)
    count = await chip_count(flow)
    if count != len(keys):
        raise RuntimeError(f"chip 数量不符: {count} != {len(keys)}")
    print(f"[assets] mounted chips: {count}", flush=True)
    return count
