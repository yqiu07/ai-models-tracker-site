# 2026/05/11/16:08
# name: 数据架构重构报告 v3
# description: Model Navigate 数据存储架构从 5 张表精简为 3+1 结构的重构报告

---

## 概述

将 Model Navigate 的数据存储从**混乱的 5 张中间表**精简为**3 个核心文件 + 1 个运行记录**的清晰架构，流水线从 9 步精简为 6 步。

核心设计原则：**时效性增量更新**——总表是唯一真相源，每次追踪只关心"有没有新的"。

---

## 新架构

```
data/
├── Object-Models.xlsx          ← ① 总表（唯一真相源，只增不减）
├── increments/                 ← ② 增量日志（按次归档）
│   ├── 20260508_run1053.xlsx
│   └── ...
├── Backup/                     ← ③ 备份（每次写入总表前自动快照）
│   ├── Object-Models_20260509_195300.xlsx
│   └── ...
└── run_log.csv                 ← ④ 运行记录（轻量追溯）
```

### 角色定义

| 文件 | 角色 | 更新逻辑 |
|------|------|---------|
| **Object-Models.xlsx** | 唯一真相源 | 只增不减，每次流水线结束增量合并新模型 |
| **increments/RUN_ID.xlsx** | 增量归档 | 每次触发产出的新增模型，含"触发时间"列 |
| **Backup/Object-Models_*.xlsx** | 安全备份 | 写入总表前自动快照，可回滚 |
| **run_log.csv** | 运行记录 | run_id, since, until, trigger_time, new_count, source, pushed |

### 已删除的旧表

| 旧表 | 原角色 | 被替代方式 |
|------|--------|-----------|
| Object-Models-Old.xlsx | 基线 | → 总表去重替代 |
| Object-Models-Medium.xlsx | 快照备份 | → Backup/ 替代 |
| Object-Models-Updated.xlsx | 工作台 | → 总表+增量替代 |
| Object-Models-Updated - only.xlsx | 增量快照 | → increments/ 替代 |

---

## 新流水线（v3, 6 步）

```
步骤1: 数据采集      → auto_collect.py（llmstats+腾讯研究院+HuggingFace+平台目录）
步骤2: 增量去重      → 与总表去重，提取本次新增
步骤3: LLM 审核      → review_models.py（可选）
步骤4: 合并归档      → 增量写入总表 + 备份 + 归档到 increments/
步骤5: 钉钉推送      → push_dingtalk.py
步骤6: 运行记录      → run_log.csv + Trace/
```

### 对比旧流水线

| 维度 | v2（旧） | v3（新） |
|------|---------|---------|
| 步骤数 | 9 | 6 |
| 表格数 | 5 | 1 + 增量归档 |
| 去重基准 | Updated vs Medium | 直接与总表对比 |
| 增量追溯 | 无（每次覆盖） | increments/ 按次归档 |
| 运行历史 | 仅 Trace | run_log.csv + Trace |

---

## 关键代码改动

| 文件 | 改动 | 行数变化 |
|------|------|---------|
| `main.py` | 重写流水线步骤定义和执行函数 | 1500→829 行 |
| `push_dingtalk.py` | EXCEL_PATH 改为读总表 | +3 行 |
| `auto_collect.py` | 平台目录加 2026+ 时间过滤 | +15 行 |

### main.py 新步骤函数

- `step_collect_data()` — 调用 auto_collect.py 采集
- `step_dedup_against_master()` — 与总表去重，输出增量
- `step_merge_and_archive()` — 合并到总表 + 备份
- `step_write_run_log()` — 运行记录 + Trace

---

## 使用方式

```bash
# 标准追踪（采集→去重→合并→推送）
python main.py --since 20260508 --until 20260511 --push

# 仅采集不推送
python main.py --since 20260508 --until 20260511

# 从指定步骤开始
python main.py --step 4 --since 20260508 --until 20260511

# 预览模式
python main.py --since 20260508 --until 20260511 --dry-run

# 查看运行历史
cat data/run_log.csv
```

---

## 数据治理改进

1. **时效性过滤**：平台目录只采集 2026+ 模型（`cutoff_ts=1735689600`）
2. **增量原则**：每次只关心"总表里没有的新模型"
3. **触发时间记录**：增量表含"触发时间"列，可追溯每个模型何时被发现
4. **备份策略**：写入总表前自动快照，可随时回滚
5. **轻量追溯**：run_log.csv 无需打开 Excel 即可查看全部运行历史

---

## 后续方向

- [ ] 更新 SKILL.md 适配 v3 架构
- [ ] 验证完整流水线端到端跑通
- [ ] 考虑 run_log.csv → SQLite 升级（数据量增大后）
- [ ] 备份自动清理策略（保留最近 N 份）
