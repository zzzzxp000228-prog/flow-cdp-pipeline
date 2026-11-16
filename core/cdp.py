"""CDP 底层：单连接、持久化、带超时保护的 Flow 客户端。

Chrome 136+ 对弹窗/新标签有限制，整批生成必须复用同一条 WebSocket 连接。
所有 JS 侧文案用正则匹配中英文界面，切换界面语言不需要改代码。
"""
import asyncio
import json
import time

import websockets

from .config import load_config
from .selectors import q


class FlowCDP:
    """最小可用的 CDP 客户端。作为上下文管理器使用。"""

    def __init__(self, config=None, open_timeout=120):
        self.cfg = config or load_config()
        self.open_timeout = open_timeout
        self.ws = None
        self.sid = None
        self.mid = 0
        self.events = []
        self.target_url = None

    async def __aenter__(self):
        url = self.cfg.ws_url()
        self.ws = await websockets.connect(
            url,
            max_size=2**24,
            ping_interval=None,
            ping_timeout=None,
            origin=None,
            open_timeout=self.open_timeout,
        )
        self.events = []
        targets = (await self.call("Target.getTargets"))["targetInfos"]
        match = self.cfg.target_url_match
        candidates = [t for t in targets if match in t.get("url", "")]
        if not candidates:
            raise RuntimeError(f"没有找到匹配 '{match}' 的标签页。请先在 Chrome 打开 Flow 项目页。")
        target = candidates[0]
        self.target_url = target.get("url")
        self.sid = (
            await self.call("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
        )["sessionId"]
        print(f"[cdp] attached: {self.target_url}", flush=True)
        for domain in ("Page", "Runtime", "DOM", "Network"):
            await self.call(f"{domain}.enable", sid=self.sid)
        await self.call("Page.setInterceptFileChooserDialog", {"enabled": True}, sid=self.sid)
        await self.call(
            "Emulation.setDeviceMetricsOverride",
            {**self.cfg.viewport, "deviceScaleFactor": 1, "mobile": False},
            sid=self.sid,
        )
        await asyncio.sleep(1.2)
        return self

    async def __aexit__(self, *exc):
        if self.ws:
            try:
                await self.call("Page.setInterceptFileChooserDialog", {"enabled": False}, sid=self.sid)
            except Exception:
                pass
            await self.ws.close()

    # ---- 基础 RPC ----
    async def call(self, method, params=None, sid=None, timeout=None):
        """发一条 CDP 命令并等对应 id 的响应；其它事件先缓存。"""
        self.mid += 1
        my_id = self.mid
        msg = {"id": my_id, "method": method}
        if params:
            msg["params"] = params
        if sid:
            msg["sessionId"] = sid
        await self.ws.send(json.dumps(msg))

        async def _recv():
            while True:
                data = json.loads(await self.ws.recv())
                if data.get("id") == my_id:
                    if "error" in data:
                        raise RuntimeError(f"CDP {method}: {data['error']}")
                    return data.get("result", {})
                if "method" in data:
                    self.events.append(data)

        if timeout:
            return await asyncio.wait_for(_recv(), timeout)
        return await _recv()

    async def wait_event(self, method_name, timeout=10.0):
        """从缓存或新事件中找指定事件。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for i, ev in enumerate(self.events):
                if ev.get("method") == method_name:
                    return self.events.pop(i)
            try:
                data = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=0.4))
                if "method" in data:
                    if data.get("method") == method_name:
                        return data
                    self.events.append(data)
            except asyncio.TimeoutError:
                pass
        return None

    async def js(self, expr, timeout=None):
        result = await self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
            sid=self.sid,
            timeout=timeout,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS 异常: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    # ---- 输入 ----
    async def tap(self, x, y):
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            await self.call(
                "Input.dispatchMouseEvent",
                {"type": kind, "x": float(x), "y": float(y), "button": "left", "clickCount": 1},
                sid=self.sid,
            )

    async def key(self, key, vk):
        await self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "windowsVirtualKeyCode": vk}, sid=self.sid)
        await self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "windowsVirtualKeyCode": vk}, sid=self.sid)

    async def esc(self):
        await self.key("Escape", 27)

    async def insert_text(self, text):
        await self.call("Input.insertText", {"text": text}, sid=self.sid)

    async def hover_neutral(self):
        await self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10.0, "y": 10.0}, sid=self.sid)
        await asyncio.sleep(0.25)

    # ---- 页面观察 ----
    async def ensure_all_media_view(self):
        box = await self.js(
            f"""(() => {{
                const rx = new RegExp({q(self.cfg.sel.text.all_media)}, 'i');
                const b = [...document.querySelectorAll('button')].find(x => rx.test(x.innerText || ''));
                if (!b) return null;
                const r = b.getBoundingClientRect();
                return {{ x: r.left + r.width/2, y: r.top + r.height/2 }};
            }})()"""
        )
        if box:
            await self.tap(box["x"], box["y"])
            await asyncio.sleep(0.5)

    async def get_media_tiles(self):
        """列出画廊里的媒体缩略图，排除 prompt box 内的 chip。"""
        await self.hover_neutral()
        g = self.cfg.sel.geometry
        return await self.js(
            f"""(() => {{
                const ed = document.querySelector({q(self.cfg.sel.dom.prompt_editor)});
                const plusRx = new RegExp({q(self.cfg.sel.text.add_ingredients)}, 'i');
                const plus = [...document.querySelectorAll('button')].find(x => plusRx.test(x.getAttribute('aria-label') || ''));
                let promptBox = ed ? ed.parentElement : null;
                while (promptBox && plus && !promptBox.contains(plus)) promptBox = promptBox.parentElement;
                const els = [...document.querySelectorAll({q(self.cfg.sel.dom.gallery_media)})].map(el => {{
                    if (promptBox && promptBox.contains(el)) return null;
                    const r = el.getBoundingClientRect();
                    return {{
                        tag: el.tagName,
                        src: el.currentSrc || el.src || '',
                        alt: el.alt || '',
                        x: Math.round(r.left), y: Math.round(r.top),
                        w: Math.round(r.width), h: Math.round(r.height)
                    }};
                }}).filter(o => o && o.w >= {g.tile_min_w} && o.h >= {g.tile_min_h} && o.x >= {g.tile_min_x});
                return els;
            }})()"""
        )

    async def upload_asset(self, key, fpath):
        """通过 file chooser 上传本地素材，等待新缩略图出现。"""
        print(f"[asset] uploading {key}: {fpath}", flush=True)
        before = {t["src"] for t in await self.get_media_tiles()}
        chooser = None
        for attempt in range(3):
            self.events = [e for e in self.events if e.get("method") != "Page.fileChooserOpened"]
            await self.esc()
            await asyncio.sleep(0.4)
            add_btn = await self.js(
                f"""(() => {{
                    const rx = new RegExp({q(self.cfg.sel.text.add_media_menu)}, 'i');
                    const b = [...document.querySelectorAll('button')].find(x => rx.test(x.getAttribute('aria-label') || ''));
                    if (!b) return null;
                    const r = b.getBoundingClientRect();
                    return {{ x: r.left + r.width/2, y: r.top + r.height/2 }};
                }})()"""
            )
            if not add_btn:
                raise RuntimeError("找不到 Add media menu 按钮")
            await self.tap(add_btn["x"], add_btn["y"])
            await asyncio.sleep(0.7)
            item = await self.js(
                f"""(() => {{
                    const rx = new RegExp({q(self.cfg.sel.text.upload_item + '$')}, 'i');
                    const b = [...document.querySelectorAll({q(self.cfg.sel.dom.upload_menu_item)})].find(x => rx.test((x.innerText || '').trim()));
                    if (!b) return null;
                    const r = b.getBoundingClientRect();
                    return (r.width>0 && r.height>0) ? {{ x: r.left+r.width/2, y: r.top+r.height/2 }} : null;
                }})()"""
            )
            if not item:
                print(f"  attempt {attempt+1}: upload item 不可见，重试", flush=True)
                continue
            await self.tap(item["x"], item["y"])
            chooser = await self.wait_event("Page.fileChooserOpened", timeout=5.0)
            if chooser and "backendNodeId" in chooser.get("params", {}):
                break

        if chooser and "backendNodeId" in chooser.get("params", {}):
            await self.call(
                "DOM.setFileInputFiles",
                {"backendNodeId": chooser["params"]["backendNodeId"], "files": [fpath]},
                sid=self.sid,
            )
        else:
            doc = await self.call("DOM.getDocument", {"depth": -1}, sid=self.sid)
            query = await self.call(
                "DOM.querySelectorAll",
                {"nodeId": doc["root"]["nodeId"], "selector": 'input[type="file"]'},
                sid=self.sid,
            )
            if not query.get("nodeIds"):
                raise RuntimeError("既没有 fileChooserOpened 也没有 input[type=file]")
            await self.call("DOM.setFileInputFiles", {"nodeId": query["nodeIds"][-1], "files": [fpath]}, sid=self.sid)

        for sec in range(self.cfg.sel.timing.asset_wait_sec):
            await asyncio.sleep(1.0)
            tiles = await self.get_media_tiles()
            fresh = [t for t in tiles if t["src"] and t["src"] not in before]
            if fresh:
                print(f"[asset] {key} visible in {sec+1}s", flush=True)
                return fresh[0]["src"]
        raise TimeoutError(f"等待素材 {key} 超时")
