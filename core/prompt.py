"""Prompt 注入：必须用 execCommand('insertText') 才能触发 Angular contenteditable 的模型更新。

直接赋值 .innerText / .value 不会更新组件状态，提交时会被忽略。
"""
import asyncio
import json


async def clear_prompt(flow):
    """清空 prompt 文本（chip 由 assets.clear_chips 负责）。"""
    box = await flow.js(
        """(() => {
            const ed = document.querySelector('[contenteditable="true"], textarea');
            if (!ed) return null;
            const r = ed.getBoundingClientRect();
            return { x: r.left + 40, y: r.top + 20 };
        })()"""
    )
    if not box:
        raise RuntimeError("找不到 prompt editor")
    await flow.tap(box["x"], box["y"])
    await asyncio.sleep(0.2)
    await flow.js(
        """(() => {
            const ed = document.querySelector('[contenteditable="true"], textarea');
            if (!ed) return;
            ed.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
        })()"""
    )
    await asyncio.sleep(0.2)


async def insert_prompt(flow, text, verify_token="Active References Lock"):
    """注入 prompt 并回读校验。verify_token 为空则跳过校验。"""
    box = await flow.js(
        """(() => {
            const ed = document.querySelector('[contenteditable="true"], textarea');
            const r = ed.getBoundingClientRect();
            return { x: r.left + 40, y: r.top + 20 };
        })()"""
    )
    await flow.tap(box["x"], box["y"])
    await asyncio.sleep(0.2)
    await flow.js(
        f"""(() => {{
            const ed = document.querySelector('[contenteditable="true"], textarea');
            ed.focus();
            document.execCommand('insertText', false, {json.dumps(text)});
            ed.dispatchEvent(new InputEvent('input', {{ bubbles: true, cancelable: true, inputType: 'insertText' }}));
        }})()"""
    )
    await asyncio.sleep(0.4)
    if verify_token:
        actual = await flow.js("(document.querySelector('[contenteditable=\"true\"], textarea').innerText || '')")
        if verify_token not in actual:
            raise RuntimeError("prompt 注入校验失败：回读文本里找不到校验串")
    return True
