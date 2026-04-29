"""
AI 模型追踪 —— 端到端一键更新流水线（v2 自动化版）

使用方式：
    python main.py --since 20260417 --until 20260423    # 指定时间段
    python main.py --since 20260417                     # until 默认今天
    python main.py                                      # 默认最近 7 天
    python main.py --step 3                             # 从第3步开始
    python main.py --dry-run                            # 预览流程
    python main.py --source llmstats                    # 只跑 llmstats 数据源

流水线步骤（v2.1, 9步）：
    === 数据准备 ===
    1. 准备基线：备份 Updated→Medium，复制 Old→Updated
    2. 自动化数据采集：llmstats + 腾讯研究院 → 去重 → HuggingFace 核实 → 写入 Excel
       2.5 LLM 提取腾讯研究院模型：读取文章全文 → LLM API 提取 → 回写主表格
    === 检查 ===
    3. 数据完整性检查：运行 Test/check_result.py
    === 报告与整理 ===
    4. 生成更新报告：运行 Report/generate_report.py
    5. 整理 Case 文件：运行 Crawl/Arena_x/format_cases.py
    === 质量保障 ===
    6. 对比新旧表格：Updated vs Medium，输出新增/原有/遗漏清单
    7. 同步新增模型：将新增模型写入 Object-Models-Updated - only.xlsx
    8. 生成验收报告：汇总 E2E-Test-Report.md + 更新 Update-Log.md
    === 推送 ===
    9. 钉钉推送日报：生成日报 Markdown 并推送到钉钉群（需 --push 参数）

前置条件：
    - Object-Models-Old.xlsx 存在（基线表格）
    - 请先关闭 Excel 中打开的相关文件

v2 变更（相对 v1 12步版）：
    - 步骤 2-6 合并为自动化数据采集（auto_collect.py）
    - 不再需要手动硬编码模型列表
    - 新增 --since/--until 时间段参数
    - llmstats 自动 HTTP 抓取 + Next.js RSC 解析
    - 腾讯研究院按时间段爬取 + 全文抓取
    - HuggingFace API 自动核实开源模型
    - 发布时间自动从数据源映射
"""
import subprocess
import sys
import os
import argparse
import shutil
from datetime import date, datetime
from pathlib import Path

# ============================================================
# 配置区（每次更新时修改这里）
# ============================================================

ACTION_DIR = Path(__file__).parent.resolve()

def _load_env():
    """加载 .env 文件，确保子进程也能继承环境变量（如 HF_TOKEN、DINGTALK_WEBHOOK 等）。"""
    env_path = ACTION_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

_load_env()

DATA_DIR = ACTION_DIR / "data"
REPORT_DIR = ACTION_DIR / "Report"
BASELINE_FILE = DATA_DIR / "Object-Models-Old.xlsx"
UPDATED_FILE = DATA_DIR / "Object-Models-Updated.xlsx"
MEDIUM_FILE = DATA_DIR / "Object-Models-Medium.xlsx"
ONLY_FILE = DATA_DIR / "Object-Models-Updated - only.xlsx"
BACKUP_DIR = ACTION_DIR / "Backup"
TEST_REPORT_FILE = REPORT_DIR / "E2E-Test-Report.md"
UPDATE_LOG_FILE = REPORT_DIR / "Update-Log.md"

TODAY = date.today().isoformat()
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ============================================================
# 步骤定义
# ============================================================

STEPS = [
    {
        "number": 1,
        "name": "准备基线",
        "description": "备份 Updated→Medium，复制 Old→Updated",
        "script": None,
    },
    {
        "number": 2,
        "name": "自动化数据采集",
        "description": "llmstats + 腾讯研究院 → 去重 → HuggingFace 核实 → 写入 Excel",
        "script": ACTION_DIR / "auto_collect.py",
    },
    {
        "number": 3,
        "name": "数据完整性检查",
        "description": "检查更新后表格的字段完整性",
        "script": ACTION_DIR / "Test" / "check_result.py",
    },
    {
        "number": 4,
        "name": "生成更新报告",
        "description": "生成 Markdown 格式的更新报告（含统计图表）",
        "script": ACTION_DIR / "Report" / "generate_report.py",
    },
    {
        "number": 5,
        "name": "整理 Case 文件",
        "description": "将 Crawl/Arena_x/ 下的原始 Case 文件整理为标准 Markdown 表格",
        "script": ACTION_DIR / "Crawl" / "Arena_x" / "format_cases.py",
    },
    {
        "number": 6,
        "name": "对比新旧表格",
        "description": "对比 Updated.xlsx 与 Medium.xlsx，输出新增/原有/遗漏模型清单",
        "script": None,
    },
    {
        "number": 7,
        "name": "同步新增模型",
        "description": "将本次新增的模型同步到 Object-Models-Updated - only.xlsx",
        "script": None,
    },
    {
        "number": 8,
        "name": "生成验收报告",
        "description": "汇总测试结果、对比结果，生成 E2E-Test-Report.md 和 Update-Log.md",
        "script": None,
    },
    {
        "number": 9,
        "name": "钉钉推送日报",
        "description": "生成 AI 模型追踪日报并推送到钉钉群（需要 --push 参数或 DINGTALK_WEBHOOK 环境变量）",
        "script": ACTION_DIR / "push_dingtalk.py",
    },
]

# ============================================================
# 工具函数
# ============================================================

def log(message, level="INFO"):
    """统一日志输出"""
    prefix = {"INFO": "✅", "WARN": "⚠️", "ERROR": "❌", "STEP": "🔹", "SKIP": "⏭️"}
    icon = prefix.get(level, "  ")
    print(f"  {icon} {message}")


def log_header(step_number, step_name, description):
    """步骤标题"""
    print(f"\n{'='*60}")
    print(f"  步骤 {step_number}: {step_name}")
    print(f"  {description}")
    print(f"{'='*60}")



def progress_bar(current, total, width=30):
    """渲染进度条字符串。"""
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    percent = int(100 * current / total)
    return f"[{current}/{total}] {bar} {percent}%"

def log_progress(step_num, total_steps, step_name):
    """显示整体流水线进度。"""
    bar = progress_bar(step_num, total_steps)
    print(f"\n{'─'*60}")
    print(f"  {bar}  步骤 {step_num}: {step_name}")
    print(f"{'─'*60}")

def run_subprocess_heartbeat(args, cwd=None, timeout_minutes=30, heartbeat_seconds=60,
                            silent_limit=300, label=None, capture=False):
    """通用心跳探测子进程运行器。

    30 分钟上限，每 60 秒探测子进程是否存活且有输出。
    如果超过 silent_limit 秒无任何输出，判定为不健康并终止。

    Args:
        args: 命令行参数列表
        cwd: 工作目录
        timeout_minutes: 最大运行时间（分钟），默认 30
        heartbeat_seconds: 心跳间隔（秒），默认 60
        silent_limit: 无输出多久判定为不健康（秒），默认 300
        label: 日志标签（如 "auto_collect.py"）
        capture: 是否捕获输出（True=不打印到终端，返回 stdout）

    Returns:
        (returncode: int, stdout: str)。stdout 仅 capture=True 时有内容。
    """
    import time as _time

    tag = label or str(args[0]) if args else "subprocess"
    max_wait = timeout_minutes * 60

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
        cwd=cwd,
    )

    elapsed = 0
    last_output_time = _time.time()
    collected_output = []

    while elapsed < max_wait:
        try:
            proc.wait(timeout=heartbeat_seconds)
            # 进程已结束，读取剩余输出
            remaining = proc.stdout.read() if proc.stdout else ""
            if remaining:
                collected_output.append(remaining)
                if not capture:
                    for line in remaining.strip().split('\n'):
                        if line.strip():
                            print(f"    {line.rstrip()}")
            break
        except subprocess.TimeoutExpired:
            elapsed += heartbeat_seconds
            # 读取所有可用输出
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    collected_output.append(line)
                    if not capture:
                        print(f"    {line.rstrip()}")
                    last_output_time = _time.time()
            except Exception:
                pass
            # 检查进程是否还在运行
            if proc.poll() is not None:
                break
            # 健康探测：如果超过 silent_limit 无输出，判定不健康
            silent_seconds = _time.time() - last_output_time
            if silent_seconds > silent_limit:
                log(f"{tag} 已 {int(silent_seconds)}s 无输出，判定为不健康，终止", "ERROR")
                proc.kill()
                proc.wait()
                return (-1, "".join(collected_output))
            minutes_elapsed = elapsed // 60
            log(f"💓 心跳 [{minutes_elapsed}min/{timeout_minutes}min] {tag} 运行中...", "INFO")

    returncode = proc.returncode if proc.returncode is not None else -1

    if elapsed >= max_wait and proc.poll() is None:
        log(f"{tag} 超时（{timeout_minutes}分钟），终止", "ERROR")
        proc.kill()
        proc.wait()
        return (-1, "".join(collected_output))

    return (returncode, "".join(collected_output))


def run_script(script_path, timeout_minutes=30, heartbeat_seconds=60, silent_limit=300):
    """运行 Python 脚本，心跳探测模式。"""
    if not script_path.exists():
        log(f"脚本不存在: {script_path}", "ERROR")
        return False

    returncode, _ = run_subprocess_heartbeat(
        [sys.executable, "-X", "utf8", str(script_path)],
        cwd=str(script_path.parent),
        timeout_minutes=timeout_minutes,
        heartbeat_seconds=heartbeat_seconds,
        silent_limit=silent_limit,
        label=script_path.name,
    )

    if returncode != 0:
        log(f"脚本执行失败（退出码 {returncode}）", "ERROR")
        return False

    return True


def check_prerequisites():
    """检查前置条件"""
    issues = []

    if not BASELINE_FILE.exists():
        issues.append(f"基线文件不存在: {BASELINE_FILE}")

    # 检查 Excel 是否被占用（尝试以写模式打开）
    for filepath in [BASELINE_FILE, UPDATED_FILE]:
        if filepath.exists():
            try:
                with open(filepath, "a"):
                    pass
            except PermissionError:
                issues.append(f"文件被占用（请关闭 Excel）: {filepath.name}")

    # 检查关键脚本是否存在
    for step in STEPS:
        if step["script"] and not step["script"].exists():
            issues.append(f"脚本不存在: {step['script']}")

    return issues


def check_midway_prerequisites():
    """从中间步骤开始时的前置检查"""
    issues = []

    if not UPDATED_FILE.exists():
        issues.append(f"Updated 文件不存在（从中间步骤开始需要先完成前面的步骤）: {UPDATED_FILE}")

    # 检查 Excel 是否被占用
    for filepath in [UPDATED_FILE]:
        if filepath.exists():
            try:
                with open(filepath, "a"):
                    pass
            except PermissionError:
                issues.append(f"文件被占用（请关闭 Excel）: {filepath.name}")

    return issues


def backup_current():
    """备份当前的 Updated.xlsx"""
    if not UPDATED_FILE.exists():
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    backup_name = f"Object-Models-Updated_{TIMESTAMP}.xlsx"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(UPDATED_FILE, backup_path)
    log(f"已备份: {backup_path.name}")


# ============================================================
# 步骤 1：准备基线（内置逻辑）
# ============================================================

def step_prepare_baseline():
    """
    复制基线文件。
    注意：update_models.py 内部硬编码了 SOURCE = Object-Models.xlsx，
    所以步骤 1 需要同时准备好这个文件（从 Old.xlsx 复制），
    让步骤 2 的 shutil.copy2 能正常执行。

    质量保障：在覆盖 Updated.xlsx 之前，先备份为 Medium.xlsx，
    供步骤 10 对比使用。
    """
    import pandas as pd

    if not BASELINE_FILE.exists():
        log(f"基线文件不存在: {BASELINE_FILE}", "ERROR")
        return False

    # 如果 Updated 已存在，先备份为 Medium（供后续对比）
    if UPDATED_FILE.exists():
        shutil.copy2(UPDATED_FILE, MEDIUM_FILE)
        log(f"已备份为 Medium: {UPDATED_FILE.name} → {MEDIUM_FILE.name}")
        medium_row_count = len(pd.read_excel(MEDIUM_FILE))
        log(f"Medium 模型数量: {medium_row_count}")
        # 同时做一份带时间戳的备份
        backup_current()
    else:
        log("Updated.xlsx 不存在，跳过 Medium 备份（首次运行）", "WARN")

    # update_models.py 内部会从 Object-Models.xlsx 复制到 Updated.xlsx
    # 所以需要确保 Object-Models.xlsx 存在
    original_baseline = DATA_DIR / "Object-Models.xlsx"
    if not original_baseline.exists():
        shutil.copy2(BASELINE_FILE, original_baseline)
        log(f"已创建: {original_baseline.name}（从 {BASELINE_FILE.name} 复制，供 update_models.py 使用）")

    # 同时也直接准备 Updated.xlsx（以防从步骤 3+ 开始时使用）
    shutil.copy2(BASELINE_FILE, UPDATED_FILE)
    log(f"已复制: {BASELINE_FILE.name} → {UPDATED_FILE.name}")

    # 验证
    row_count = len(pd.read_excel(UPDATED_FILE))
    log(f"基线模型数量: {row_count}")
    return True


# ============================================================
# 步骤 10：对比新旧表格（内置逻辑）
# ============================================================

def step_diff_tables():
    """
    对比 Updated.xlsx（本次生产结果）与 Medium.xlsx（上次的结果），
    输出三类模型清单：新增、原有、遗漏。
    """
    import pandas as pd

    if not MEDIUM_FILE.exists():
        log("Medium.xlsx 不存在（可能是首次运行），跳过对比", "WARN")
        return True

    if not UPDATED_FILE.exists():
        log("Updated.xlsx 不存在，无法对比", "ERROR")
        return False

    df_new = pd.read_excel(UPDATED_FILE)
    df_medium = pd.read_excel(MEDIUM_FILE)

    name_col = "模型名称"
    if name_col not in df_new.columns or name_col not in df_medium.columns:
        log(f"表格中缺少'{name_col}'列，无法对比", "ERROR")
        return False

    new_names = set(df_new[name_col].dropna().astype(str).str.strip())
    medium_names = set(df_medium[name_col].dropna().astype(str).str.strip())

    added = sorted(new_names - medium_names)
    kept = sorted(new_names & medium_names)
    missing = sorted(medium_names - new_names)

    log(f"对比结果：Updated={len(new_names)} vs Medium={len(medium_names)}")
    log(f"  📈 新增模型: {len(added)}")
    log(f"  📋 原有模型: {len(kept)}")
    log(f"  ⚠️  遗漏模型: {len(missing)}")

    if added:
        log(f"  新增列表: {', '.join(added[:20])}{'...' if len(added) > 20 else ''}")
    if missing:
        log(f"  ⚠️ 遗漏列表: {', '.join(missing)}", "WARN")

    # 将对比结果写入文件供验收报告使用
    diff_report_path = REPORT_DIR / "diff_result.md"
    with open(diff_report_path, "w", encoding="utf-8") as f:
        f.write(f"# 新旧表格对比结果\n\n")
        f.write(f"> 对比时间：{TIMESTAMP}\n\n")
        f.write(f"| 类别 | 数量 |\n|------|------|\n")
        f.write(f"| Updated 总数 | {len(new_names)} |\n")
        f.write(f"| Medium 总数 | {len(medium_names)} |\n")
        f.write(f"| 📈 新增 | {len(added)} |\n")
        f.write(f"| 📋 原有 | {len(kept)} |\n")
        f.write(f"| ⚠️ 遗漏 | {len(missing)} |\n\n")

        if added:
            f.write(f"## 📈 新增模型（{len(added)}）\n\n")
            for name in added:
                f.write(f"- {name}\n")
            f.write("\n")

        if missing:
            f.write(f"## ⚠️ 遗漏模型（{len(missing)}）\n\n")
            f.write("> 以下模型在 Medium 中存在但在 Updated 中消失了，请检查是否为误删。\n\n")
            for name in missing:
                f.write(f"- {name}\n")
            f.write("\n")

        f.write(f"## 📋 原有模型（{len(kept)}）\n\n")
        f.write(f"共 {len(kept)} 个模型保持不变（列表省略）。\n")

    log(f"对比报告已写入: {diff_report_path.name}")
    return True


# ============================================================
# 步骤 11：同步新增模型到 only.xlsx（内置逻辑）
# ============================================================

def step_sync_only():
    """
    将本次新增的模型同步到 Object-Models-Updated - only.xlsx。
    新增模型 = Updated 中有但 Medium 中没有的模型。
    如果 only.xlsx 已存在，则追加（去重）；否则新建。
    """
    import pandas as pd

    if not UPDATED_FILE.exists():
        log("Updated.xlsx 不存在，无法同步", "ERROR")
        return False

    df_updated = pd.read_excel(UPDATED_FILE)
    name_col = "模型名称"

    if name_col not in df_updated.columns:
        log(f"表格中缺少'{name_col}'列", "ERROR")
        return False

    # 确定新增模型
    if MEDIUM_FILE.exists():
        df_medium = pd.read_excel(MEDIUM_FILE)
        medium_names = set(df_medium[name_col].dropna().astype(str).str.strip())
        df_added = df_updated[
            ~df_updated[name_col].astype(str).str.strip().isin(medium_names)
        ].copy()
    else:
        # 首次运行，用"是否新增"列判断
        new_col = "是否新增"
        if new_col in df_updated.columns:
            df_added = df_updated[
                df_updated[new_col].astype(str).str.strip().str.lower() == "new"
            ].copy()
        else:
            log("无法确定新增模型（无 Medium 文件也无'是否新增'列）", "WARN")
            return True

    if df_added.empty:
        log("本次无新增模型")
        return True

    # 如果 only.xlsx 已存在，追加并去重
    if ONLY_FILE.exists():
        df_existing = pd.read_excel(ONLY_FILE)
        existing_names = set(df_existing[name_col].dropna().astype(str).str.strip())
        df_truly_new = df_added[
            ~df_added[name_col].astype(str).str.strip().isin(existing_names)
        ]
        if df_truly_new.empty:
            log(f"新增模型已全部存在于 only.xlsx 中，无需追加")
            return True
        df_result = pd.concat([df_existing, df_truly_new], ignore_index=True)
        log(f"追加 {len(df_truly_new)} 个新模型到 only.xlsx（原有 {len(df_existing)}，现有 {len(df_result)}）")
    else:
        df_result = df_added
        log(f"创建 only.xlsx，写入 {len(df_result)} 个新增模型")

    df_result.to_excel(ONLY_FILE, index=False)
    log(f"已同步到: {ONLY_FILE.name}")
    return True


# ============================================================
# 步骤 12：生成验收报告（内置逻辑）
# ============================================================

def step_generate_acceptance_report():
    """
    汇总本次更新的所有结果，生成 E2E-Test-Report.md 和更新 Update-Log.md。
    """
    import pandas as pd

    if not UPDATED_FILE.exists():
        log("Updated.xlsx 不存在，无法生成验收报告", "ERROR")
        return False

    df_updated = pd.read_excel(UPDATED_FILE)
    total_count = len(df_updated)

    # 读取 Medium 数据（如果存在）
    medium_count = 0
    added_count = 0
    missing_count = 0
    if MEDIUM_FILE.exists():
        df_medium = pd.read_excel(MEDIUM_FILE)
        medium_count = len(df_medium)
        name_col = "模型名称"
        if name_col in df_updated.columns and name_col in df_medium.columns:
            new_names = set(df_updated[name_col].dropna().astype(str).str.strip())
            medium_names = set(df_medium[name_col].dropna().astype(str).str.strip())
            added_count = len(new_names - medium_names)
            missing_count = len(medium_names - new_names)

    # 读取对比报告（如果存在）
    diff_report_path = REPORT_DIR / "diff_result.md"
    diff_content = ""
    if diff_report_path.exists():
        with open(diff_report_path, "r", encoding="utf-8") as f:
            diff_content = f.read()

    # 计算字段覆盖率
    coverage = {}
    for col in df_updated.columns:
        non_empty = df_updated[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
        coverage[col] = f"{len(non_empty)}/{total_count} ({100*len(non_empty)//total_count}%)"

    # 生成 E2E-Test-Report.md
    with open(TEST_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# 端到端测试报告\n\n")
        f.write(f"> **测试时间**：{TIMESTAMP}\n")
        f.write(f"> **测试环境**：Windows 11 + PowerShell + Python {sys.version.split()[0]}\n")
        f.write(f"> **测试命令**：`python main.py`（完整流水线）\n\n")
        f.write(f"---\n\n")

        f.write(f"## 测试概览\n\n")
        f.write(f"| 指标 | 数值 |\n|------|------|\n")
        f.write(f"| 更新前模型数（Medium） | {medium_count} |\n")
        f.write(f"| 更新后模型数（Updated） | {total_count} |\n")
        f.write(f"| 📈 新增模型 | {added_count} |\n")
        f.write(f"| ⚠️ 遗漏模型 | {missing_count} |\n")
        f.write(f"| 表格总列数 | {len(df_updated.columns)} |\n\n")

        if missing_count > 0:
            f.write(f"### ⚠️ 遗漏警告\n\n")
            f.write(f"有 {missing_count} 个模型在 Medium 中存在但在 Updated 中消失了，请检查 `diff_result.md` 中的详细列表。\n\n")

        f.write(f"## 字段覆盖率\n\n")
        f.write(f"| 字段 | 覆盖率 |\n|------|--------|\n")
        for col, cov in coverage.items():
            f.write(f"| {col} | {cov} |\n")
        f.write(f"\n")

        f.write(f"## 产出文件清单\n\n")
        f.write(f"```\naction/\n")
        f.write(f"├── data/\n")
        f.write(f"│   ├── Object-Models-Updated.xlsx        ← 最终表格（{total_count}行）\n")
        f.write(f"│   ├── Object-Models-Medium.xlsx          ← 更新前备份（{medium_count}行）\n")
        if ONLY_FILE.exists():
            only_count = len(pd.read_excel(ONLY_FILE))
            f.write(f"│   └── Object-Models-Updated - only.xlsx ← 仅新增模型（{only_count}行）\n")
        f.write(f"├── Report/\n")
        f.write(f"│   ├── diff_result.md                     ← 新旧对比报告\n")
        f.write(f"│   ├── E2E-Test-Report.md                 ← 本文件\n")
        f.write(f"│   ├── Update-Log.md                      ← 更新日志\n")
        report_files = sorted(REPORT_DIR.glob("update_report_*.md"), reverse=True)
        if report_files:
            f.write(f"│   ├── {report_files[0].name}            ← 更新报告\n")
        f.write(f"│   └── daily_report_*.md                  ← 日报\n")
        f.write(f"```\n")

    log(f"测试报告已生成: {TEST_REPORT_FILE.name}")

    # 更新 Update-Log.md（在文件顶部的分隔线后追加新条目）
    new_entry = (
        f"\n## {TODAY} 更新\n\n"
        f"### 更新概览\n\n"
        f"| 指标 | 数值 |\n|---|---|\n"
        f"| 更新前模型数 | {medium_count} |\n"
        f"| 更新后模型数 | **{total_count}** |\n"
        f"| 新增模型数 | **{added_count}** |\n"
        f"| 遗漏模型数 | {missing_count} |\n"
        f"| 表格总列数 | {len(df_updated.columns)} |\n\n"
        f"### 相关文件\n\n"
        f"- 测试报告：`E2E-Test-Report.md`\n"
        f"- 对比报告：`diff_result.md`\n"
    )
    if report_files:
        new_entry += f"- 详细报告：`Report/{report_files[0].name}`\n"
    new_entry += f"\n---\n"

    if UPDATE_LOG_FILE.exists():
        with open(UPDATE_LOG_FILE, "r", encoding="utf-8") as f:
            existing_content = f.read()
        # 在第一个 "---" 之后插入新条目
        marker = "\n---\n"
        first_marker_pos = existing_content.find(marker)
        if first_marker_pos != -1:
            insert_pos = first_marker_pos + len(marker)
            updated_content = existing_content[:insert_pos] + new_entry + existing_content[insert_pos:]
        else:
            updated_content = existing_content + "\n" + new_entry
        with open(UPDATE_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(updated_content)
    else:
        with open(UPDATE_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 模型追踪更新日志\n\n")
            f.write(f"> 每次对 `Object-Models-Updated.xlsx` 进行更新后，在此记录更新情况。\n\n")
            f.write(f"---\n{new_entry}")

    log(f"更新日志已更新: {UPDATE_LOG_FILE.name}")
    return True


# ============================================================
# 主流程
# ============================================================


# ------------------------------------------------------------
# 工具函数：判断文件是否今天修改
# ------------------------------------------------------------

def _file_modified_today(filepath):
    """判断文件是否在今天被修改过。"""
    if not filepath.exists():
        return False
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    return mtime.date() == date.today()


# ------------------------------------------------------------
# Checkpoint：检查每步产出文件是否已存在
# ------------------------------------------------------------

def check_checkpoint(step_num, since_int=None, until_int=None):
    """检查第 step_num 步的产出文件是否已在今天生成过。

    返回 (has_cache: bool, summary_lines: list[str])。
    """
    import pandas as pd
    lines = []
    has_cache = False

    if step_num == 1:
        medium_ok = _file_modified_today(MEDIUM_FILE)
        updated_ok = _file_modified_today(UPDATED_FILE)
        if medium_ok and updated_ok:
            has_cache = True
            lines.append(f"Medium.xlsx 今天已更新")
            lines.append(f"Updated.xlsx 今天已更新")

    elif step_num == 2:
        if _file_modified_today(UPDATED_FILE) and MEDIUM_FILE.exists():
            updated_rows = len(pd.read_excel(UPDATED_FILE, engine="openpyxl"))
            medium_rows = len(pd.read_excel(MEDIUM_FILE, engine="openpyxl"))
            if updated_rows > medium_rows:
                has_cache = True
                lines.append(f"Updated.xlsx（{updated_rows} 行）> Medium.xlsx（{medium_rows} 行）")

    elif step_num == 3:
        test_dir = ACTION_DIR / "Test"
        if test_dir.exists():
            check_files = list(test_dir.glob("DataForCheck*.md"))
            today_files = [f for f in check_files if _file_modified_today(f)]
            if today_files:
                has_cache = True
                for f in today_files:
                    lines.append(f"今天已生成: {f.name}")

    elif step_num == 4:
        report_files = list(REPORT_DIR.glob("update_report_*.md"))
        today_reports = [f for f in report_files if _file_modified_today(f)]
        if today_reports:
            has_cache = True
            for f in today_reports:
                lines.append(f"今天已生成: {f.name}")

    elif step_num == 5:
        arena_formatted = ACTION_DIR / "Crawl" / "Arena_x" / "formatted_leaderboards.md"
        if _file_modified_today(arena_formatted):
            has_cache = True
            lines.append(f"今天已生成: {arena_formatted.name}")

    elif step_num == 6:
        diff_result = REPORT_DIR / "diff_result.md"
        if _file_modified_today(diff_result):
            has_cache = True
            lines.append(f"今天已生成: {diff_result.name}")

    elif step_num == 7:
        if _file_modified_today(ONLY_FILE):
            has_cache = True
            lines.append(f"今天已生成: {ONLY_FILE.name}")

    elif step_num == 8:
        if _file_modified_today(TEST_REPORT_FILE):
            has_cache = True
            lines.append(f"今天已生成: {TEST_REPORT_FILE.name}")

    elif step_num == 9:
        daily_reports = list(REPORT_DIR.glob("daily_report_*.md"))
        today_dailies = [f for f in daily_reports if _file_modified_today(f)]
        if today_dailies:
            has_cache = True
            for f in today_dailies:
                lines.append(f"今天已生成: {f.name}")

    return has_cache, lines


# ============================================================
# 步骤校验（每步执行完后验证产出）
# ============================================================

def verify_step(step_num, since_int=None, until_int=None):
    """验证每步执行后的产出是否符合预期。返回 (passed, messages) 元组。"""
    import pandas as pd
    messages = []
    passed = True

    if step_num == 1:
        # 校验：Updated.xlsx 存在且行数>0，Medium.xlsx 存在
        if UPDATED_FILE.exists():
            row_count = len(pd.read_excel(UPDATED_FILE, engine="openpyxl"))
            messages.append(f"✅ Updated.xlsx 存在（{row_count} 行）")
            if row_count == 0:
                messages.append("❌ Updated.xlsx 行数为 0")
                passed = False
        else:
            messages.append("❌ Updated.xlsx 不存在")
            passed = False
        if MEDIUM_FILE.exists():
            medium_count = len(pd.read_excel(MEDIUM_FILE, engine="openpyxl"))
            messages.append(f"✅ Medium.xlsx 存在（{medium_count} 行）")
        else:
            messages.append("⚠️ Medium.xlsx 不存在（首次运行属正常）")

    elif step_num == 2:
        # 校验：Updated.xlsx 行数、Extract/articles/ 文件数、TXCrawl_result.xlsx
        articles_dir = ACTION_DIR / "Extract" / "articles"
        txcrawl_result = ACTION_DIR / "Extract" / "TXCrawl_result.xlsx"
        llmstats_json = ACTION_DIR / "Crawl" / "Arena_x" / "llmstats_models.json"
        tx_dir = ACTION_DIR / "TXresearch"

        if UPDATED_FILE.exists():
            row_count = len(pd.read_excel(UPDATED_FILE, engine="openpyxl"))
            messages.append(f"✅ Updated.xlsx 存在（{row_count} 行）")
        else:
            messages.append("❌ Updated.xlsx 不存在")
            passed = False

        # llmstats 校验
        if llmstats_json.exists():
            import json
            with open(llmstats_json, "r", encoding="utf-8") as f:
                llm_data = json.load(f)
            messages.append(f"✅ llmstats_models.json 存在（{len(llm_data)} 条）")
        else:
            messages.append("⚠️ llmstats_models.json 不存在（llmstats 可能未抓取成功）")

        # 腾讯研究院校验
        if articles_dir.exists():
            txt_files = list(articles_dir.glob("*.txt"))
            messages.append(f"✅ Extract/articles/ 有 {len(txt_files)} 篇文章")
            if since_int and until_int:
                tag = f"{since_int}-{until_int}"
                json_cache = tx_dir / f"articles_{tag}.json"
                if json_cache.exists():
                    messages.append(f"✅ 腾讯研究院 JSON 缓存存在: articles_{tag}.json")
                else:
                    messages.append(f"⚠️ 腾讯研究院 JSON 缓存不存在: articles_{tag}.json")
                    messages.append(f"   💡 可能原因：Selenium/Chrome/ChromeDriver 未安装")
                    messages.append(f"   💡 手动运行：cd Crawl\\TXresearch && python crawl_sohu.py --since {since_int} --until {until_int}")
        else:
            messages.append("⚠️ Extract/articles/ 目录不存在")

        # TXCrawl_result.xlsx 校验
        if txcrawl_result.exists():
            tx_df = pd.read_excel(txcrawl_result, engine="openpyxl")
            messages.append(f"✅ TXCrawl_result.xlsx 存在（{len(tx_df)} 行）")
            # 检查是否有模型提取结果
            model_col = "文章提及的新兴模型"
            if model_col in tx_df.columns:
                filled = tx_df[model_col].dropna().astype(str)
                filled = filled[filled.str.len() > 0]
                if len(filled) == 0:
                    messages.append("⚠️ TXCrawl_result.xlsx 中[文章提及的新兴模型]列为空（需人机协作完成 L2 提取）")
                else:
                    messages.append(f"✅ TXCrawl_result.xlsx 中有 {len(filled)}/{len(tx_df)} 篇已提取模型信息")
        else:
            messages.append("⚠️ TXCrawl_result.xlsx 不存在")

    elif step_num == 3:
        # 校验：check_result.py 的输出（通过文件存在性判断）
        check_files = list((ACTION_DIR / "Test").glob("DataForCheck*.md"))
        if check_files:
            messages.append(f"✅ 数据检查报告存在（{len(check_files)} 个文件）")
        else:
            messages.append("⚠️ 未找到数据检查报告文件")

    elif step_num == 4:
        # 校验：Report/ 下有 update_report_*.md
        report_files = sorted(REPORT_DIR.glob("update_report_*.md"), reverse=True)
        if report_files:
            messages.append(f"✅ 更新报告存在: {report_files[0].name}")
        else:
            messages.append("⚠️ 未找到更新报告（Report/update_report_*.md）")

    elif step_num == 5:
        # 校验：format_cases.py 的输出
        formatted = ACTION_DIR / "Crawl" / "Arena_x" / "formatted_leaderboards.md"
        if formatted.exists():
            messages.append(f"✅ Case 文件已整理: {formatted.name}")
        else:
            messages.append("⚠️ formatted_leaderboards.md 不存在（format_cases.py 可能未执行或脚本不存在）")

    elif step_num == 6:
        # 校验：diff_result.md 存在
        diff_path = REPORT_DIR / "diff_result.md"
        if diff_path.exists():
            messages.append(f"✅ 对比报告存在: {diff_path.name}")
            with open(diff_path, "r", encoding="utf-8") as f:
                diff_content = f.read()
            if "遗漏" in diff_content:
                # 提取遗漏数量
                import re
                match = re.search(r"⚠️ 遗漏 \| (\d+)", diff_content)
                if match and int(match.group(1)) > 0:
                    messages.append(f"⚠️ 有 {match.group(1)} 个遗漏模型，请检查")
        else:
            messages.append("⚠️ diff_result.md 不存在")

    elif step_num == 7:
        # 校验：only.xlsx 存在或无新增
        if ONLY_FILE.exists():
            only_count = len(pd.read_excel(ONLY_FILE, engine="openpyxl"))
            messages.append(f"✅ only.xlsx 存在（{only_count} 个新增模型）")
        else:
            messages.append("ℹ️ only.xlsx 不存在（可能无新增模型）")

    elif step_num == 8:
        # 校验：E2E-Test-Report.md + Update-Log.md 存在
        if TEST_REPORT_FILE.exists():
            messages.append(f"✅ 验收报告存在: {TEST_REPORT_FILE.name}")
        else:
            messages.append("❌ E2E-Test-Report.md 不存在")
            passed = False
        if UPDATE_LOG_FILE.exists():
            messages.append(f"✅ 更新日志存在: {UPDATE_LOG_FILE.name}")
        else:
            messages.append("❌ Update-Log.md 不存在")
            passed = False

        # 数据质量校验
        if UPDATED_FILE.exists():
            df = pd.read_excel(UPDATED_FILE, engine="openpyxl")
            total = len(df)
            for col_name in ["公司", "备注", "模型发布时间"]:
                if col_name in df.columns:
                    filled = df[col_name].dropna().astype(str)
                    filled = filled[(filled.str.len() > 0) & (filled != "nan")]
                    pct = len(filled) / total * 100 if total > 0 else 0
                    icon = "✅" if pct == 100 else "⚠️"
                    messages.append(f"{icon} {col_name}: {len(filled)}/{total} ({pct:.0f}%)")

    elif step_num == 9:
        # 校验：日报 MD 文件存在
        daily_reports = sorted(REPORT_DIR.glob("daily_report_*.md"), reverse=True)
        if daily_reports:
            messages.append(f"✅ 日报存在: {daily_reports[0].name}")
        else:
            messages.append("⚠️ 未找到日报文件")

    return passed, messages

def run_pipeline(start_step=1, dry_run=False, since_int=None, until_int=None, source="all", push=False, force=False):
    """运行端到端流水线（v2 自动化版）"""
    from datetime import timedelta as _td

    # 计算时间窗口
    _today = datetime.now()
    if until_int is None:
        until_int = int(_today.strftime("%Y%m%d"))
    if since_int is None:
        since_int = int((_today - _td(days=7)).strftime("%Y%m%d"))

    print(f"\n{'#'*60}")
    print(f"  AI 模型追踪 —— 端到端更新流水线 (v2)")
    print(f"  日期: {TODAY}")
    print(f"  时间窗口: {since_int} ~ {until_int}")
    print(f"  数据源: {source}")
    print(f"  起始步骤: {start_step}")
    print(f"  模式: {'预览' if dry_run else '执行'}")
    print(f"{'#'*60}")

    # 前置检查
    issues = check_prerequisites() if start_step == 1 else check_midway_prerequisites()
    if issues:
        log("前置条件检查失败:", "ERROR")
        for issue in issues:
            log(f"  - {issue}", "ERROR")
        return False

    results = {}

    for step in STEPS:
        step_num = step["number"]
        step_name = step["name"]

        # 跳过已完成的步骤
        if step_num < start_step:
            print(f"\n  ⏭️ 跳过步骤 {step_num}: {step_name}")
            results[step_num] = "SKIPPED"
            continue

        log_progress(step_num, len(STEPS), step_name)
        log(step["description"], "STEP")

        # Checkpoint：检查是否已有今天的产出
        if not force and not dry_run:
            has_cache, cache_summary = check_checkpoint(step_num, since_int, until_int)
            if has_cache:
                log(f"已有今天的产出（使用 --force 可强制重新执行）", "SKIP")
                for line in cache_summary:
                    log(f"  {line}")
                results[step_num] = "CACHED"
                continue

        if dry_run:
            if step_num == 2:
                log(f"将运行: auto_collect.py --since {since_int} --until {until_int} --source {source}", "STEP")
                log(f"将运行: extract_models_llm.py --since {since_int} --until {until_int} --write-excel（LLM 提取腾讯研究院模型）", "STEP")
            elif step["script"]:
                log(f"将运行: {step['script']}", "STEP")
            else:
                log("将执行内置逻辑", "STEP")
            results[step_num] = "DRY_RUN"
            continue

        # 执行步骤
        success = False
        if step_num == 1:
            success = step_prepare_baseline()
        elif step_num == 2:
            # 自动化数据采集（调用 auto_collect.py，心跳探测模式）
            auto_collect_script = ACTION_DIR / "auto_collect.py"
            auto_collect_args = [
                sys.executable, "-X", "utf8", str(auto_collect_script),
                "--since", str(since_int),
                "--until", str(until_int),
                "--source", source,
            ]
            log(f"运行: auto_collect.py --since {since_int} --until {until_int} --source {source}", "STEP")
            returncode, _ = run_subprocess_heartbeat(
                auto_collect_args,
                cwd=str(ACTION_DIR),
                timeout_minutes=30,
                label="auto_collect.py",
            )
            if returncode != 0:
                log(f"auto_collect.py 失败（退出码 {returncode}）", "ERROR")
                success = False
            else:
                success = True

            # 步骤 2.5：LLM 自动提取腾讯研究院文章中的模型信息并回写主表格
            if success:
                extract_llm_script = ACTION_DIR / "Extract" / "extract_models_llm.py"
                llm_json_cache = ACTION_DIR / "Extract" / "extracted_models_llm.json"
                if extract_llm_script.exists():
                    if not force and _file_modified_today(llm_json_cache):
                        log("LLM 提取结果今天已生成（使用 --force 可强制重新执行）", "SKIP")
                        import json as _json
                        with open(llm_json_cache, "r", encoding="utf-8") as _f:
                            _cached = _json.load(_f)
                        log(f"  缓存中有 {len(_cached)} 条提取结果")
                    else:
                        log("运行: extract_models_llm.py（LLM 自动提取腾讯研究院模型 → 回写主表格）", "STEP")
                        # 先列出文章数量（快速操作，用 capture 模式）
                        list_args = [
                            sys.executable, "-X", "utf8", str(extract_llm_script),
                            "--since", str(since_int),
                            "--until", str(until_int),
                            "--list",
                        ]
                        list_rc, list_stdout = run_subprocess_heartbeat(
                            list_args,
                            cwd=str(extract_llm_script.parent),
                            timeout_minutes=2,
                            label="extract_models_llm --list",
                            capture=True,
                        )
                        # 从 --list 输出中解析文章数量
                        import re as _re
                        article_indices = _re.findall(r'\[(\d+)\]', list_stdout or "")
                        article_count = max((int(i) for i in article_indices), default=0)

                        if article_count == 0:
                            log("无符合条件的文章，跳过 LLM 提取", "INFO")
                        else:
                            log(f"共 {article_count} 篇文章，逐篇提取中...", "INFO")
                            llm_failed = 0
                            for article_idx in range(1, article_count + 1):
                                idx_args = [
                                    sys.executable, "-X", "utf8", str(extract_llm_script),
                                    "--since", str(since_int),
                                    "--until", str(until_int),
                                    "--index", str(article_idx),
                                    "--write-excel",
                                ]
                                idx_rc, _ = run_subprocess_heartbeat(
                                    idx_args,
                                    cwd=str(extract_llm_script.parent),
                                    timeout_minutes=10,
                                    label=f"extract_models_llm [{article_idx}/{article_count}]",
                                )
                                if idx_rc != 0:
                                    llm_failed += 1
                            if llm_failed > 0:
                                log(f"LLM 提取完成（{llm_failed}/{article_count} 篇失败，不影响流水线）", "WARN")
                            else:
                                log(f"LLM 模型提取完成（{article_count} 篇全部成功）", "INFO")
                else:
                    log("extract_models_llm.py 不存在，跳过 LLM 提取", "WARN")

            # 步骤 2.7：GPT-5.5 审核（补全 + 质量审核 + 置信度）
            if success:
                review_script = ACTION_DIR / "review_models.py"
                review_report = REPORT_DIR / "review_report.md"
                if review_script.exists():
                    if not force and _file_modified_today(review_report):
                        log("GPT-5.5 审核报告今天已生成（使用 --force 可强制重新执行）", "SKIP")
                    else:
                        log("运行: review_models.py（GPT-5.5 审核 + 补全 + 置信度）", "STEP")
                        review_rc, _ = run_subprocess_heartbeat(
                            [sys.executable, "-X", "utf8", str(review_script)],
                            cwd=str(ACTION_DIR),
                            timeout_minutes=10,
                            label="review_models.py",
                        )
                        if review_rc != 0:
                            log("review_models.py 失败（不影响流水线继续）", "WARN")
                        else:
                            log("GPT-5.5 审核完成", "INFO")
                else:
                    log("review_models.py 不存在，跳过 GPT-5.5 审核", "WARN")
        elif step_num == 6:
            success = step_diff_tables()
        elif step_num == 7:
            success = step_sync_only()
        elif step_num == 8:
            success = step_generate_acceptance_report()
        elif step_num == 9:
            # 钉钉推送日报（需要 --push 参数启用，或设置了 DINGTALK_WEBHOOK）
            push_script = ACTION_DIR / "push_dingtalk.py"
            has_webhook = bool(os.environ.get("DINGTALK_WEBHOOK", ""))
            if not push and not has_webhook:
                log("跳过钉钉推送（未指定 --push 且未设置 DINGTALK_WEBHOOK）", "SKIP")
                success = True
            elif push_script.exists():
                push_args = [
                    sys.executable, "-X", "utf8", str(push_script),
                    "--since", str(since_int),
                    "--until", str(until_int),
                    "--save-md",
                ]
                log(f"运行: push_dingtalk.py --since {since_int} --until {until_int}", "STEP")
                push_rc, _ = run_subprocess_heartbeat(
                    push_args,
                    cwd=str(ACTION_DIR),
                    timeout_minutes=5,
                    label="push_dingtalk.py",
                )
                success = push_rc == 0
                if not success:
                    log("push_dingtalk.py 失败", "ERROR")
            else:
                log(f"推送脚本不存在: {push_script}", "ERROR")
                success = False
        elif step["script"]:
            success = run_script(step["script"])
        else:
            log("无执行逻辑", "WARN")
            success = True

        results[step_num] = "SUCCESS" if success else "FAILED"

        # ── 步骤校验 ──
        if success and not dry_run:
            verify_passed, verify_messages = verify_step(step_num, since_int, until_int)
            if verify_messages:
                print(f"  {'─'*40}")
                print(f"  📋 步骤 {step_num} 校验结果:")
                for msg in verify_messages:
                    print(f"     {msg}")
            if not verify_passed:
                log(f"步骤 {step_num} 校验未通过（产出不符合预期）", "WARN")
                log("流水线继续执行，但请注意校验警告", "WARN")

        if not success:
            log(f"步骤 {step_num} 失败，流水线中断", "ERROR")
            log("提示：修复问题后，可用 --step 参数从失败步骤重新开始", "WARN")
            break

    # 打印汇总
    print(f"\n{'='*60}")
    print(f"  流水线执行汇总")
    print(f"{'='*60}")
    for step in STEPS:
        step_num = step["number"]
        status = results.get(step_num, "NOT_RUN")
        icon = {
            "SUCCESS": "✅",
            "FAILED": "❌",
            "SKIPPED": "⏭️",
            "DRY_RUN": "👁️",
            "CACHED": "📦",
            "NOT_RUN": "⬜",
        }.get(status, "❓")
        print(f"  {icon} 步骤 {step_num}: {step['name']} — {status}")

    # 最终产出
    all_success = all(
        v in ("SUCCESS", "SKIPPED", "DRY_RUN", "CACHED") for v in results.values()
    )
    if all_success and not dry_run:
        print(f"\n{'='*60}")
        print(f"  🎉 流水线执行完成！ {progress_bar(len(STEPS), len(STEPS))}")
        print(f"{'='*60}")

        # 最终数据质量汇总
        try:
            import pandas as pd
            if UPDATED_FILE.exists():
                df = pd.read_excel(UPDATED_FILE, engine="openpyxl")
                total = len(df)
                print(f"\n  📊 数据质量汇总（{total} 个模型）:")
                for col_name in ["公司", "备注", "模型发布时间"]:
                    if col_name in df.columns:
                        filled = df[col_name].dropna().astype(str)
                        filled = filled[(filled.str.len() > 0) & (filled != "nan")]
                        pct = len(filled) / total * 100 if total > 0 else 0
                        icon = "✅" if pct == 100 else ("⚠️" if pct >= 80 else "❌")
                        bar = progress_bar(len(filled), total, width=20)
                        print(f"     {icon} {col_name}: {bar}")
        except Exception:
            pass
        if UPDATED_FILE.exists():
            print(f"  📊 更新表格: {UPDATED_FILE}")
        if MEDIUM_FILE.exists():
            print(f"  📦 更新前备份: {MEDIUM_FILE}")
        if ONLY_FILE.exists():
            print(f"  🆕 仅新增模型: {ONLY_FILE}")
        diff_path = REPORT_DIR / "diff_result.md"
        if diff_path.exists():
            print(f"  🔍 对比报告: {diff_path}")
        if TEST_REPORT_FILE.exists():
            print(f"  🧪 测试报告: {TEST_REPORT_FILE}")
        if UPDATE_LOG_FILE.exists():
            print(f"  📋 更新日志: {UPDATE_LOG_FILE}")
        report_dir = ACTION_DIR / "Report"
        report_files = sorted(report_dir.glob("update_report_*.md"), reverse=True)
        if report_files:
            print(f"  📝 详细报告: {report_files[0]}")
        formatted_path = ACTION_DIR / "Crawl" / "Arena_x" / "formatted_leaderboards.md"
        if formatted_path.exists():
            print(f"  📋 排行榜汇总: {formatted_path}")

    return all_success


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI 模型追踪 —— 端到端一键更新流水线 (v2 自动化版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py --since 20260417 --until 20260423    指定时间段
  python main.py --since 20260417                     until 默认今天
  python main.py                                      默认最近 7 天
  python main.py --step 3                             从第3步开始
  python main.py --dry-run                            预览流程
  python main.py --source llmstats                    只跑 llmstats
  python main.py --push                               含钉钉推送
        """,
    )
    parser.add_argument(
        "--step",
        type=int,
        default=1,
        choices=range(1, len(STEPS) + 1),
        help="从第几步开始执行（默认从1开始）",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="起始日期（YYYYMMDD 格式，如 20260417），默认 7 天前",
    )
    parser.add_argument(
        "--until", type=str, default=None,
        help="截止日期（YYYYMMDD 格式，如 20260423），默认今天",
    )
    parser.add_argument(
        "--source", type=str, default="all",
        choices=["all", "llmstats", "txresearch"],
        help="数据源（默认 all = llmstats + 腾讯研究院）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：只显示将要执行的步骤，不实际运行",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="启用钉钉推送（步骤9），需配置 DINGTALK_WEBHOOK 环境变量或 .env",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新执行所有步骤，忽略 checkpoint 缓存",
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="将所有输出同时写入指定日志文件（适用于后台运行时轮询监控）",
    )

    args = parser.parse_args()

    # 如果指定了 --log，设置 tee 输出（同时写终端 + 日志文件）
    if args.log:
        import io

        class TeeWriter:
            """同时写入多个流的包装器。"""
            def __init__(self, *streams):
                self.streams = streams
            def write(self, data):
                for s in self.streams:
                    s.write(data)
                    s.flush()
            def flush(self):
                for s in self.streams:
                    s.flush()

        log_file = open(args.log, "w", encoding="utf-8")
        sys.stdout = TeeWriter(sys.stdout, log_file)
        sys.stderr = TeeWriter(sys.stderr, log_file)

    since_int = int(args.since) if args.since else None
    until_int = int(args.until) if args.until else None

    success = run_pipeline(
        start_step=args.step,
        dry_run=args.dry_run,
        since_int=since_int,
        until_int=until_int,
        source=args.source,
        push=args.push,
        force=args.force,
    )

    if args.log:
        log_file.close()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Windows GBK 终端兼容：强制 UTF-8 输出
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
