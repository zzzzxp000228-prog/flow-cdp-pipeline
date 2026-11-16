"""后期总成：按 PIECES 裁剪 -> concat -> BGM 侧链混音 -> 三版本字幕 -> QA 拼图。

规格：1080x1920@60fps / bt709 / lanczos+cas / loudnorm I=-16 TP=-1.5 LRA=9。
PIECES 从 JSON 读入（见 examples/build_plan.example.json），切点和字幕时间来自 qa.py + transcribe.py。
"""
import json
import math
import os
import struct
import subprocess
import wave


def _run(cmd):
    subprocess.run(cmd, check=True)


def ffprobe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        text=True,
    )
    return float(json.loads(out)["format"]["duration"])


def generate_tension_score(out_wav, total_dur, endcard_dur=1.8):
    """合成低调 noir 弦乐 + 心跳脉冲 BGM（纯 math + wave，无外部素材）。"""
    sr = 48000
    n = int(sr * total_dur)
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        buf = bytearray(n * 4)
        for i in range(n):
            t = i / sr
            env = 1.0
            if t < 0.4:
                env *= t / 0.4
            elif t > total_dur - 0.5:
                env *= max(0.0, (total_dur - t) / 0.5)

            bass = 73.42 if t < 18.0 else (58.27 if t < 37.5 else 82.41)
            sub = (0.50 * math.sin(2 * math.pi * bass * t)
                   + 0.22 * math.sin(2 * math.pi * bass * 2.0 * t)
                   + 0.14 * math.sin(2 * math.pi * bass * 3.0 * t))
            pad = (0.18 * math.sin(2 * math.pi * 220.0 * t + 0.015 * math.sin(2 * math.pi * 1.1 * t))
                   + 0.12 * math.sin(2 * math.pi * 261.63 * t))

            pulse = 0.0
            phase = (t * 2.0) % 1.0
            if t < total_dur - endcard_dur and phase < 0.09:
                pulse = 0.16 * math.exp(-phase * 48.0) * math.sin(2 * math.pi * 110.0 * t)

            boom = 0.0
            te = t - (total_dur - endcard_dur)
            if 0.0 <= te < 1.5:
                boom = 0.45 * math.exp(-te * 2.6) * math.sin(2 * math.pi * 55.0 * te)

            val = env * (0.14 * (sub + pad) + pulse) + 0.24 * boom
            val = max(-0.85, min(0.85, val))
            struct.pack_into("<hh", buf, i * 4, int(val * 32767), int(val * 0.98 * 32767))
        wf.writeframes(buf)


def _ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(path, timeline_subs, fonts, bilingual=True):
    """timeline_subs: [(start, end, en_text, zh_text)]。"""
    en_font = fonts.get("en", "Arial")
    zh_font = fonts.get("zh", "Microsoft YaHei")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: EnSub,{en_font},40,&H00FFFFFF,&H000000FF,&H00101014,&H96000000,-1,0,0,0,100,100,0.4,0,1,3.6,1.8,2,56,56,288,1
Style: ZhSub,{zh_font},37,&H00E8D49A,&H000000FF,&H00101014,&H96000000,-1,0,0,0,100,100,0.6,0,1,3.4,1.6,2,56,56,222,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, en_text, zh_text in timeline_subs:
        t0, t1 = _ass_time(start), _ass_time(end)
        en_margin = 288 if bilingual else 246
        lines.append(f"Dialogue: 1,{t0},{t1},EnSub,,0,0,{en_margin},,{en_text}")
        if bilingual and zh_text:
            lines.append(f"Dialogue: 0,{t0},{t1},ZhSub,,0,0,222,,{zh_text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def normalize_piece(piece, out_mp4, spec):
    """裁一段并归一化到目标规格。piece 里 ss/ee 是原片绝对秒。"""
    ss = piece["ss"]
    dur = round(piece["ee"] - ss, 3)
    fade_out = max(0.02, dur - 0.015)
    pre_vf = f"{piece['pre_vf']}," if piece.get("pre_vf") else ""
    vf = (
        f"trim=start={ss}:duration={dur},setpts=PTS-STARTPTS,"
        f"{pre_vf}"
        f"scale={spec['width']}:{spec['height']}:flags=lanczos,cas={spec['cas']},"
        f"fps={spec['fps']},format=yuv420p"
    )
    af = (
        f"atrim=start={ss}:duration={dur},asetpts=PTS-STARTPTS,"
        "aformat=sample_rates=48000:channel_layouts=stereo,"
        f"afade=t=in:st=0:d=0.015,afade=t=out:st={fade_out:.3f}:d=0.015"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", piece["src"], "-vf", vf, "-af", af,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(spec.get("crf_piece", 16)),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out_mp4,
    ])
    return ffprobe_duration(out_mp4)


def build_endcard(out_mp4, spec, endcard):
    """生成文字结尾卡。文案从 plan 的 endcard 配置读入。"""
    w, h, fps = spec["width"], spec["height"], spec["fps"]
    dur = endcard.get("duration", 1.8)
    font_en = spec.get("fonts", {}).get("en_bold", "C\\:/Windows/Fonts/arialbd.ttf")
    font_zh = spec.get("fonts", {}).get("zh_bold", "C\\:/Windows/Fonts/msyhbd.ttc")
    font_plain = spec.get("fonts", {}).get("en", "C\\:/Windows/Fonts/arial.ttf")

    def esc(text):
        return text.replace("'", "\\'")

    vf = (
        f"fps={fps},format=yuv420p,"
        f"drawtext=fontfile='{font_en}':text='{esc(endcard['line_en'])}':fontcolor=#D4AF37:fontsize=50:"
        "x=(w-text_w)/2:y=800:alpha='if(lt(t,0.3),t/0.3,1)',"
        f"drawtext=fontfile='{font_zh}':text='{esc(endcard['line_zh'])}':fontcolor=#FFFFFF:fontsize=46:"
        "x=(w-text_w)/2:y=895:alpha='if(lt(t,0.45),max(0,(t-0.12)/0.33),1)',"
        f"drawtext=fontfile='{font_plain}':text='{esc(endcard['line_next'])}':fontcolor=#A8A8B2:fontsize=30:"
        "x=(w-text_w)/2:y=1010:alpha='if(lt(t,0.6),max(0,(t-0.25)/0.35),1)'"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=#0B0B0F:s={w}x{h}:r={fps}:d={dur}",
        "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={dur}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(spec.get("crf_piece", 16)),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", out_mp4,
    ])
    return ffprobe_duration(out_mp4)


def make_master_qa_sheet(master_mp4, piece_offsets, total_dur, out_png, work_dir, spec):
    """每段取中点帧 + 结尾卡，5 列网格拼图。"""
    os.makedirs(work_dir, exist_ok=True)
    tiles = []
    for idx, (_pid, start, dur) in enumerate(piece_offsets, 1):
        t_mid = min(total_dur - 0.1, start + dur * 0.55)
        tile = os.path.join(work_dir, f"_qa_tile_{idx:02d}.png")
        vf = (
            "scale=270:480,"
            "drawbox=x=0:y=0:w=270:h=34:color=black@0.72:t=fill,"
            "drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
            f"text='#{idx:02d} {t_mid:.1f}s':fontcolor=#F0D078:fontsize=16:x=8:y=9"
        )
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t_mid:.3f}",
              "-i", master_mp4, "-frames:v", "1", "-vf", vf, tile])
        tiles.append(tile)

    end_tile = os.path.join(work_dir, "_qa_tile_end.png")
    vf_end = (
        "scale=270:480,"
        "drawbox=x=0:y=0:w=270:h=34:color=black@0.72:t=fill,"
        f"drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
        f"text='END {total_dur-0.5:.1f}s':fontcolor=#F0D078:fontsize=16:x=8:y=9"
    )
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{total_dur-0.5:.3f}",
          "-i", master_mp4, "-frames:v", "1", "-vf", vf_end, end_tile])
    tiles.append(end_tile)

    # 补到 15 张（5x3）
    pad = os.path.join(work_dir, "_qa_tile_pad.png")
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
          "-f", "lavfi", "-i", "color=c=#0B0B0F:s=270x480:d=1", "-frames:v", "1", pad])
    while len(tiles) < 15:
        tiles.append(pad)

    inputs = []
    for p in tiles[:15]:
        inputs.extend(["-i", p])
    layout = "|".join(f"{(i % 5) * 270}_{(i // 5) * 480}" for i in range(15))
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
          "-filter_complex", f"xstack=inputs=15:layout={layout}", "-frames:v", "1", out_png])


def build_master(plan_path, cfg):
    """按 plan JSON 构建三版本成片。返回输出路径与时长。"""
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    spec = plan["spec"]
    spec.setdefault("fonts", cfg.fonts)
    pieces = plan["pieces"]
    # src 支持相对 project_root 的写法，也支持绝对路径
    for p in pieces:
        if not os.path.isabs(p["src"]):
            p["src"] = os.path.join(cfg.project_root, p["src"])
    work_selected = cfg.path("selected")
    work_audio = cfg.path("audio")
    out_dir = cfg.path("output")
    for d in (work_selected, work_audio, out_dir):
        os.makedirs(d, exist_ok=True)

    piece_files, timeline_subs, offsets = [], [], []
    cursor = 0.0
    for idx, p in enumerate(pieces, 1):
        out_p = os.path.join(work_selected, f"{p['id']}.mp4")
        actual = normalize_piece(p, out_p, spec)
        piece_files.append(out_p)
        offsets.append((p["id"], cursor, actual))
        for s_off, e_off, en_text, zh_text in p.get("subs", []):
            st = cursor + max(0.02, s_off)
            en = min(cursor + actual - 0.03, cursor + e_off)
            if en > st + 0.15:
                timeline_subs.append((st, en, en_text, zh_text))
        cursor += actual
        print(f"[master] {idx:02d}/{len(pieces)} {p['id']}: {actual:.3f}s", flush=True)

    endcard_mp4 = os.path.join(work_selected, "endcard.mp4")
    end_dur = build_endcard(endcard_mp4, spec, plan["endcard"])
    piece_files.append(endcard_mp4)
    total = cursor + end_dur
    print(f"[master] total {cursor:.3f}s + {end_dur:.3f}s = {total:.3f}s", flush=True)

    concat_list = os.path.join(work_audio, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in piece_files:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")

    raw = os.path.join(work_audio, "raw_concat.mp4")
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
          "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", raw])

    bgm = os.path.join(work_audio, "bgm.wav")
    generate_tension_score(bgm, total, plan["endcard"].get("duration", 1.8))
    mixed = os.path.join(work_audio, "mixed.wav")
    audio_filter = (
        "[0:a]loudnorm=I=-16:TP=-1.5:LRA=9,asplit=2[dlg1][dlg2];"
        "[1:a]volume=0.82[bgm];"
        "[bgm][dlg1]sidechaincompress=threshold=0.015:ratio=4.5:attack=15:release=260[ducked];"
        "[dlg2][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.94[aout]"
    )
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-i", bgm,
          "-filter_complex", audio_filter, "-map", "[aout]", "-ar", "48000", "-ac", "2", mixed])

    stem = plan["output_stem"]
    clean = os.path.join(out_dir, f"{stem}_Clean_1080p60.mp4")
    en = os.path.join(out_dir, f"{stem}_EN_1080p60.mp4")
    bilingual = os.path.join(out_dir, f"{stem}_EN_ZH_1080p60.mp4")

    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-i", mixed,
          "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", clean])

    ass_en = os.path.join(work_audio, "subs_en.ass")
    ass_bi = os.path.join(work_audio, "subs_bi.ass")
    write_ass(ass_en, timeline_subs, spec["fonts"], bilingual=False)
    write_ass(ass_bi, timeline_subs, spec["fonts"], bilingual=True)

    for ass_file, target in ((ass_en, en), (ass_bi, bilingual)):
        ass_esc = ass_file.replace("\\", "/").replace(":", "\\:")
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", clean,
              "-vf", f"ass='{ass_esc}'",
              "-c:v", "libx264", "-preset", "medium", "-crf", str(spec.get("crf_sub", 17)),
              "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
              "-c:a", "copy", "-movflags", "+faststart", target])
        print(f"[master] rendered {target} ({os.path.getsize(target)/1024/1024:.2f} MB)", flush=True)

    qa_png = os.path.join(out_dir, plan.get("qa_sheet", "final_qa_sheet.png"))
    make_master_qa_sheet(bilingual, offsets, total, qa_png, work_audio, spec)
    print(f"[master] QA sheet: {qa_png}", flush=True)
    return {"clean": clean, "en": en, "bilingual": bilingual, "qa": qa_png, "duration": total}
