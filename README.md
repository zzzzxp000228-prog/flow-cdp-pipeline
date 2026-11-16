# flow-cdp-pipeline

用 Chrome DevTools Protocol 驱动 Google Flow 批量生成视频，再用 FFmpeg 做后期总成的可复用管线。

核心能力：
- 单条 WebSocket 连接跑完整批（Chrome 136+ 对弹窗/新标签有限制，多连接会失败）。
- x1 出图锁：主动校验并拒绝 x2/x3/x4 误触，避免多倍扣积分。
- 参考图按文件名挂载，适配 Flow 2026-11 搜索驱动 picker，最多 3 张。
- 720p Blob 无损下载（不在 Flow 里花积分升分辨率），后期统一 Lanczos+CAS 升到 1080p60。
- 生成后先做 scdet 硬切点 + 0.1s 音频 RMS + whisper 台词转录，再决定剪辑点。
- 输出 Clean / EN / EN_ZH 三版本 + QA 拼图。

## 目录结构

```
flow-cdp-pipeline/
├── README.md                    本文件
├── LICENSE                      MIT
├── requirements.txt             Python 依赖
├── .gitignore
├── config/
│   ├── settings.example.json    配置模板（复制成 settings.json 后改）
│   └── settings.json            本地配置（gitignore，含个人路径）
├── core/                        可复用模块
│   ├── config.py                配置加载 + 环境变量覆盖 + 路径解析
│   ├── selectors.py             selector/坐标/等待参数集中配置（改版只改这里）
│   ├── cdp.py                   CDP 单连接客户端 + 素材上传
│   ├── settings.py              Flow 设置锁定（分辨率/时长/x1）
│   ├── assets.py                参考图挂载（新版搜索 picker + 超时保护）
│   ├── prompt.py                prompt 注入（execCommand）
│   ├── generate.py              提交/轮询/720p Blob 下载/抽帧 QA
│   ├── qa.py                    scdet + RMS 包络
│   ├── transcribe.py            faster-whisper 词级时间戳
│   └── master.py                FFmpeg 后期总成
├── cli_upload.py                上传素材
├── cli_generate.py              批量生成镜头
├── cli_qa.py                    原片质检
├── cli_transcribe.py            台词转录
├── cli_master.py                后期总成
├── examples/
│   ├── sequences.example.json   镜头定义示例
│   └── build_plan.example.json  后期计划示例
└── tests/
    └── smoke_test.py            离线冒烟测试（不连浏览器）
```

## 依赖

```bash
# Python 3.10+
pip install -r requirements.txt

# ffmpeg / ffprobe（加入 PATH）
# Windows:  winget install Gyan.FFmpeg
# macOS:    brew install ffmpeg
# Ubuntu:   sudo apt install ffmpeg

# 可选：台词转录需要的模型会在首次运行时自动下载（small.en）
```

## 浏览器准备

1. 用**带远程调试端口**的 Chrome 打开你的 Flow 项目页（`https://flow.google.com/project/<uuid>`）。
2. 需要已登录 Google 账号。
3. 确认 `DevToolsActivePort` 文件存在：
   - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort`
   - macOS: `~/Library/Application Support/Google/Chrome/DevToolsActivePort`
   - Linux: `~/.config/google-chrome/DevToolsActivePort`

用系统默认 profile 启动（复用登录态）示例：

```bash
# Windows（PowerShell）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

`config.py` 会自动读 `DevToolsActivePort` 拿到真实端口（Chrome 有时会忽略你指定的端口），不需要手动填。

## 配置

```bash
cp config/settings.example.json config/settings.json
```

编辑 `config/settings.json`：

| 字段 | 说明 |
|---|---|
| `project_root` | 项目根目录，所有相对路径的基准 |
| `manifest` | manifest 文件名（相对 project_root） |
| `devtools_file` | 留空自动探测；也可填绝对路径 |
| `cdp_url` | 可选，直接写 `ws://127.0.0.1:PORT/devtools/browser/...` 覆盖探测 |
| `target_url_match` | 用来定位 Flow 标签页的 URL 子串 |
| `dirs` | assets / candidates / frames / audio / output / selected 各目录 |
| `count_lock` | 出图数量锁，默认 `x1` |
| `allowed_counts` | 允许的 count 值 |
| `assets` | 素材 key -> 文件名，挂载参考图时用 key 引用 |
| `fonts` | ASS 字幕字体与 drawtext 字体文件路径 |

环境变量优先级更高：

```bash
FLOW_CONFIG=/path/to/settings.json
FLOW_PROJECT_ROOT=/path/to/project
FLOW_CDP_URL=ws://127.0.0.1:9222/devtools/browser/xxxx
CHROME_DEVTOOLS_FILE=/path/to/DevToolsActivePort
```

## 完整工作流

所有命令在仓库根目录执行。

### 1. 冒烟测试（离线，不连浏览器）

```bash
python tests/smoke_test.py
# 预期：全部 PASS，最后一行 RESULT: ALL PASS
```

### 2. 上传素材

把角色/场景图片放进 `assets/`（文件名要和 `config.assets` 里的值对应），然后：

```bash
python cli_upload.py
# 预期：每个 key 打印 uploaded / attached，flow_manifest.json 里出现 assets 段
```

### 3. 定义镜头

复制 `examples/sequences.example.json`，改写 `sequences`。每个镜头字段：

- `name`：镜头名（日志用）
- `refs`：参考图 key 列表，最多 3 个（必须在 config.assets 里）
- `res` / `dur` / `count`：分辨率 / 时长 / 出图数
- `prompt`：完整提示词，必须包含 `Active References Lock` 校验串
- `poll_timeout`：等待新成片的最长秒数

提示词规范（减少废片）：
- 写死 `Real-time 24fps motion, hard cuts only, strictly NO wine glasses anywhere, strictly NO BGM, strictly NO on-screen subtitles.`
- 台词要求 `finishing before X.Xs` 并自然闭嘴，方便后期卡硬切点。
- 不用 `masterpiece` / `8K` / `best quality` 这类堆砌词，用具体光学/胶片/皮肤描述。

### 4. 批量生成

```bash
python cli_generate.py --plan examples/sequences.example.json --seqs 1,2,3
# 已存在的 cand1.mp4 会跳过；强制重跑加 --force
# 每镜输出：clips/candidates/seqNN_cand1.mp4 + assets/frames/seqNN_cand1_sheet.png（20 宫格）
```

### 5. 原片质检

```bash
python cli_qa.py --glob "clips/candidates/seq*_cand1.mp4" --out audio/qa.json
# 打印每镜 scdet 硬切点、峰值 RMS、speech 区间；结果写入 audio/qa.json
```

### 6. 台词转录（需要词级时间戳时）

```bash
pip install faster-whisper numpy
python cli_transcribe.py --glob "clips/candidates/seq*_cand1.mp4"
# 输出 audio/transcript.json，含每个词的 s/e/p（起止秒与置信度）
```

### 7. 后期总成

根据 qa + transcribe 的结果，写 `build_plan.json`（参考 `examples/build_plan.example.json`）：

- `pieces[].ss` / `ee`：原片裁剪起止秒，卡 scdet 硬切点。
- `pieces[].subs`：`[相对起点秒, 结束秒, 英文字幕, 中文字幕]`，来自词级时间戳。
- `endcard`：结尾卡三行文案。

```bash
python cli_master.py --plan /path/to/build_plan.json
# 输出：
#   output/<stem>_Clean_1080p60.mp4
#   output/<stem>_EN_1080p60.mp4
#   output/<stem>_EN_ZH_1080p60.mp4
#   output/final_qa_sheet.png
```

## 已逆向的坑（改代码前先看）

1. **Flow picker 2026-11 改版**：旧的滚动列表 + `Add to prompt` 失效。新版是搜索浮层：`搜索资产 / Search assets` 输入框 -> 输入文件名 -> 点结果行直接进 prompt box。`core/assets.py` 已适配。
2. **plus 首次点击可能只出 tooltip**：`open_picker` 会重试最多 8 次直到搜索框出现。
3. **搜索框残留文本**：必须 `el.select()` + 真实 Delete 键，只 `insertText` 会在 Angular input 里累加成 `a.jpg_a.jpg`。
4. **prompt 注入**：必须 `document.execCommand('insertText', false, text)`，直接赋值 `.innerText` 不会更新 Angular 模型。
5. **DevToolsActivePort 端口会变**：不要写死 9222，读文件拿真实端口。
6. **faster-whisper 的 av 兼容**：新版 av 的 `open()` 没有 `metadata_errors` 参数。`core/transcribe.py` 用 ffmpeg f32le + numpy 绕过内置解码。
7. **切点检测阈值**：`scdet=threshold=8.0` 是验证值，太低会误检镜头内运动。
8. **BGM 侧链**：`sidechaincompress` 让人声出现时背景音乐自动闪避，参数在 `core/master.py` 的 `audio_filter`。

## Flow 改版怎么适配（不用翻代码）

所有界面文案正则、DOM 选择器、坐标阈值、等待参数都集中在 `core/selectors.py` 的 `DEFAULT`，
运行时由 `Config.sel` 暴露（`sel.text.*` / `sel.dom.*` / `sel.geometry.*` / `sel.timing.*`）。
Flow 改版后按现象定位，只改配置，不动业务模块：

- 按钮/搜索框找不到 -> 改 `selectors.text`（用 `|` 分隔中英文，如 `"搜索资产|Search assets"`）。
- 元素找得到但坐标不对（结果行、fresh tile、进度条、设置浮层）-> 改 `selectors.geometry`。
  这些值跟 `viewport` 强相关，改分辨率时一起调。
- 轮询太慢/太快、重试不够 -> 改 `selectors.timing`。

本地 override 写在 `config/settings.json` 的 `selectors` 段即可，做深合并，未写的字段沿用默认值。
例：

```json
{
  "selectors": {
    "text": { "asset_search": "Find assets" },
    "geometry": { "result_row_min_y": 300, "result_row_max_y": 900 },
    "timing": { "poll_interval": 2.0 }
  }
}
```

`python tests/smoke_test.py` 会校验默认值完整、动态 JS 花括号平衡、配置覆盖生效且不污染默认。

## 模块化设计

每个模块独立可测、可替换：

- 换浏览器自动化框架：只改 `core/cdp.py`。
- 换 Flow UI 结构：只改 `core/assets.py` 的 JS 选择器。
- 换 ASR 引擎：只改 `core/transcribe.py`。
- 换后期规格：改 build plan 的 `spec` 字段，不动 `core/master.py`。

所有参数外置到配置或 CLI，不在源码里写死路径。

## License

MIT
