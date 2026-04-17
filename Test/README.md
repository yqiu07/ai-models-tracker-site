## Test 文件夹说明

本文件夹存放模型追踪任务中的**数据核实与更新脚本**。

---

### 文件清单

| 文件 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `update_models.py` | 将腾讯研究院提取的67个新模型录入表格 | `Object-Models-Updated.xlsx` | 同文件（追加行） |
| `extract_llmstats.py` | 从llmstats排行榜数据中提取未追踪模型 | `Object-Models-Updated.xlsx` + llmstats文件 | 终端输出候选列表 |
| `update_llmstats.py` | 将llmstats的14个新模型录入表格 | `Object-Models-Updated.xlsx` | 同文件（追加行） |
| `final_update.py` | 综合更新：补充8个模型 + benchmark数据 + "是否新增"列 | `Object-Models-Updated.xlsx` + `Object-Models-Old.xlsx` | 同文件 |
| `verify_models.py` | 通过 web_search 核实模型信息（尺寸、官网等） | 模型名称列表 | 终端输出核实结果 |
| `check_result.py` | 检查更新后表格的数据完整性 | `Object-Models-Updated.xlsx` | 终端输出统计 |
| `hf_verify_results.json` | HuggingFace 核实结果缓存 | — | JSON |

---

### 核实方法说明

#### 整体流程

```
数据源文件 → 提取模型候选 → 去重（与已有表格对比）→ 信息核实 → 录入表格
```

#### 核实手段

| 核实对象 | 方法 | 可信度 |
|---|---|---|
| **模型名称** | AI阅读原文提取 + 人工确认 | ⭐⭐⭐⭐ |
| **公司归属** | 原文明确标注 / web_search 确认 | ⭐⭐⭐⭐⭐ |
| **开闭源** | 原文标注 / HuggingFace 页面 / 官方发布页 | ⭐⭐⭐⭐⭐ |
| **尺寸（参数量）** | HuggingFace 模型页 / 官方技术博客 | ⭐⭐⭐⭐ |
| **类型** | AI根据Taxonomy规范判断 | ⭐⭐⭐ |
| **能否推理** | 官方说明是否支持CoT/thinking | ⭐⭐⭐ |
| **官网链接** | web_search 查找官方页面 | ⭐⭐⭐⭐ |
| **benchmark数据** | llm-stats.com 排行榜直接引用 | ⭐⭐⭐⭐ |
| **备注描述** | AI综合多个来源撰写 | ⭐⭐⭐ |

#### 核实渠道

- **开源模型** → HuggingFace 模型页（参数量、架构、License）
- **闭源模型** → 官方发布页 / 平台入口（功能描述、定价）
- **Qwen系列** → 阿里云百炼平台（官方名称、API接口名）
- **benchmark** → llm-stats.com（Code Arena、Chat Arena、GPQA、SWE-bench等）

#### 核实原则

1. **硬信息无法核实则留空**：尺寸、官网等字段，找不到可靠来源宁可不填
2. **软信息可以AI生成**：备注中的描述性内容由AI综合多来源撰写
3. **去重采用模糊匹配**：normalize后比较（忽略大小写、短横线、空格），核心名称包含即视为同一模型
4. **筛选剔除非模型项**：纯工具/框架/功能更新/未发布项不录入

#### HuggingFace 实际核实结果（04-17 更新）

通过 `urllib.request` 访问 HuggingFace API 对开源模型逐个核实：

| 状态 | 模型 | 结果 |
|---|---|---|
| ✅ 成功 | Mistral Small 4 (119B) | 119.4B, Apache-2.0, MoE 128专家4激活 |
| ✅ 成功 | Whisper Large V3 Turbo | 809M, MIT, automatic-speech-recognition |
| ✅ 成功 | Sarvam-105B | MoE(未公开), Apache-2.0, 多语言(印度语言) |
| ✅ 成功 | Voxtral Mini | 4.7B, Apache-2.0, 多语言 |
| ❌ 401 | Gemma 4 27B-IT / E2B / E4B | 需在浏览器中同意 License |
| ❌ 401 | GLM-5.1 | 需在浏览器中同意 License |
| ❌ 401 | Sarvam-30B | 需在浏览器中同意 License |
| ❌ 401 | Mamba-3 | 需在浏览器中同意 License |
| ⏭️ 未尝试 | 14 个闭源模型 | 不在 HuggingFace 上 |

脚本：`add_verify_status.py`

#### "核实情况"列说明

表格中新增的"核实情况"列如实记录每个模型的核实执行结果，而非建议的核实方式。标注规则：

| 标注 | 含义 |
|---|---|
| `真的做了 web_search` | 通过 web_search 工具实际搜索并获取了信息 |
| `HuggingFace API 成功` | 通过 urllib.request 访问 HF API 获取了参数量/License |
| `HuggingFace 401` | 访问了 HF API 但返回 401 需授权 |
| `公开榜单直接引用` | 数据直接来自 llm-stats.com，无需额外核实 |
| `未单独核实` | 未对该模型执行独立的核实操作 |

#### 已知局限

- **类型和能否推理字段**：AI判断可能有偏差，建议人工抽检
- **模型名称别名**：不同数据源对同一模型命名不一致（如 `claude-opus-4.6` vs `claude-opus-4-6`），可能导致漏匹配
- **尺寸覆盖率低**（~15%）：大部分闭源/多模态模型不公开参数量
- **官网覆盖率中等**（~45%）：部分小众模型未找到官方页面
- **6 个 HuggingFace 401 模型**：需在浏览器中手动同意 License 后才能通过 API 访问

---

### Case 文件整理工具

`Crawl/Arena_x/format_cases.py` 可将原始 Case 文件（从 llm-stats.com 复制的不规整数据）整理为人机可读的 Markdown 表格。

**使用方式**：
```bash
cd D:\yuwang\action\Crawl\Arena_x
python format_cases.py
```

**支持的格式**：
| 格式 | 示例文件 | 解析方式 |
|---|---|---|
| Code Arena / Chat Arena | `Case-llmstats-AI leaderboards STT.md` | 排名+公司+模型+tab数据 |
| 图像生成 | `Case-llmstats-AI leaderboards-image generation.md` | 同上 |
| TTS / STT | `Case-llmstats-AI leaderboards TTS.md` | 同上 |
| LLM Leaderboard | `Case-llmstats-LLM Leaderboards.md` | logo行+模型名+国旗行+数据行 |
| 模型更新时间线 | `LLM-updates-byllmstats.md` | 日期+公司+模型+类型+License |

**输出**：`formatted_leaderboards.md`
