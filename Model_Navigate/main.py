"""
AI 模型追踪 —— 端到端一键更新流水线（v3 精简版）

使用方式：
    python main.py --since 20260417 --until 20260423    # 指定时间段
    python main.py --since 20260417                     # until 默认今天
    python main.py                                      # 默认最近 7 天
    python main.py --step 3                             # 从第3步开始
    python main.py --dry-run                            # 预览流程
    python main.py --source llmstats                    # 只跑 llmstats 数据源

流水线步骤（v3, 8步）：
    === 数据采集与清洗 ===
    1. 数据采集：llmstats + 腾讯研究院 + HuggingFace + 平台目录 + LM Arena → 采集原始数据
    2. 增量去重：与总表去重 + 时间窗口过滤，提取本次新增模型
    === 质量保障 ===
    3. LLM 审核：GPT-5.5 审核（名称规范 + 发布时间/官网/备注补全 + 重要性评级）
    4. 数据校验：Web Search 校验新增模型的发布时间/官网/备注
    5. 交叉巡检：LLM 联网搜索该时段新模型，与已有数据交叉比对，补漏遗漏模型
    === 归档与推送 ===
    6. 合并归档：增量写入总表 + 归档到 increments/ + 备份总表
    7. 钉钉推送：生成日报并推送到钉钉群（需 --push 参数）
    8. 运行记录：写入 run_log.csv + 生成 Trace 记录

前置条件：
    - 首次运行时自动创建空总表（冷启动）
    - 请先关闭 Excel 中打开的相关文件

数据架构（v3）：
    - 总表 Object-Models.xlsx：唯一真相源
    - increments/：每次运行的增量日志
    - Backup/：写入总表前的快照备份
    - run_log.csv：轻量级运行记录
"""
import subprocess
import sys
import os
import argparse
import shutil
import re
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
TRACE_DIR = ACTION_DIR / "Trace"

# ── v3 数据架构（精简为：总表 + 增量日志 + 备份 + 运行记录）──
MASTER_FILE = DATA_DIR / "Object-Models.xlsx"          # 总表：唯一真相源
INCREMENT_DIR = DATA_DIR / "increments"                 # 增量日志：每次触发归档
BACKUP_DIR = DATA_DIR / "Backup"                        # 备份：写入总表前快照
RUN_LOG_FILE = DATA_DIR / "run_log.csv"                 # 运行记录：轻量级追溯

# ── 兼容旧路径 ──
UPDATED_FILE = DATA_DIR / "Object-Models-Updated.xlsx"  # Step 1 采集输出 → Step 2 去重后成为增量
TEST_REPORT_FILE = REPORT_DIR / "E2E-Test-Report.md"
UPDATE_LOG_FILE = REPORT_DIR / "Update-Log.md"

TODAY = date.today().isoformat()
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_ID = datetime.now().strftime("%Y%m%d_run%H%M")

# ============================================================
# 步骤定义（v3 精简流水线：6 步）
# ============================================================

STEPS = [
    {
        "number": 1,
        "name": "数据采集",
        "description": "llmstats + 腾讯研究院 + HuggingFace + 平台目录 + LM Arena → 采集原始数据",
        "script": ACTION_DIR / "auto_collect.py",
    },
    {
        "number": 2,
        "name": "增量去重",
        "description": "与总表去重 + 时间窗口过滤，提取本次新增模型",
        "script": None,
    },
    {
        "number": 3,
        "name": "LLM 审核",
        "description": "GPT-5.5 审核（名称规范 + 发布时间/官网/备注补全 + 重要性评级）",
        "script": ACTION_DIR / "review_models.py",
    },
    {
        "number": 4,
        "name": "数据校验",
        "description": "Web Search 校验新增模型的发布时间/官网/备注（AI 对话中执行）",
        "script": None,
        "manual": True,  # 标记为需要 AI 对话中人机协作执行的步骤
    },
    {
        "number": 5,
        "name": "交叉巡检",
        "description": "LLM 联网搜索该时段新模型，与已有数据交叉比对，补漏遗漏模型",
        "script": ACTION_DIR / "cross_check.py",
    },
    {
        "number": 6,
        "name": "合并归档",
        "description": "增量写入总表 + 归档到 increments/ + 备份总表",
        "script": None,
    },
    {
        "number": 7,
        "name": "钉钉推送",
        "description": "生成日报并推送到钉钉群（需 --push 参数）",
        "script": ACTION_DIR / "push_dingtalk.py",
    },
    {
        "number": 8,
        "name": "运行记录",
        "description": "写入 run_log.csv + 生成 Trace 记录",
        "script": None,
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


def _create_empty_master():
    """冷启动：创建空总表 Excel（含正确表头）。"""
    import pandas as pd
    from auto_collect import EXCEL_COLUMNS

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    empty_df = pd.DataFrame(columns=EXCEL_COLUMNS)
    empty_df.to_excel(MASTER_FILE, index=False)
    log(f"冷启动：已自动创建空总表 {MASTER_FILE.name}（首次运行）", "WARN")


def check_prerequisites():
    """检查前置条件。总表不存在时自动创建空总表（冷启动）。"""
    issues = []

    if not MASTER_FILE.exists():
        _create_empty_master()

    # 检查 Excel 是否被占用（尝试以写模式打开）
    for filepath in [MASTER_FILE, UPDATED_FILE]:
        if filepath.exists():
            try:
                with open(filepath, "a"):
                    pass
            except PermissionError:
                issues.append(f"文件被占用（请关闭 Excel）: {filepath.name}")

    # 检查关键脚本是否存在
    for step in STEPS:
        if step.get("script") and not step["script"].exists():
            issues.append(f"脚本不存在: {step['script']}")

    return issues


def check_midway_prerequisites():
    """从中间步骤开始时的前置检查。"""
    issues = []

    if not UPDATED_FILE.exists() and not MASTER_FILE.exists():
        issues.append("总表和增量文件均不存在（从中间步骤开始需要先完成前面的步骤）")

    # 检查 Excel 是否被占用
    for filepath in [MASTER_FILE, UPDATED_FILE]:
        if filepath.exists():
            try:
                with open(filepath, "a"):
                    pass
            except PermissionError:
                issues.append(f"文件被占用（请关闭 Excel）: {filepath.name}")

    return issues


# ============================================================
# 验收机制
# ============================================================

def verify_step_output(step_num, since_int, until_int):
    """验收每步执行结果，返回 (passed: bool, messages: list[str])。

    各步骤验收规则（v3 8步）：
      Step 1（采集）: UPDATED_FILE 存在 + 行数>0 + "模型名称"列非空率100% + "公司"列非空率≥80%
      Step 2（去重）: 增量文件存在 + 行数≤采集行数 + 无重复模型名
      Step 3（审核）: UPDATED_FILE 中 importance 列填充率≥50%（如有）
      Step 4（校验）: UPDATED_FILE 中 "模型发布时间" 填充率报告
      Step 5（交叉巡检）: 脚本正常执行即通过（遗漏模型数仅做报告）
      Step 6（合并归档）: MASTER_FILE 行数 ≥ 合并前行数 + 无重复模型名
      Step 7/8（推送/记录）: 直接 pass
    """
    import pandas as pd
    messages = []

    if step_num in (7, 8):
        return True, ["日志/推送类步骤，无需数据验收"]

    if step_num == 1:
        if not UPDATED_FILE.exists():
            return False, ["采集结果文件不存在"]
        df = pd.read_excel(UPDATED_FILE)
        if len(df) == 0:
            return False, ["采集结果为空（0行）"]
        name_col = "模型名称"
        if name_col in df.columns:
            name_fill_rate = df[name_col].notna().mean()
            if name_fill_rate < 1.0:
                messages.append(f"模型名称列非空率 {name_fill_rate:.0%}（要求100%）")
                return False, messages
        else:
            return False, ["缺少'模型名称'列"]
        company_col = "公司"
        if company_col in df.columns:
            company_fill_rate = df[company_col].notna().mean()
            if company_fill_rate < 0.8:
                messages.append(f"公司列非空率 {company_fill_rate:.0%}（要求≥80%）")
                return False, messages
        messages.append(f"采集验收通过: {len(df)}行, 模型名称100%, 公司{df['公司'].notna().mean():.0%}" if "公司" in df.columns else f"采集验收通过: {len(df)}行")
        return True, messages

    elif step_num == 2:
        increment_path = INCREMENT_DIR / f"{RUN_ID}.xlsx"
        empty_marker = INCREMENT_DIR / f"{RUN_ID}_empty.xlsx"
        if empty_marker.exists():
            return True, ["本次无新增模型，去重验收通过"]
        if not increment_path.exists():
            return False, ["增量文件不存在"]
        df_inc = pd.read_excel(increment_path)
        # 行数应≤采集行数
        if UPDATED_FILE.exists():
            df_collected = pd.read_excel(UPDATED_FILE)
            if len(df_inc) > len(df_collected):
                messages.append(f"增量行数({len(df_inc)})超过采集行数({len(df_collected)})")
                return False, messages
        # 无重复模型名
        name_col = "模型名称"
        if name_col in df_inc.columns and not df_inc.empty:
            duplicates = df_inc[name_col].dropna().duplicated().sum()
            if duplicates > 0:
                messages.append(f"增量中存在 {duplicates} 个重复模型名")
                return False, messages
        messages.append(f"去重验收通过: 增量{len(df_inc)}行, 无重复")
        return True, messages

    elif step_num == 3:
        if not UPDATED_FILE.exists():
            return True, ["审核文件不存在，跳过验收"]
        df = pd.read_excel(UPDATED_FILE)
        importance_col = "importance"
        if importance_col in df.columns and len(df) > 0:
            fill_rate = df[importance_col].notna().mean()
            if fill_rate < 0.5:
                messages.append(f"importance列填充率 {fill_rate:.0%}（要求≥50%）")
                return False, messages
            messages.append(f"审核验收通过: importance填充率{fill_rate:.0%}")
        else:
            messages.append("无importance列或数据为空，视为通过")
        return True, messages

    elif step_num == 4:
        if not UPDATED_FILE.exists():
            return True, ["校验文件不存在，跳过验收"]
        df = pd.read_excel(UPDATED_FILE)
        date_col = "模型发布时间"
        if date_col in df.columns and len(df) > 0:
            fill_rate = df[date_col].notna().mean()
            messages.append(f"校验验收: 模型发布时间填充率{fill_rate:.0%}")
        else:
            messages.append("无'模型发布时间'列，视为通过")
        return True, messages

    elif step_num == 5:
        # 交叉巡检：只要脚本正常执行即通过，遗漏模型数仅做报告
        messages.append("交叉巡检验收: 脚本执行完成即通过")
        return True, messages

    elif step_num == 6:
        if not MASTER_FILE.exists():
            return False, ["总表文件不存在"]
        df = pd.read_excel(MASTER_FILE)
        name_col = "模型名称"
        if name_col in df.columns:
            duplicates = df[name_col].dropna().duplicated().sum()
            if duplicates > 0:
                messages.append(f"总表存在 {duplicates} 个重复模型名")
                return False, messages
        messages.append(f"合并验收通过: 总表{len(df)}行, 无重复模型名")
        return True, messages

    return True, ["未定义验收规则，默认通过"]


# ============================================================
# v3 步骤函数
# ============================================================

def step_collect_data(since_int, until_int, source, force):
    """步骤 1: 数据采集。调用 auto_collect.py + extract_models_llm.py 采集原始数据。

    数据源：
      1. auto_collect.py: llmstats + HuggingFace + 平台目录 + LM Arena
      2. extract_models_llm.py: 腾讯研究院 AI 速递（LLM 从文章中提取模型信息）
    """
    # ── 1/2: auto_collect.py（llmstats + HF + 平台目录 + LM Arena）──
    args = [sys.executable, "-X", "utf8", str(ACTION_DIR / "auto_collect.py"),
            "--since", str(since_int), "--until", str(until_int)]
    if source != "all":
        args += ["--source", source]
    if force:
        args.append("--force")

    returncode, _ = run_subprocess_heartbeat(
        args, cwd=str(ACTION_DIR), timeout_minutes=30,
        label="auto_collect.py"
    )
    if returncode != 0:
        log("数据采集失败（auto_collect）", "ERROR")
        return False

    # ── 2/2: extract_models_llm.py（腾讯研究院 LLM 提取）──
    # 仅在 source == "all" 或 source == "tencent" 时执行
    if source in ("all", "tencent"):
        extract_script = ACTION_DIR / "Extract" / "extract_models_llm.py"
        if extract_script.exists():
            log("腾讯研究院 LLM 提取...")
            tx_args = [sys.executable, "-X", "utf8", str(extract_script),
                       "--since", str(since_int), "--until", str(until_int),
                       "--write-excel"]
            tx_returncode, _ = run_subprocess_heartbeat(
                tx_args, cwd=str(extract_script.parent), timeout_minutes=15,
                label="extract_models_llm.py"
            )
            if tx_returncode != 0:
                log("腾讯研究院 LLM 提取失败（非致命，继续流水线）", "WARN")
            else:
                log("腾讯研究院 LLM 提取完成")
        else:
            log(f"腾讯研究院提取脚本不存在: {extract_script}", "WARN")

    return True

def step_dedup_against_master(since_int, until_int):
    """步骤 2: 增量去重。读取采集结果与总表去重，输出本次新增模型。

    采集结果在 UPDATED_FILE（兼容 auto_collect.py 当前写入逻辑），
    去重基准为 MASTER_FILE。
    返回新增模型数量。
    """
    import pandas as pd

    if not UPDATED_FILE.exists():
        log("采集结果文件不存在", "ERROR")
        return False

    df_collected = pd.read_excel(UPDATED_FILE)
    log(f"采集到 {len(df_collected)} 个模型")

    name_col = "模型名称"
    if name_col not in df_collected.columns:
        log(f"采集结果缺少 '{name_col}' 列", "ERROR")
        return False

    def _normalize(name):
        return str(name).strip().lower().replace("-", "").replace("_", "").replace(" ", "")

    # 读取总表建立去重集合
    if MASTER_FILE.exists():
        df_master = pd.read_excel(MASTER_FILE)
        master_names = set(df_master[name_col].dropna().apply(_normalize))
        log(f"总表已有 {len(master_names)} 个模型")
    else:
        master_names = set()
        log("总表不存在，所有采集模型视为新增", "WARN")

    # 去重
    is_new = ~df_collected[name_col].apply(_normalize).isin(master_names)
    df_new = df_collected[is_new].copy()
    log(f"去重后新增: {len(df_new)} 个")

    # 时间窗口过滤：平台目录采集的模型按"平台上架时间"过滤
    # 只保留上架时间在 since~until 窗口内的，或没有上架时间的（其他数据源）
    time_col = "平台上架时间"
    if time_col in df_new.columns and not df_new.empty:
        import pandas as _pd
        since_str = f"{str(since_int)[:4]}-{str(since_int)[4:6]}-{str(since_int)[6:]}"
        until_str = f"{str(until_int)[:4]}-{str(until_int)[4:6]}-{str(until_int)[6:]}"
        dates = _pd.to_datetime(df_new[time_col], errors="coerce")
        has_date = dates.notna()
        in_window = (dates >= since_str) & (dates <= until_str)
        # 保留：在窗口内的 + 没有上架时间的（非平台采集来源）
        keep_mask = ~has_date | in_window
        filtered_count = has_date.sum() - in_window.sum()
        df_new = df_new[keep_mask].copy()
        if filtered_count > 0:
            log(f"时间窗口过滤: 移除 {filtered_count} 个窗口外模型，保留 {len(df_new)} 个")

    if df_new.empty:
        log("本次无新增模型")
        # 写空增量到临时位置供后续步骤读取
        INCREMENT_DIR.mkdir(parents=True, exist_ok=True)
        empty_path = INCREMENT_DIR / f"{RUN_ID}_empty.xlsx"
        df_new.to_excel(empty_path, index=False)
        return True

    # 添加"触发时间"列
    df_new["触发时间"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 写入临时增量文件供后续步骤使用
    INCREMENT_DIR.mkdir(parents=True, exist_ok=True)
    increment_path = INCREMENT_DIR / f"{RUN_ID}.xlsx"
    df_new.to_excel(increment_path, index=False)
    log(f"增量已写入: {increment_path.name}（{len(df_new)} 个新模型）")

    # 写入 .meta 文件持久化 RUN_ID（跨步骤恢复用）
    meta_path = INCREMENT_DIR / f"{RUN_ID}.meta"
    meta_path.write_text(RUN_ID, encoding="utf-8")

    # 同时写入 UPDATED_FILE（兼容 push_dingtalk.py 和 review_models.py）
    df_new.to_excel(UPDATED_FILE, index=False)
    return True

def step_merge_and_archive(since_int, until_int):
    """步骤 5: 合并归档。将增量合并到总表 + 备份。

    数据源优先级（修复 Step 3/4 补全数据丢失问题）：
      1. Object-Models-Updated.xlsx — Step 3(审核) + Step 4(校验) 的产出（字段已补全）
      2. increments/{RUN_ID}.xlsx — fallback（未经补全的原始增量）
    """
    import pandas as pd

    # 检查是否为空增量
    empty_marker = INCREMENT_DIR / f"{RUN_ID}_empty.xlsx"
    if empty_marker.exists():
        log("本次无新增模型，跳过合并")
        empty_marker.unlink()  # 清理空标记
        return True

    # 优先读取 Object-Models-Updated.xlsx（经过 Step 3 审核 + Step 4 校验后的数据）
    # 这是修复"官网/备注/发布时间没有补上去"问题的关键：
    # Step 3/4 将补全结果写入 UPDATED_FILE，Step 5 必须从这里读取
    source_file = None
    if UPDATED_FILE.exists():
        source_file = UPDATED_FILE
        log(f"读取经审核+校验后的数据: {UPDATED_FILE.name}")
    else:
        # Fallback: 从 increments 目录读取原始增量
        increment_path = INCREMENT_DIR / f"{RUN_ID}.xlsx"
        if increment_path.exists():
            source_file = increment_path
            log(f"UPDATED_FILE 不存在，fallback 到增量: {increment_path.name}", "WARN")
        else:
            xlsx_files = sorted(
                [f for f in INCREMENT_DIR.glob("*.xlsx") if not f.stem.endswith("_empty")],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if xlsx_files:
                source_file = xlsx_files[0]
                log(f"RUN_ID 增量也不存在，fallback 到最新增量: {source_file.name}", "WARN")

    if source_file is None:
        log("无可用增量文件，跳过合并", "WARN")
        return True

    df_increment = pd.read_excel(source_file)
    if df_increment.empty:
        log("增量为空，跳过合并")
        return True

    # 归档增量到 increments/ 目录（保留审核+校验后的完整版本）
    INCREMENT_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = INCREMENT_DIR / f"{RUN_ID}.xlsx"
    if source_file != archive_path:
        df_increment.to_excel(archive_path, index=False)
        log(f"已归档增量: {archive_path.name}")

    # 备份总表
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if MASTER_FILE.exists():
        backup_name = f"Object-Models_{TIMESTAMP}.xlsx"
        shutil.copy2(MASTER_FILE, BACKUP_DIR / backup_name)
        log(f"总表已备份: Backup/{backup_name}")

    # 标记增量为新增（供日报 push_dingtalk.py 判断"新增"用）
    if "是否新增" not in df_increment.columns:
        df_increment["是否新增"] = "New"
    else:
        df_increment["是否新增"] = df_increment["是否新增"].astype(object)
        df_increment["是否新增"] = df_increment["是否新增"].fillna("New")

    # 合并到总表
    name_col = "模型名称"
    if MASTER_FILE.exists():
        df_master = pd.read_excel(MASTER_FILE)
        # 对齐列结构
        all_cols = list(df_master.columns)
        for col in df_increment.columns:
            if col not in all_cols:
                all_cols.append(col)
        df_master = df_master.reindex(columns=all_cols)
        df_increment = df_increment.reindex(columns=all_cols)
        df_merged = pd.concat([df_master, df_increment], ignore_index=True)
        log(f"总表合并: {len(df_master)} + {len(df_increment)} = {len(df_merged)}")
    else:
        df_merged = df_increment
        log(f"总表新建: {len(df_merged)} 个模型")

    if name_col in df_merged.columns:
        before_count = len(df_merged)
        df_merged["__model_key"] = df_merged[name_col].fillna("").astype(str).map(
            lambda name: re.sub(r"[\s\-_:/（）()【】\[\]]+", "", name.strip().lower())
        )
        df_merged = df_merged[df_merged["__model_key"] != ""]
        df_merged = df_merged.drop_duplicates(subset=["__model_key"], keep="last")
        df_merged = df_merged.drop(columns=["__model_key"])
        removed_count = before_count - len(df_merged)
        if removed_count > 0:
            log(f"总表合并后兜底去重: 移除 {removed_count} 条重复模型", "WARN")

    df_merged.to_excel(MASTER_FILE, index=False)
    log(f"总表已更新: {MASTER_FILE.name}")
    return True

def step_write_run_log(since_int, until_int, source, pushed):
    """步骤 6: 写入运行记录。"""
    import pandas as pd
    import csv

    # 统计本次新增数量
    increment_path = INCREMENT_DIR / f"{RUN_ID}.xlsx"
    new_count = 0
    if increment_path.exists():
        df = pd.read_excel(increment_path)
        new_count = len(df)

    # 写入 run_log.csv
    RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = RUN_LOG_FILE.exists()
    with open(RUN_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["run_id", "since", "until", "trigger_time", "new_count", "source", "pushed", "note"])
        writer.writerow([
            RUN_ID, since_int, until_int,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            new_count, source, pushed, ""
        ])
    log(f"运行记录已写入: {RUN_LOG_FILE.name}")

    # 生成 Trace 记录
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    trace_path = TRACE_DIR / f"trace_{since_int}-{until_int}_{TIMESTAMP}.md"
    trace_content = (
        f"# Trace: {since_int}-{until_int}\n\n"
        f"- **Run ID**: {RUN_ID}\n"
        f"- **时间段**: {since_int} ~ {until_int}\n"
        f"- **触发时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- **数据源**: {source}\n"
        f"- **新增模型**: {new_count}\n"
        f"- **已推送**: {pushed}\n"
    )
    trace_path.write_text(trace_content, encoding="utf-8")
    log(f"Trace 记录: {trace_path.name}")
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
# Checkpoint：检查每步产出文件是否已在今天生成过（v3 适配）
# ------------------------------------------------------------

def check_checkpoint(step_num, since_int=None, until_int=None):
    """检查第 step_num 步的产出文件是否已在今天生成过。

    返回 (has_cache: bool, summary_lines: list[str])。
    适配 v3 8步流水线。
    """
    import pandas as pd
    lines = []
    has_cache = False

    if step_num == 1:
        # 数据采集：检查 UPDATED_FILE 是否今天已更新
        if _file_modified_today(UPDATED_FILE):
            has_cache = True
            lines.append("UPDATED_FILE 今天已更新（采集结果已存在）")

    elif step_num == 2:
        # 增量去重：检查增量文件是否今天已生成
        if INCREMENT_DIR.exists():
            today_increments = [
                f for f in INCREMENT_DIR.glob(f"{RUN_ID}*.xlsx")
                if _file_modified_today(f)
            ]
            if today_increments:
                has_cache = True
                for increment_file in today_increments:
                    lines.append(f"今天已生成: {increment_file.name}")

    elif step_num == 3:
        # LLM 审核：检查 UPDATED_FILE 中 importance 列是否已填充
        if _file_modified_today(UPDATED_FILE) and UPDATED_FILE.exists():
            df = pd.read_excel(UPDATED_FILE, engine="openpyxl")
            if "importance" in df.columns and df["importance"].notna().mean() > 0.5:
                has_cache = True
                lines.append("importance 列已填充，审核可能已完成")

    elif step_num == 4:
        # 数据校验：检查校验脚本产出
        if _file_modified_today(UPDATED_FILE):
            has_cache = True
            lines.append("UPDATED_FILE 今天已更新（校验可能已完成）")

    elif step_num == 5:
        # 交叉巡检：检查巡检产出
        if _file_modified_today(UPDATED_FILE):
            has_cache = True
            lines.append("UPDATED_FILE 今天已更新（巡检可能已完成）")

    elif step_num == 6:
        # 合并归档：检查总表是否今天已更新
        if _file_modified_today(MASTER_FILE):
            has_cache = True
            lines.append("总表今天已更新（合并可能已完成）")

    elif step_num in (7, 8):
        # 钉钉推送 / 运行记录：检查日报文件
        daily_reports = list(REPORT_DIR.glob("daily_report_*.md"))
        today_dailies = [f for f in daily_reports if _file_modified_today(f)]
        if today_dailies:
            has_cache = True
            for daily_file in today_dailies:
                lines.append(f"今天已生成: {daily_file.name}")

    return has_cache, lines


# ============================================================
# 主流程
# ============================================================

def run_pipeline(since_int, until_int, source="all", start_step=1,
                 push=False, dry_run=False, force=False):
    """执行 v3 精简流水线。"""
    total_steps = len(STEPS)
    results = {}

    print(f"\n{'#'*60}")
    print(f"  AI 模型追踪 —— 端到端更新流水线 (v3)")
    print(f"  日期: {TODAY}")
    print(f"  时间窗口: {since_int} ~ {until_int}")
    print(f"  数据源: {source}")
    print(f"  起始步骤: {start_step}")
    print(f"  模式: {'预览' if dry_run else '执行'}")
    print(f"{'#'*60}")

    for step in STEPS:
        step_num = step["number"]
        step_name = step["name"]

        if step_num < start_step:
            results[step_num] = "SKIPPED"
            continue

        log_progress(step_num, total_steps, step_name)
        log(step["description"])

        if dry_run:
            results[step_num] = "DRY-RUN"
            continue

        success = False
        try:
            if step_num == 1:
                success = step_collect_data(since_int, until_int, source, force)
            elif step_num == 2:
                success = step_dedup_against_master(since_int, until_int)
            elif step_num == 3:
                # LLM 审核（review_models.py，传入时间窗口让 GPT-5.5 智能判断）
                script = step.get("script")
                if script and script.exists():
                    review_args = [sys.executable, "-X", "utf8", str(script),
                                   "--since", str(since_int), "--until", str(until_int)]
                    returncode, _ = run_subprocess_heartbeat(
                        review_args, cwd=str(ACTION_DIR), timeout_minutes=10,
                        label="review_models.py"
                    )
                    success = (returncode == 0)
                else:
                    log("审核脚本不存在，跳过", "SKIP")
                    success = True
            elif step_num == 4:
                # 数据校验：调用 verify_models.py 自动校验发布时间/官网/备注
                verify_script = ACTION_DIR / "verify_models.py"
                if verify_script.exists():
                    returncode, _ = run_subprocess_heartbeat(
                        [sys.executable, "-X", "utf8", str(verify_script)],
                        cwd=str(ACTION_DIR), timeout_minutes=15,
                        label="verify_models.py"
                    )
                    success = (returncode == 0)
                else:
                    log("verify_models.py 不存在，跳过数据校验", "WARN")
                    success = True
            elif step_num == 5:
                # 交叉巡检：LLM 联网搜索该时段新模型，与已有数据交叉比对补漏
                cross_check_script = ACTION_DIR / "cross_check.py"
                if cross_check_script.exists():
                    cross_args = [
                        sys.executable, "-X", "utf8", str(cross_check_script),
                        "--since", str(since_int), "--until", str(until_int),
                    ]
                    if UPDATED_FILE.exists():
                        cross_args.extend(["--excel", str(UPDATED_FILE)])
                    returncode, _ = run_subprocess_heartbeat(
                        cross_args, cwd=str(ACTION_DIR), timeout_minutes=10,
                        label="cross_check.py"
                    )
                    success = (returncode == 0)
                else:
                    log("cross_check.py 不存在，跳过交叉巡检", "WARN")
                    success = True
            elif step_num == 6:
                success = step_merge_and_archive(since_int, until_int)
            elif step_num == 7:
                # 钉钉推送
                if not push:
                    log("未指定 --push，仅预览日报（dry-run）")
                    log("💡 确认数据无误后，请手动执行: python push_dingtalk.py --since ... --until ...")
                args = [sys.executable, "-X", "utf8",
                        str(ACTION_DIR / "push_dingtalk.py"),
                        "--since", str(since_int), "--until", str(until_int)]
                if not push:
                    args.append("--dry-run")
                returncode, _ = run_subprocess_heartbeat(
                    args, cwd=str(ACTION_DIR), timeout_minutes=5,
                    label="push_dingtalk.py"
                )
                success = (returncode == 0)
            elif step_num == 8:
                success = step_write_run_log(since_int, until_int, source, push)
            else:
                log(f"未知步骤: {step_num}", "ERROR")
                success = False
        except Exception as exc:
            log(f"步骤异常: {exc}", "ERROR")
            success = False

        # 验收机制：步骤成功后执行数据验收
        if success:
            passed, verify_msgs = verify_step_output(step_num, since_int, until_int)
            for msg in verify_msgs:
                log(f"[验收] {msg}", "INFO" if passed else "WARN")
            if not passed:
                log(f"步骤 {step_num} 验收未通过（仅报警，不终止流水线）", "WARN")

        results[step_num] = "SUCCESS" if success else "FAILED"
        if not success:
            log(f"步骤 {step_num} 失败，流水线终止", "ERROR")
            break

    # 汇总
    print(f"\n{'='*60}")
    print(f"  流水线执行汇总")
    print(f"{'='*60}")
    for step in STEPS:
        n = step["number"]
        status = results.get(n, "NOT_RUN")
        icon = {"SUCCESS": "✅", "FAILED": "❌", "SKIPPED": "⏭️", "DRY-RUN": "🔍"}.get(status, "  ")
        print(f"  {icon} 步骤 {n}: {step['name']} → {status}")

    # 数据质量汇总
    if MASTER_FILE.exists() and not dry_run:
        import pandas as pd
        df = pd.read_excel(MASTER_FILE)
        total = len(df)
        company_filled = df["公司"].notna().sum() if "公司" in df.columns else 0
        note_filled = df["备注"].notna().sum() if "备注" in df.columns else 0
        date_filled = df["模型发布时间"].notna().sum() if "模型发布时间" in df.columns else 0
        print(f"\n  📊 总表数据质量（{total} 个模型）:")
        print(f"     公司: [{company_filled}/{total}] {int(100*company_filled/total)}%")
        print(f"     备注: [{note_filled}/{total}] {int(100*note_filled/total)}%")
        print(f"     发布时间: [{date_filled}/{total}] {int(100*date_filled/total)}%")

    all_success = all(v == "SUCCESS" for v in results.values() if v not in ("SKIPPED", "DRY-RUN", "NOT_RUN"))
    if all_success:
        print(f"\n  🎉 流水线执行完成！")
    else:
        print(f"\n  ⚠️ 流水线存在失败步骤，请检查")
    print(f"{'='*60}")
    return all_success


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="AI 模型追踪 —— v3 精简流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--since", type=str, help="起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, help="截止日期 (YYYYMMDD)")
    parser.add_argument("--step", type=int, default=1, help="从第N步开始")
    parser.add_argument("--source", type=str, default="all", help="数据源 (all/llmstats/txresearch/platform)")
    parser.add_argument("--push", action="store_true", help="推送到钉钉")
    parser.add_argument("--force", action="store_true", help="强制重新采集")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    args = parser.parse_args()

    from datetime import timedelta
    today = datetime.now()
    if args.until:
        until_int = int(args.until)
    else:
        until_int = int(today.strftime("%Y%m%d"))
    if args.since:
        since_int = int(args.since)
    else:
        since_int = int((today - timedelta(days=7)).strftime("%Y%m%d"))

    # 前置检查
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INCREMENT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    run_pipeline(
        since_int=since_int,
        until_int=until_int,
        source=args.source,
        start_step=args.step,
        push=args.push,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
