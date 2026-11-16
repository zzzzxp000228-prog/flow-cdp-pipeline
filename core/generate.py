"""生成与下载：提交任务 -> 轮询新成片 -> Blob 无损抓 720p -> 20 宫格 QA。

不在 Flow 里花积分升 1080p/4K，统一下载 720p 后由 FFmpeg Lanczos+CAS 升频。
所有文案正则 / 坐标阈值 / 等待参数从 flow.cfg.sel 读取。
"""
import asyncio
import base64
import json
import os
import subprocess
import time

from . import assets, prompt, settings
from .selectors import q


def make_contact_sheet(mp4_path, sheet_png, frames_dir):
    """2fps 抽帧 -> 5x4 拼图（约 20 帧/10s）。"""
    os.makedirs(frames_dir, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", mp4_path,
         "-vf", "fps=2,scale=270:480,tile=5x4", "-frames:v", "1", sheet_png],
        check=True, capture_output=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,duration", "-of", "json", mp4_path],
        capture_output=True, text=True, check=True,
    )
    print(f"[qa] contact sheet: {sheet_png}", flush=True)
    return json.loads(probe.stdout)


async def download_720p_via_blob(flow, out_mp4, chunk_size=1024 * 1024):
    """拦截 URL.createObjectURL 捕获 Blob，分块 base64 读出写盘。

    直接点下载会走浏览器下载目录且文件名带随机后缀；Blob 捕获可精确控制路径。
    """
    sel = flow.cfg.sel
    t = sel.timing
    min_size = t.blob_min_size
    await flow.js(
        f"""(() => {{
            window.__capturedVideoBlob = null;
            if (!window.__origCreateObjURL) {{
                window.__origCreateObjURL = URL.createObjectURL.bind(URL);
                URL.createObjectURL = function(obj) {{
                    const u = window.__origCreateObjURL(obj);
                    try {{
                        if (obj && typeof obj.size === 'number' && obj.size > {min_size}) {{
                            window.__capturedVideoBlob = obj;
                        }}
                    }} catch (e) {{}}
                    return u;
                }};
            }}
        }})()"""
    )
    dl = await flow.js(
        f"""(() => {{
            const rx = new RegExp({q(sel.text.download)}, 'i');
            const b = [...document.querySelectorAll('button')].find(x =>
                rx.test(x.getAttribute('aria-label')||'') || (x.innerText||'').trim()==='download');
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return {{ x: r.left+r.width/2, y: r.top+r.height/2 }};
        }})()"""
    )
    if not dl:
        raise RuntimeError("找不到下载按钮")
    await flow.tap(dl["x"], dl["y"])
    await asyncio.sleep(0.8)

    options = await flow.js(
        f"""(() => [...document.querySelectorAll({q(sel.dom.download_option)})].filter(el => {{
            const r = el.getBoundingClientRect();
            const txt = el.innerText||'';
            const opt = new RegExp({q(sel.text.download_option)}, 'i');
            const excl = new RegExp({q(sel.text.download_exclude)}, 'i');
            return r.width>0 && opt.test(txt) && !excl.test(txt);
        }}).map(el => ({{ text: el.innerText.trim(),
            x: Math.round(el.getBoundingClientRect().x+el.getBoundingClientRect().width/2),
            y: Math.round(el.getBoundingClientRect().y+el.getBoundingClientRect().height/2) }})))()"""
    )
    if not options:
        raise RuntimeError("找不到 720p 下载选项")
    await flow.tap(options[0]["x"], options[0]["y"])

    size = 0
    for _ in range(t.blob_wait_rounds):
        await asyncio.sleep(t.blob_wait_interval)
        size = await flow.js("window.__capturedVideoBlob ? window.__capturedVideoBlob.size : 0")
        if size and size > min_size:
            break
    if not size:
        raise RuntimeError("等待 720p Blob 超时")

    chunks = []
    offset = 0
    while offset < size:
        end = min(offset + chunk_size, size)
        b64 = await flow.js(
            f"""(async () => {{
                const slice = window.__capturedVideoBlob.slice({offset}, {end});
                const buf = await slice.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let bin = '';
                for (let i=0; i<bytes.length; i+=0x8000) {{
                    bin += String.fromCharCode.apply(null, bytes.subarray(i, i+0x8000));
                }}
                return btoa(bin);
            }})()"""
        )
        chunks.append(base64.b64decode(b64))
        offset = end
    data = b"".join(chunks)
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    with open(out_mp4, "wb") as f:
        f.write(data)
    print(f"[download] {len(data)//1024} KB -> {out_mp4}", flush=True)
    return len(data)


async def wait_for_fresh_video(flow, pre_srcs, timeout=360, expect=1):
    """轮询画廊顶部，等出现在 pre_srcs 之外、且进度条消失的新视频。"""
    sel = flow.cfg.sel
    g = sel.geometry
    t = sel.timing
    fresh_rx = q(sel.text.fresh_video)
    failed_rx = q(sel.text.failed)

    def is_fresh(tile):
        base = (tile.get("src") or "").split("?")[0]
        if not base or base in pre_srcs:
            return False
        return (sel.text.fresh_video in (tile.get("alt") or "")) or ("/asb/" in base) or (tile.get("tag") == "VIDEO")

    t0 = time.time()
    while time.time() - t0 < timeout:
        await asyncio.sleep(t.poll_interval)
        elapsed = int(time.time() - t0)
        await flow.hover_neutral()
        tiles = await flow.get_media_tiles()
        fresh = sorted(
            [t2 for t2 in tiles if is_fresh(t2) and t2["y"] < g.fresh_tile_max_y and t2["x"] < g.fresh_tile_max_x],
            key=lambda t2: (round(t2["y"] / 40), t2["x"]),
        )
        progress = await flow.js(
            f"""(() => [...document.querySelectorAll('*')].filter(el => {{
                const r = el.getBoundingClientRect();
                return el.children.length===0 && r.y<{g.progress_max_y} && r.x>{g.progress_min_x} &&
                       /^\\d{{1,3}}%$/.test((el.innerText||'').trim());
            }}).map(el => el.innerText.trim()))()"""
        )
        failed = await flow.js(
            f"""(() => [...document.querySelectorAll('*')].filter(el => {{
                const r = el.getBoundingClientRect();
                const tx = (el.innerText||'').trim();
                const rx = new RegExp({failed_rx}, 'i');
                return el.children.length===0 && r.y>{g.failed_min_y} && r.y<{g.failed_max_y} &&
                       r.x>{g.progress_min_x} && rx.test(tx);
            }}).map(el => el.innerText.trim()))()"""
        )
        print(f"  [{elapsed}s] fresh={len(fresh)}/{expect} progress={progress}", flush=True)
        if failed and not progress and not fresh and elapsed >= t.failed_min_elapsed:
            raise RuntimeError(f"Flow 拒绝生成: {failed[:3]}")
        if elapsed >= t.fresh_min_elapsed and len(fresh) >= expect and not progress:
            return fresh[:expect]
    raise TimeoutError(f"等待新成片超时（{timeout}s）")


async def generate_sequence(flow, cfg, seq, out_mp4, sheet_png, force_settings=False):
    """完整跑一个镜头：清 prompt -> 挂载参考图 -> 注入 prompt -> 提交 -> 下载 -> QA。"""
    from .cdp import FlowCDP  # noqa: F401  (类型提示用)

    sel = cfg.sel
    await flow.ensure_all_media_view()
    await settings.ensure_settings(
        flow, target_res=seq.get("res", "720p"), target_dur=seq.get("dur", "10"),
        target_count=seq.get("count", cfg.count_lock), allowed_counts=cfg.allowed_counts,
    )
    await prompt.clear_prompt(flow)
    await assets.mount_refs(flow, seq["refs"], cfg.assets, max_refs=seq.get("max_refs", 3))
    await prompt.insert_prompt(flow, seq["prompt"], verify_token=seq.get("verify_token", "Active References Lock"))

    await flow.js("""(() => { document.querySelectorAll('div').forEach(d => { if (d.scrollTop > 0) d.scrollTop = 0; }); })()""")
    await flow.hover_neutral()
    await asyncio.sleep(0.8)
    pre_tiles = await flow.get_media_tiles()
    pre_srcs = {t["src"].split("?")[0] for t in pre_tiles if t.get("src")}
    print(f"[gen] gallery tiles before submit: {len(pre_tiles)}", flush=True)

    gen = await flow.js(
        f"""(() => {{
            const rx = new RegExp({q(sel.text.start_generation)}, 'i');
            const arrow = {q(sel.text.gen_arrow)};
            const b = [...document.querySelectorAll('button')].find(x =>
                rx.test(x.getAttribute('aria-label')||'') ||
                ((x.innerText||'').trim()===arrow && x.getBoundingClientRect().y>{sel.geometry.gen_arrow_min_y}));
            if (!b || b.disabled) return null;
            const r = b.getBoundingClientRect();
            return {{ x: r.left+r.width/2, y: r.top+r.height/2 }};
        }})()"""
    )
    if not gen:
        raise RuntimeError("找不到生成按钮或按钮被禁用")
    print(f"[gen] submitting {seq.get('name','sequence')} ...", flush=True)
    await flow.tap(gen["x"], gen["y"])

    fresh = await wait_for_fresh_video(flow, pre_srcs, timeout=seq.get("poll_timeout", 360))
    await asyncio.sleep(1.5)
    await flow.hover_neutral()

    tile = fresh[0]
    await flow.tap(tile["x"] + tile["w"] / 2, tile["y"] + tile["h"] / 2)
    await asyncio.sleep(1.5)
    await download_720p_via_blob(flow, out_mp4)

    # 返回画廊
    back_rx = q(sel.text.back)
    back_done = q(sel.text.back_done)
    back = await flow.js(
        f"""(() => {{
            const rx = new RegExp({back_rx}, 'i');
            const b = [...document.querySelectorAll('button')].find(x =>
                rx.test(x.getAttribute('aria-label')||'') || (x.innerText||'').trim()==={back_done});
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return {{ x: r.left+r.width/2, y: r.top+r.height/2 }};
        }})()"""
    )
    if back:
        await flow.tap(back["x"], back["y"])
    else:
        await flow.esc()
    await asyncio.sleep(1.0)

    return make_contact_sheet(out_mp4, sheet_png, cfg.path("frames"))
