# EP04 制作交接指令（给本地 WorkBuddy）

把下面 `===== 指令开始 =====` 到 `===== 指令结束 =====` 之间的全部内容，复制粘贴到本地 WorkBuddy 的新会话作为第一条消息发送。这段是自包含的，不需要我们这次对话的任何上下文。

===== 指令开始 =====

你现在接力制作一部已经跑通 EP01-EP03 的豪门复仇短剧的 **EP04**。严格按下面的流程做，不要自行简化、不要改角色设定、不要跳过质检步骤。所有工作在当前回合内做完再回报，不要说"后台执行"。

## 剧情位置

前情（EP01-03 已定稿）：Claire 是隐秘的 "V"，掌管 Vance Capital。她被前夫 Marcus 为五万美金抛弃、当众羞辱后，暗中并购了 Sterling，在 EP03 清晨完成收购，揭穿身份、清算 Marcus 与情妇 Chloe，留下话："这只是开局，Vance Capital 才刚开始。"

EP04 主题：**清算正式开始**。董事会审计启动 → 反派密谋反扑 → Marcus 伪造签名诬陷 → Claire 出示鉴证证据反杀 → Marcus 崩溃 → Claire 宣告"这不是收购，是清算"。承接 EP03 结尾，节奏保持冷冽克制。

## 第零步：先看片（动手前必须做）

在写任何东西、生成任何镜头之前，先实际看一遍已定稿的 EP01-EP03 成片，把人物长相、服装、场景、表演节奏和剧情衔接看进脑子，再往下写。不要只看文字梗概就动手。

用抽帧方式看片（ffmpeg 每隔数秒抽一帧，再用看图工具逐张看）：

```
cd "C:\Users\Administrator\.gemini\antigravity\scratch\short_drama_western_broken_engagement_ep01\output"
```

要看的成片（中英双语版，带字幕便于对剧情）：
- `EP01_02_Combined_Full_EN_ZH_1080p60.mp4`（100s，EP01+EP02 合并版，优先看这个）
- `EP03_Western_Broken_Engagement_EN_ZH_1080p60.mp4`（60s，紧接的上一集，必须看）

如需分开看单集：`EP01_Western_Broken_Engagement_EN_ZH_1080p60.mp4`（61s）、`EP02_Western_Broken_Engagement_EN_ZH_1080p60.mp4`（52s）。

抽帧命令示例（每 2 秒一帧，输出到临时图目录后逐张查看）：

```
mkdir -p /tmp/ep_review
ffmpeg -y -i "EP03_Western_Broken_Engagement_EN_ZH_1080p60.mp4" -vf "fps=0.5,scale=540:-1" /tmp/ep_review/ep03_%03d.jpg
```

看片时重点确认，作为 EP04 的衔接基准：
- 各角色实际长相与服装：Claire（象牙风衣、灰裙、全干）、Damien（黑色羊绒大衣）、Marcus（炭灰三件套）、Chloe（深红礼服）——后续严禁换脸换装。
- 反复出现的场景：棋盘大理石门厅、深色胡桃木吊灯宴会厅、带红色 V 印章的蓝色建筑蓝图。
- 结尾情绪与悬点：EP03 收在 Claire 宣告"这只是开局"，EP04 要从这里无缝接上。
- 表演节奏：冷冽克制、硬切、人物在句末自然闭嘴，不要夸张表情。

看完用两三句话说明你从片里确认的角色/场景/衔接点，再进入下一步。

## 第一步：读规范与剧本

1. 用文件读取工具读交接手册并完全遵守：
   `C:\Users\Administrator\.gemini\antigravity\scratch\short_drama_western_broken_engagement_ep01\FLOW_CDP_HANDOFF_FOR_WORKBUDDY.md`
2. EP04 六镜剧本已经写好，直接用，不要重写 prompt：
   `flow-cdp-pipeline/examples/ep04_sequences.json`
   （仓库路径 `C:\Users\Administrator\WorkBuddy AI\2026-11-16-14-31-31\flow-cdp-pipeline`；若本地没有则从 `https://github.com/zzzzxp000228-prog/flow-cdp-pipeline.git` 克隆）

## 第二步：环境与连接

- 依赖：`pip install -r requirements.txt` 和 `pip install faster-whisper numpy`；ffmpeg/ffprobe 加入 PATH。
- 离线自检：`python tests/smoke_test.py`，预期最后一行 `RESULT: ALL PASS`。
- 配置：`cp config/settings.example.json config/settings.json`，把 `project_root` 设为项目根目录：
  `C:\Users\Administrator\.gemini\antigravity\scratch\short_drama_western_broken_engagement_ep01`
- 连 Chrome：不要写死 9222。从
  `C:\Users\Administrator\AppData\Local\Google\Chrome\User Data\DevToolsActivePort`
  读第一行端口 + 第二行路径拼 WebSocket，连 browser 端点后 `Target.getTargets` 找 `flow.google.com/project/` 标签页。标准 Chrome profile 不支持 `/json/list`。找不到标签页就先在 Chrome 打开并登录 Flow 项目页。

## 新场景生成规则（仅当现有资产不够时触发）

EP04 六镜剧本已经全部映射到既有资产（ballroom 宴会厅 / foyer 门厅 / blueprint_seal 蓝图印章），正常情况下**不需要生成新场景**。如果实际生成中发现某个环境板不合适、确实缺新场景，按下面规则处理：

- 用 **Google Flow 内置的生图工具**现场生成新场景图。不要改用外部生图服务、不要用本地软件拼图、不要换掉角色参考图、也不要改写镜头 prompt 硬凑。
- 复用已经建立的那条 CDP 单连接，不要新开连接。在 Flow 里切到图片生成/工具模式，用 `Runtime.evaluate` 观察当前 UI 定位生图入口和输入框，按现场实际界面操作（交接手册只覆盖了视频生成和素材上传，生图入口没有现成脚本封装，需要你像之前逆向 picker 那样现场定位——这一步本机未执行，属现场操作）。
- 生图 prompt 规范：空景、无人物、无酒杯；写明光线（清晨冷光 / 暖吊灯）和材质（胡桃木 / 棋盘大理石 / 黄铜）；风格跟既有 plate 一致（真实胶片质感，不要插画或卡通）。
- 生成的图片用与 720p Blob 下载相同的方式保存到项目 `assets/`，命名 `plate_<场景名>.jpg`，横向场景板优先 16:9。
- 落盘后登记：写进 `flow_manifest.json` 的 assets 段和 `config/settings.json` 的 assets 映射（key 如 `boardroom`），再把 `examples/ep04_sequences.json` 对应镜头的 refs 换成新 key。仍然遵守每镜参考图 ≤3 张、人脸 ≤2 张的规则。
- 若只是换角度/光线就能用现有场景，优先复用，不为省事新建资产。

## 新人物生成规则（仅当现有角色不够时触发）

EP04 六镜只用既有角色（Claire / Damien / Marcus / Chloe），正常情况下**不需要新人物**。如果剧情确实需要新角色（例如董事会主席、鉴证专家），按下面规则：

- 用 **Google Flow 内置的生图工具**现场生成新人物图。不要用外部生图服务、不要本地拼图、不要拿既有角色改脸改名凑数。
- 复用已建立的那条 CDP 单连接，切到 Flow 图片生成模式；生图入口没有现成脚本封装，按现场实际 UI 定位输入和操作（本机未实测，属现场操作）。
- 新人物 prompt 规范：成年角色，写清年龄、性别、服装、发型、神态；风格与既有角色板一致（真实胶片质感、写实皮肤纹理，不要插画/卡通）。给稳定可复用的固定描述，便于后续镜头保持同一张脸。
- **不得改动或替换任何既有角色**（Claire 全程全干、象牙风衣；Marcus 炭灰三件套；Chloe 深红礼服；Damien 黑色羊绒大衣），新人物是新增，不是覆盖。
- 生成的图片用与 720p Blob 下载相同的方式存到项目 `assets/`，命名 `char_<角色名>.jpg`，人物肖像用竖版或方图。
- 落盘后登记：写进 `flow_manifest.json` 的 assets 段和 `config/settings.json` 的 assets 映射（key 如 `board_chair`），再把需要该角色的镜头 refs 换成新 key。
- **人脸数量红线**：每镜参考图 ≤3 张、人脸 ≤2 张。加入新人物后若某镜变成 3 张人脸，会触发 Flow「prominent people」政策过滤被拒——必须把该镜 refs 压回 ≤2 人脸（换掉一张人脸为场景/道具板），不要硬塞。

## 第三步：生成六镜原片

所有命令在仓库根目录执行：

```
python cli_generate.py --plan examples/ep04_sequences.json --seqs 1,2,3,4,5,6
```

关键规则（违反会翻车）：
- 单条 WebSocket 连接跑完整批，不要多连接。
- x1 省积分锁，拒绝 x2/x3/x4 误触。
- 参考图按文件名挂搜索浮层：点 plus → 搜文件名 → 点结果行进 prompt box；搜索框残留用 `el.select()` + 真实 Delete 键清；每镜最多 3 张。剧本里每镜的 refs 已控制在 1-2 张人脸 + 场景/道具板，规避 Flow 三人脸政策过滤——不要改动 refs。
- prompt 必须 `execCommand('insertText')` 注入。
- 720p Blob 捕获下载，不在 Flow 里升分辨率。
- 每镜输出 `clips/candidates/seqNN_cand1.mp4` + `assets/frames/seqNN_cand1_sheet.png`（20 宫格）。逐张看 QA 图：角色是否一致（Claire 必须全干、象牙风衣、干发；无酒杯）、口型是否在 3.9s/9.3s 前闭嘴。有问题用 `--force` 单独重跑该镜。

## 第四步：质检与转录

```
python cli_qa.py --glob "clips/candidates/seq0*_cand1.mp4" --out audio/qa_ep04.json
python cli_transcribe.py --glob "clips/candidates/seq0*_cand1.mp4"
```

- 看每镜 scdet 硬切点（预期在 4.2s 前后）和 RMS 峰值、speech 区间。
- 转录给出词级时间戳。**字幕必须以实际开口台词为准**，不要照抄剧本 prompt。

## 第五步：后期总成

根据 qa 与 transcribe 的真实结果写 `build_plan.json`（参考 `examples/build_plan.example.json`）：
- 每镜拆 A/B 两段：`ss`/`ee` 卡 scdet 硬切点（A 段约 0.25-4.30，B 段约 4.33-9.95）。
- `subs` 的起止秒用转录词级时间戳，相对该 piece 起点；每句 `[起点, 终点, 英文字幕, 中文字幕]`。
- 结尾卡文案改成：
  - `line_en`: `THE RECKONING BEGINS`
  - `line_zh`: `清算才刚刚开始`
  - `line_next`: `EPISODE 05  |  NEXT`
- `output_stem`: `EP04_Western_Broken_Engagement`

```
python cli_master.py --plan /path/to/build_plan.json
```

预期输出（1080x1920@60fps，Clean / EN / EN_ZH 三版本 + QA 拼图）：
```
output/EP04_Western_Broken_Engagement_Clean_1080p60.mp4
output/EP04_Western_Broken_Engagement_EN_1080p60.mp4
output/EP04_Western_Broken_Engagement_EN_ZH_1080p60.mp4
output/final_qa_sheet_ep04.png
```
最后看一眼 QA 拼图：字幕位置、角色一致性、无酒杯、结尾卡正常。

## 硬边界

- 严禁修改 `output/` 下已有的 EP01、EP02、EP01_02_Combined、EP03 成片。只新增 EP04 文件。
- 角色与场景资产沿用 `flow_manifest.json` 与 `assets/`，严禁换脸、换服装风格。Claire 全程全干、象牙风衣。
- 若需新场景或新人物，只用 Google Flow 内置生图工具生成，按上面「新场景生成规则」「新人物生成规则」落盘登记；不引入外部生图、不改动既有角色资产。新增人物不得替换既有角色，且每镜人脸数仍须 ≤2。
- 每一步给一句进度；失败明确报卡在哪步和报错原文，不要静默跳过。

===== 指令结束 =====
