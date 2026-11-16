"""Prompt 注入：必须用 execCommand('insertText') 才能触发 Angular contenteditable 的模型更新。

直接赋值 .innerText / .value 不会更新组件状态，提交时会被忽略。
editor 选择器 / 点击偏移从 flow.cfg.sel 读取。
"""
import asyncio
import json

from .selectors import q


def _editor_box_js(sel):
    """定位 prompt editor，返回一个可点击的内部点。"""
    g = sel.geometry
    return f"""(() => {{
        const ed = document.querySelector({q(sel.dom.prompt_editor)});
        if (!ed) return null;
        const r = ed.getBoundingClientRect();
        return {{ x: r.left + {g.prompt_tap_offset_x}, y: r.top + {g.prompt_tap_offset_y} }};
    }})()"""


async def clear_prompt(flow):
    """清空 prompt 文本（chip 由 assets.clear_chips 负责）。"""
    sel = flow.cfg.sel
    box = await flow.js(_editor_box_js(sel))
    if not box:
        raise RuntimeError("找不到 prompt editor")
    await flow.tap(box["x"], box["y"])
    await asyncio.sleep(0.2)
    await flow.js(
        f"""(() => {{
            const ed = document.querySelector({q(sel.dom.prompt_editor)});
            if (!ed) return;
            ed.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
        }})()"""
    )
    await asyncio.sleep(0.2)


async def insert_prompt(flow, text, verify_token="Active References Lock"):
    """注入 prompt 并回读校验。verify_token 为空则跳过校验。"""
    sel = flow.cfg.sel
    box = await flow.js(_editor_box_js(sel))
    if not box:
        raise RuntimeError("找不到 prompt editor")
    await flow.tap(box["x"], box["y"])
    await asyncio.sleep(0.2)
    await flow.js(
        f"""(() => {{
            const ed = document.querySelector({q(sel.dom.prompt_editor)});
            if (!ed) return;
            ed.focus();
            document.execCommand('insertText', false, {json.dumps(text, ensure_ascii=False)});
            ed.dispatchEvent(new InputEvent('input', {{ bubbles: true, cancelable: true, inputType: 'insertText' }}));
        }})()"""
    )
    await asyncio.sleep(0.4)
    if verify_token:
        actual = await flow.js(
            f"""(document.querySelector({q(sel.dom.prompt_editor)}).innerText || '')"""
        )
        if verify_token not in actual:
            raise RuntimeError("prompt 注入校验失败：回读文本里找不到校验串")
    return True
