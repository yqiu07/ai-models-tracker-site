# AI 模型追踪项目

> 目标：系统化追踪全球AI模型发布动态，明确各厂商旗舰模型版本号、对齐国内外趋势，按选型标准评估后接入评测链路。

---

## 项目概览

| 指标 | 数值 |
|---|---|
| **当前模型总数** | 247 |
| 原有模型 | 158（`Object-Models-Old.xlsx`） |
| 本次新增 | 89（标记 New） |
| 数据来源 | 腾讯研究院AI速递（19篇）+ llm-stats.com（7个排行榜） |
| 最近更新 | 2026-04-16 |

---

## 目录结构

```
action/
├── Object-Models-Updated.xlsx   ← 主表格（247条，含标记列）
├── Object-Models-Old.xlsx       ← 原始表格（158条，用于对比）
├── README.md                    ← 本文件
│
├── Crawl/                       ← 数据采集
│   ├── Arena_x/                 ← llm-stats.com 排行榜数据（7个文件）
│   └── TXresearch/              ← 腾讯研究院爬虫脚本
│
├── Extract/                     ← 数据提取
│   ├── articles/                ← 19篇腾讯研究院文章（txt）
│   ├── crawl_articles.py        ← 文章爬取脚本
│   ├── extract_models.py        ← 模型提取脚本
│   ├── Taxonomy.xlsx            ← 字段填写规范
│   ├── Focus.xlsx               ← 重点关注的机构/公司
│   ├── TXCrawl.xlsx             ← 腾讯研究院文章列表
│   ├── TXCrawl_result.xlsx      ← 提取结果（含新兴模型列）
│   └── README.md                ← Extract 模块说明
│
├── Test/                        ← 核实与更新脚本
│   ├── update_models.py         ← 腾讯研究院67个模型录入
│   ├── extract_llmstats.py      ← llmstats模型提取
│   ├── update_llmstats.py       ← llmstats14个模型录入
│   ├── final_update.py          ← 综合更新（补充模型+benchmark+标记列）
│   ├── verify_models.py         ← 模型信息核实
│   ├── check_result.py          ← 数据完整性检查
│   ├── hf_verify_results.json   ← HuggingFace核实缓存
│   └── README.md                ← 核实方法说明
│
└── Report/                      ← 更新报告
    ├── update_report_20260416.md ← 首次更新报告（含可视化图表）
    ├── generate_report.py       ← 报告生成脚本（可复用）
    └── README.md                ← 报告文件夹说明
```

---

## 工作流程

```
1. 获取信息（Crawl/Extract）
   ├── 腾讯研究院AI速递 → 爬取文章 → AI阅读提取模型
   └── llm-stats.com → 复制排行榜数据 → 解析表格

2. 去重过滤（Test）
   └── 与 Object-Models-Old.xlsx 对比 → 剔除已追踪模型

3. 信息核实（Test）
   ├── 开源模型 → HuggingFace 模型页
   ├── 闭源模型 → 官方发布页 / 平台入口
   ├── Qwen系列 → 阿里云百炼
   └── benchmark → llm-stats.com 排行榜

4. 录入更新（Test）
   └── 写入 Object-Models-Updated.xlsx + 标记列

5. 生成报告（Report）
   └── 运行 generate_report.py → 输出 update_report_YYYYMMDD.md

6. 同步到伦理小群
```

---

## 表格字段说明

| 字段 | 说明 | 填写规范 |
|---|---|---|
| 模型名称 | 用 API 接口名 | 参考 `Taxonomy.xlsx` |
| 是否接入 | 是否已接入评测 | — |
| workflow接入进展 | 接入状态 | — |
| 公司 | 发布公司 | — |
| 国内外 | 国内/国外 | — |
| 开闭源 | 开源/闭源/集成产品 | — |
| 尺寸 | 参数量 | 找不到则留空 |
| 类型 | 基座/领域/微调/多模态/智能体 | 优先选领域而非微调 |
| 能否推理 | thinking/non-thinking | 无CoT/diffusion一律non-thinking |
| 任务类型 | 主要任务 | — |
| 官网 | 官方页面链接 | — |
| 备注 | 补充信息 | — |
| 记录创建时间 | 录入日期 | — |
| 是否新增 | New/空 | 与Old.xlsx对比 |
| 数据来源 | 原有/腾讯研究院/llmstats | — |
| 核实方式 | 核实渠道 | HuggingFace/官网/公开榜单/web_search |

---

## 数据来源

| 渠道 | 地址 | 关注重点 |
|---|---|---|
| **llm-stats.com** | https://llm-stats.com | AI News、Leaderboards 前三个 |
| **Arena** | https://arena.ai/leaderboard | Text 字段、Arena Overview |
| **腾讯研究院** | https://news.qq.com/omn/author/8QMc2nlf74IUvjvZ | AI速递系列简讯 |
| **X 账号** | @rowancheung、@Zai_org 等 | 官方发布动态 |
| **官方机构** | 见 `Extract/Focus.xlsx` | 各公司官网/博客 |

---

## 快速开始（用户使用指南）

### 环境准备

```bash
# 确保已安装 Python 3.10+ 和以下依赖
pip install pandas openpyxl
```

### 一键运行完整流水线

```bash
cd D:\yuwang\action
python main.py
```

运行后将依次执行 8 个步骤，最终产出：
- `Object-Models-Updated.xlsx` — 更新后的模型表格
- `Report/update_report_YYYYMMDD.md` — 更新报告
- `Crawl/Arena_x/formatted_leaderboards.md` — 排行榜汇总

### 常用命令

| 命令 | 说明 |
|------|------|
| `python main.py` | 完整流水线（从头到尾） |
| `python main.py --dry-run` | 预览模式，不实际执行 |
| `python main.py --step 5` | 从第 5 步开始（跳过前面已完成的步骤） |
| `python main.py --skip-verify` | 跳过核实状态步骤 |

### 流水线步骤说明

```
步骤 1：准备基线        — 复制 Old.xlsx → Updated.xlsx
步骤 2：录入腾讯研究院  — 追加腾讯研究院AI速递中提取的新模型
步骤 3：录入 llmstats   — 追加 llm-stats.com 排行榜中的新模型
步骤 4：综合更新        — 补充模型 + benchmark 数据更新 + "是否新增"列
步骤 5：添加核实状态    — 添加"核实情况"列 + HuggingFace 核实的尺寸更新
步骤 6：数据完整性检查  — 输出字段覆盖率统计
步骤 7：生成更新报告    — 输出 Markdown 格式报告（含可视化图表）
步骤 8：整理 Case 文件  — 将原始排行榜数据整理为标准 Markdown 表格
```

### 如何进行一次新的更新

1. **采集数据**：运行 `Crawl/` 下的爬虫脚本，或手动收集新模型信息
2. **提取模型**：运行 `Extract/extract_models.py`，从文章中提取新模型列表
3. **填入数据**：将新模型数据填入 `Test/` 下对应脚本的 `NEW_MODELS` 列表中
4. **一键运行**：`python main.py`
5. **人工抽检**：打开 `Object-Models-Updated.xlsx`，抽查新增模型的字段准确性
6. **生成报告**：步骤 7 已自动生成，也可单独运行 `python main.py --step 7`

### 前置文件要求

| 文件 | 说明 | 必须存在 |
|------|------|----------|
| `Object-Models-Old.xlsx` | 原始基线表格（用于对比标记"是否新增"） | ✅ |
| `Test/update_models.py` | 腾讯研究院模型数据（硬编码） | ✅ |
| `Test/update_llmstats.py` | llmstats 模型数据（硬编码） | ✅ |
| `Test/final_update.py` | 综合更新脚本 | ✅ |

---

## 初始动作

> 以下为项目启动时的原始操作指南，保留作为参考。

● 日常维护
    ○ 模型追踪：系统化监控全球AI模型发布动态，覆盖文生文（基座/领域/微调）、多模态、物理模型、智能体、trending产品及具身智能六大类；通过公开榜单（LLM-Stats、Arena）、公众号、X账号、官网等多渠道获取信息；按国内（阿里、字节、月之暗面等）与国外（OpenAI、Google DeepMind、Meta等）分层重点追踪；规范更新Models文档字段，包括模型名称、公司、开闭源、尺寸、类型、任务类型、官网、备注等，并同步至伦理小群。
在D:\yuwang\action\Object-Models.xlsx这里面追踪
目标：追踪AI发布动态，明确各厂商旗舰模型版本号、对齐国内外趋势。按照选型标准评估后接入评测链路
1.https://llm-stats.com 重点关注字段AI News、和leaderboards的前三个
2.https://arena.ai/leaderboard 重点关注Text字段，以及往下找到Arena Overview
1. 公众号：腾讯研究院 https://news.qq.com/omn/author/8QMc2nlf74IUvjvZ
2. X账号：@rowancheung、@Zai_org等官方账号  
 https://x.com/rowancheung
https://x.com/Zai_org
1. 官方机构、组织、公司...见 D:\yuwang\action\Extract\Focus.xlsx

建议动作是：
1. 获取信息
    a. 信息源以腾讯研究院发布类简讯为主、其他长文查漏补缺。
    b. 单独检查公开榜单涉及的模型，标准版全都要更新到表格D:\yuwang\action\Object-Models.xlsx里。 
2. 核实信息
    a. 开源模型在hugging face看到模型页之后按上面的信息填写，包括尺寸、特点、和上一版相比主要的优化方向...  
    b. 闭源模型找到发布页或平台入口即可，信息一般少一点，主要选类型和任务类型字段，其他主要用途等补充信息写在备注里。
    c. qwen系列在阿里云百炼上找到官方名称
3. 更新在D:\yuwang\action\Object-Models.xlsx文档里，字段填写规范如下 D:\yuwang\action\Extract\Taxonomy.xlsx
4. 同步到伦理小群
