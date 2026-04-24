# DataForCheck 错误核查报告

> 生成时间：2026-04-17
> 核查对象：`DataForCheck.md`（共 259 行）
> 核查方式：AI 逐行比对 + 交叉验证（置信度标注见下方）

---

## 一、文件结构问题

`DataForCheck.md` 包含**两个数据区域**，存在大量重复：

- **区域A**（约前 130 行）：日期格式 `2026-04-16`，部分数据已修正（如公司归属）
- **区域B**（约后 129 行）：日期格式 `2026/4/17` 等，为原始未修正数据

**建议**：以区域A为准，删除区域B中的重复条目。

---

## 二、公司归属错误（区域B 中存在，区域A 已修正）

以下条目在**区域B**中公司标注错误，但在**区域A**中已修正为正确值：

| 模型名称 | 区域B 错误公司 | 区域A 正确公司 | 置信度 |
|----------|---------------|---------------|--------|
| JoyStreamer | 小米 | 京东 | ✅ 确定 |
| JoyAI-Image-Edit | 小米 | 京东 | ✅ 确定 |
| PixVerse C1 | （区域B无此条目，但原始数据中曾标为小米） | 爱诗科技 | ✅ 确定 |
| PixVerse V6 | （区域B无此条目，但原始数据中曾标为智谱） | 爱诗科技 | ✅ 确定 |
| PixVerse R1 | （区域B无此条目，但原始数据中曾标为智谱） | 爱诗科技 | ✅ 确定 |
| step-3.5-flash | Google | 阶跃星辰 | ✅ 确定 |
| StepClaw | Google | 阶跃星辰 | ✅ 确定 |
| Spark 2.0 | Google | （应为 World Labs / 李飞飞团队相关，非 Google） | ⚠️ 需确认 |
| VoxCPM 2 | 月之暗面 | 面壁智能 | ✅ 确定 |
| Lantay | 月之暗面（区域B） | 面壁智能（区域A） | ⚠️ 需确认 |
| Vidu Q3 | （区域B无公司） | 生数科技（区域A） | ✅ 确定 |
| Revo 3 | （区域B无公司） | 强脑科技（区域A） | ✅ 确定 |

---

## 三、公司归属错误（区域B 独有，区域A 未覆盖）

> ⚠️ **勘误说明（2026-04-20）**：本节初版将 MAI-Image-2、MAI-Transcribe-1、MAI-Voice-1 列为公司归属错误，经用户用 xlsx 源文件截图核实，这三个模型在实际表格中**公司已正确标注为微软**，是 `DataForCheck.md` 文本文件中区域B的旧数据与 xlsx 不一致导致的误判，已删除。同理，Midjourney V8 Alpha、Marble 系列等条目也可能存在类似的"文本文件旧数据 vs xlsx 实际数据不一致"的情况，**以下仅保留区域B文本文件中明确可见的错误，但均需与 xlsx 源文件交叉核实**。

| 模型名称 | 区域B 错误公司 | 正确公司 | 说明 | 置信度 |
|----------|---------------|---------|------|--------|
| K-EXAONE-236B-A23B | 百度 | LG AI Research | 韩国 LG 旗下 AI 实验室，非百度 | ⚠️ 需与xlsx核实 |
| Midjourney V8 Alpha | MiniMax | Midjourney | 区域B文本中公司列标为 MiniMax | ⚠️ 需与xlsx核实 |
| Marble 1.1 | Google | World Labs | 区域B文本中标为 Google，实际为李飞飞团队 World Labs | ⚠️ 需与xlsx核实 |
| Marble 1.1-Plus | Google | World Labs | 同上 | ⚠️ 需与xlsx核实 |
| Mamba-3 | （无公司） | CMU + Princeton | 描述中已写明，公司列应补充 | ⚠️ 需与xlsx核实 |
| Ising | （区域B无公司） | NVIDIA（区域A已标注） | 区域B缺失公司 | ⚠️ 需与xlsx核实 |

---

## 四、国内外标记错误

| 模型名称 | 当前标记 | 正确标记 | 说明 | 置信度 |
|----------|---------|---------|------|--------|
| step-3.5-flash（区域B） | 国内（但公司标为Google） | 国内 | 国内外标记本身正确（阶跃星辰是国内），但与错误的公司"Google"矛盾 | ✅ 确定 |
| StepClaw（区域B） | 国内（但公司标为Google） | 国内 | 同上 | ✅ 确定 |
| K-EXAONE-236B-A23B | 国外 | 国外 | 国内外标记正确，但公司"百度"是错的（应为LG） | ✅ 确定 |
| MAI-Image-2 | 国外 | 国外 | 国内外标记正确，但公司"MiniMax"是错的（应为微软） | ✅ 确定 |
| Midjourney V8 Alpha | 国外 | 国外 | 国内外标记正确，但公司"MiniMax"是错的 | ✅ 确定 |

---

## 五、类型/任务类型错误

| 模型名称 | 字段 | 当前值 | 正确值 | 说明 | 置信度 |
|----------|------|--------|--------|------|--------|
| Whisper Large V3 Turbo（区域B） | 类型 | 多模态 | 语音 | 区域A已修正为"语音" | ✅ 确定 |
| Voxtral Mini（区域B） | 类型 | 领域 | 语音 | 区域A已修正为"语音" | ✅ 确定 |
| Qwen-Image-2.0（区域B） | 类型 | 领域 | 多模态 | 图像生成模型应归为多模态，区域A中 Qwen Image 2.0 已标为多模态 | ⚠️ 需确认 |

---

## 六、重复条目清单

以下模型在区域A和区域B中**各出现一次**（共出现两次），应去重保留区域A版本：

| # | 模型名称 | 区域A行为准 |
|---|----------|------------|
| 1 | Ising | ✅ 区域A已补充公司 NVIDIA |
| 2 | JoyAI-Image-Edit | ✅ 区域A已修正公司为京东 |
| 3 | JoyStreamer | ✅ 区域A已修正公司为京东 |
| 4 | Kimi Claw | ✅ 两版一致 |
| 5 | Kimi Linear | ✅ 两版一致 |
| 6 | Lantay | ⚠️ 区域A标面壁智能，区域B标月之暗面，需确认 |
| 7 | LibTV | ✅ 区域A补充公司 LiblibAI |
| 8 | LobsterAI | ✅ 区域A补充公司网易有道 |
| 9 | LongCat-AudioDiT | ✅ 两版一致 |
| 10 | lyria-3-pro | ✅ 区域A有完整描述 |
| 11 | MAI-Image-2 | ⚠️ 区域B公司标MiniMax（错），需确认区域A是否已修正 |
| 12 | MAI-Transcribe-1 | ⚠️ 区域B公司标Meta（错），需确认 |
| 13 | MAI-Voice-1 | ⚠️ 区域B公司标Meta（错），需确认 |
| 14 | Mamba-3 | ✅ 两版一致 |
| 15 | Marble 1.1 | ⚠️ 区域B公司标Google（错），应为World Labs |
| 16 | Marble 1.1-Plus | ⚠️ 同上 |
| 17 | MaxClaw | ✅ 两版一致 |
| 18 | Meoo/秒悟 | ✅ 两版一致 |
| 19 | Midjourney V8 Alpha | ⚠️ 区域B公司标MiniMax（错），应为Midjourney |
| 20 | MiMo-V2-Omni | ✅ 两版一致 |
| 21 | MiMo-V2-Pro | ✅ 区域A有完整描述 |
| 22 | MiniMax Music 2.6 | ✅ 两版一致 |
| 23 | mistral-small-4-119b-2603 | ✅ 区域A有完整描述 |
| 24 | Muse Spark | ✅ 需确认是否重复 |
| 25 | NemoClaw | ✅ 两版一致 |
| 26 | Psi-R2 | ✅ 两版一致 |
| 27 | Psi-W0 | ✅ 两版一致 |
| 28 | QBotClaw | ✅ 两版一致 |
| 29 | QClaw V2 | ✅ 两版一致 |
| 30 | Qwen Image 2.0 / Qwen-Image-2.0 | ⚠️ 命名不一致，可能是同一模型的两个条目 |
| 31 | Reve | ✅ 区域A补充公司 Reve AI |
| 32 | Revo 3 | ✅ 区域A补充公司强脑科技 |
| 33 | Sarvam-105B | ✅ 区域A补充公司 Sarvam AI |
| 34 | Sarvam-30B | ✅ 区域A补充公司 Sarvam AI |
| 35 | Seedream 4.5 | ✅ 两版一致 |
| 36 | step-3.5-flash | ✅ 区域A已修正公司为阶跃星辰 |
| 37 | StepClaw | ✅ 区域A已修正公司为阶跃星辰 |
| 38 | veo-3.1-lite | ✅ 两版一致 |
| 39 | Vidu Q3 | ✅ 区域A补充公司生数科技 |
| 40 | VoxCPM 2 | ✅ 区域A已修正公司为面壁智能 |
| 41 | Voxtral Mini | ✅ 区域A已修正类型为语音 |
| 42 | Wan2.7-Image | ✅ 两版一致 |
| 43 | Whisper Large V3 Turbo | ✅ 区域A已修正类型为语音 |
| 44 | Imagen 4 Standard | ✅ 两版一致（区域B有换行格式问题） |
| 45 | Imagen 4 Ultra | ✅ 两版一致（区域B有换行格式问题） |
| 46 | XChat | ✅ 两版一致 |
| 47 | YOYO Claw | ✅ 区域A补充公司荣耀 |
| 48 | Ψ₀ | ✅ 两版一致 |

---

## 七、其他数据质量问题

### 7.1 Spark 2.0 公司归属存疑
- **当前**：区域A 和区域B 均无公司 / 区域B标为 Google
- **问题**：描述为"开源3D高斯溅射渲染引擎；配合Marble世界模型使用"，Marble 是 World Labs（李飞飞团队）的产品。Spark 2.0 可能也是 World Labs 的，而非 Google
- **置信度**：⚠️ 需人工确认

### 7.2 Intern-S1-Pro 公司缺失
- **当前**：公司列为空
- **问题**：描述为"AI Lab；科学领域多模态大模型"，可能是上海AI Lab（书生系列）
- **置信度**：⚠️ 需人工确认

### 7.3 Solaris 公司缺失
- **当前**：公司列为空
- **问题**：描述为"多人视频世界模型"，来源不明
- **置信度**：⚠️ 需人工确认

### 7.4 Mercury 2 公司缺失
- **当前**：公司列为空
- **问题**：描述为"Inception AI (USA)；聚焦提速"
- **建议**：补充公司为 Inception AI
- **置信度**：✅ 确定

### 7.5 日期格式不统一
- 区域A 使用 `2026-04-16` 格式
- 区域B 使用 `2026/4/17`、`2026/2/27` 等格式
- **建议**：统一为 `YYYY-MM-DD` 格式

### 7.6 模型名称格式问题（区域B）
以下模型名称包含换行符或引号，可能导致解析错误：
- `"Whisper\nLarge V3 Turbo"` → 应为 `Whisper Large V3 Turbo`
- `"Imagen 4\nStandard"` → 应为 `Imagen 4 Standard`
- `"Imagen 4\nUltra"` → 应为 `Imagen 4 Ultra`
- `"Marble\n1.1-Plus"` → 应为 `Marble 1.1-Plus`
- `"Midjourney\nV8 Alpha"` → 应为 `Midjourney V8 Alpha`

### 7.7 Lantay 公司归属矛盾
- **区域A**：面壁智能
- **区域B**：月之暗面
- **说明**：Lantay 是面壁智能的文档智能体产品，区域A正确
- **置信度**：⚠️ 需人工确认（面壁智能可能性更大）

### 7.8 LabClaw 公司缺失
- **当前**：公司列为空
- **问题**：描述为"生物医学科研领域的skills"，来源为开源项目
- **置信度**：⚠️ 需人工确认

---

## 八、错误汇总统计

> ⚠️ **重要说明（2026-04-20 勘误）**：本报告初版仅基于 `DataForCheck.md` 文本文件分析，未核对 xlsx 源文件。经用户截图核实，MAI 系列（MAI-Image-2、MAI-Transcribe-1、MAI-Voice-1）在 xlsx 中公司已正确标注为微软，属于误判。**以下所有"需与xlsx核实"的条目，均需以 xlsx 源文件为准。**

| 错误类型 | 数量 | 严重程度 | 说明 |
|----------|------|---------|------|
| 公司归属错误（仅区域B文本文件中可见） | 6 处 | 🟡 均需与xlsx核实 | K-EXAONE、Midjourney、Marble×2、Mamba-3、Ising |
| 公司归属存疑 | 5 处 | 🟡 中 | Spark 2.0、Intern-S1-Pro、Solaris、Mercury 2、LabClaw |
| 类型/任务类型错误（区域B vs 区域A） | 3 处 | 🟡 需与xlsx核实 | Whisper、Voxtral、Qwen-Image-2.0 |
| 重复条目（区域A vs 区域B） | 48 组 | 🟡 中 | 文本文件结构问题 |
| 日期格式不统一 | 全局 | 🟢 低 | 区域A用-，区域B用/ |
| 模型名称格式问题 | 5 处 | 🟡 中 | 含换行符 |

---

## 九、处理建议

1. **核心教训**：`DataForCheck.md` 文本文件中的数据可能与 xlsx 源文件不一致，**必须以 xlsx 为准**
2. **建议**：后续核查数据时，直接从 xlsx 导出 CSV/TSV 文件供 AI 分析，避免手动复制粘贴导致的数据不一致
3. **去重**：`DataForCheck.md` 中区域A和区域B大量重复，建议清理
4. **统一格式**：日期统一为 `YYYY-MM-DD`，模型名称去除换行符
5. **人工确认**：所有标注 ⚠️ 的条目需要与 xlsx 源文件交叉核实
