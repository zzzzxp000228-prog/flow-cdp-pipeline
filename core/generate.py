"""生成与下载：提交任务 -> 轮询新成片 -> Blob 无损抓 720p -> 20 宫格 QA。

不在 Flow 里花积分升 1080p/4K，统一下载 720p 后由 FFmpeg Lanczos+CAS 升频。
"""
import asyncio
import base64
import json
import os
import subprocess
import time

from . import assets, prompt, settings


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
    await flow.js(
        """(() => {
            window.__capturedVideoBlob = null;
            if (!window.__origCreateObjURL) {
                window.__origCreateObjURL = URL.createObjectURL.bind(URL);
                URL.createObjectURL = function(obj) {
                    const u = window.__origCreateObjURL(obj);
                    try {
                        if (obj && typeof obj.size === 'number' && obj.size > 300000) {
                            window.__capturedVideoBlob = obj;
                        }
                    } catch (e) {}
                    return u;
                };
            }
        })()"""
    )
    dl = await flow.js(
        """(() => {
            const b = [...document.querySelectorAll('button')].find(x =>
                /Download media|下载/i.test(x.getAttribute('aria-label')||'') || (x.innerText||'').trim()==='download');
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return { x: r.left+r.width/2, y: r.top+r.height/2 };
        })()"""
    )
    if not dl:
        raise RuntimeError("找不到下载按钮")
    await flow.tap(dl["x"], dl["y"])
    await asyncio.sleep(0.8)

    options = await flow.js(
        """(() => [...document.querySelectorAll('button, [role="menuitem"]')].filter(el => {
            const r = el.getBoundingClientRect();
            return r.width>0 && /720p|Original|原片/i.test(el.innerText||'') && !/Animated GIF/i.test(el.innerText||'');
        }).map(el => ({ text: el.innerText.trim(),
            x: Math.round(el.getBoundingClientRect().x+el.getBoundingClientRect().width/2),
            y: Math.round(el.getBoundingClientRect().y+el.getBoundingClientRect().height/2) })))()"""
    )
    if not options:
        raise RuntimeError("找不到 720p 下载选项")
    await flow.tap(options[0]["x"], options[0]["y"])

    size = 0
    for _ in range(90):
        await asyncio.sleep(0.5)
        size = await flow.js("window.__capturedVideoBlob ? window.__capturedVideoBlob.size : 0")
        if size and size > 300000:
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
    def is_fresh(tile):
        base = (tile.get("src") or "").split("?")[0]
        if not base or base in pre_srcs:
            return False
        return ("Generated video" in (tile.get("alt") or "")) or ("/asb/" in base) or (tile.get("tag") == "VIDEO")

    t0 = time.time()
    while time.time() - t0 < timeout:
        await asyncio.sleep(5.0)
        elapsed = int(time.time() - t0)
        await flow.hover_neutral()
        tiles = await flow.get_media_tiles()
        fresh = sorted(
            [t for t in tiles if is_fresh(t) and t["y"] < 340 and t["x"] < 550],
            key=lambda t: (round(t["y"] / 40), t["x"]),
        )
        progress = await flow.js(
            """(() => [...document.querySelectorAll('*')].filter(el => {
                const r = el.getBoundingClientRect();
                return el.children.length===0 && r.y<880 && r.x>50 && /^\\d{1,3}%$/.test((el.innerText||'').trim());
            }).map(el => el.innerText.trim()))()"""
        )
        failed = await flow.js(
            """(() => [...document.querySelectorAll('*')].filter(el => {
                const r = el.getBoundingClientRect();
                const t = (el.innerText||'').trim();
                return el.children.length===0 && r.y>60 && r.y<320 && r.x>50 && /(失敗|无法生成|政策|Failed|violate|Unable to generate)/i.test(t);
            }).map(el => el.innerText.trim()))()"""
        )
        print(f"  [{elapsed}s] fresh={len(fresh)}/{expect} progress={progress}", flush=True)
        if failed and not progress and not fresh and elapsed >= 15:
            raise RuntimeError(f"Flow 拒绝生成: {failed[:3]}")
        if elapsed >= 25 and len(fresh) >= expect and not progress:
            return fresh[:expect]
    raise TimeoutError(f"等待新成片超时（{timeout}s）")


async def generate_sequence(flow, cfg, seq, out_mp4, sheet_png, force_settings=False):
    """完整跑一个镜头：清 prompt -> 挂载参考图 -> 注入 prompt -> 提交 -> 下载 -> QA。"""
    from .cdp import FlowCDP  # noqa: F401  (类型提示用)

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
        """(() => {
            const b = [...document.querySelectorAll('button')].find(x =>
                /启动世代|Start generation/i.test(x.getAttribute('aria-label')||'') ||
                ((x.innerText||'').trim()==='arrow_forward' && x.getBoundingClientRect().y>880));
            if (!b || b.disabled) return null;
            const r = b.getBoundingClientRect();
            return { x: r.left+r.width/2, y: r.top+r.height/2 };
        })()"""
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
    back = await flow.js(
        """(() => {
            const b = [...document.querySelectorAll('button')].find(x =>
                /Done editing|Back button/i.test(x.getAttribute('aria-label')||'') || (x.innerText||'').trim()==='Done');
            if (!b) return null;
            const r = b.getBoundingClientRect();
            return { x: r.left+r.width/2, y: r.top+r.height/2 };
        })()"""
    )
    if back:
        await flow.tap(back["x"], back["y"])
    else:
        await flow.esc()
    await asyncio.sleep(1.0)

    return make_contact_sheet(out_mp4, sheet_png, cfg.path("frames"))
