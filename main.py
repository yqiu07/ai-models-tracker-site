"""
AI 模型追踪 —— 端到端一键更新流水线

使用方式：
    python main.py                    # 完整流水线（从头到尾）
    python main.py --step 3           # 从第3步开始（跳过前面已完成的步骤）
    python main.py --step 5           # 只生成报告（假设表格已更新完毕）
    python main.py --dry-run          # 预览流程，不实际执行
    python main.py --skip-verify      # 跳过核实状态步骤

流水线步骤：
    1. 准备基线：复制 Object-Models-Old.xlsx → Object-Models-Updated.xlsx
    2. 录入腾讯研究院模型：运行 Test/update_models.py
    3. 录入 llmstats 模型：运行 Test/update_llmstats.py
    4. 综合更新（补充模型 + benchmark + 标记列）：运行 Test/final_update.py
    5. 添加核实状态列：运行 Test/add_verify_status.py
    6. 填充模型发布时间：运行 Test/add_release_dates.py
    7. 数据完整性检查：运行 Test/check_result.py
    8. 生成更新报告：运行 Report/generate_report.py
    9. 整理 Case 文件：运行 Crawl/Arena_x/format_cases.py

前置条件：
    - Object-Models.xlsx 存在（原始基线表格）
    - Object-Models-Old.xlsx 存在（用于标记"是否新增"）
    - Test/ 下的脚本中已填入本次更新的模型数据（硬编码）
    - 请先关闭 Excel 中打开的相关文件
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
BASELINE_FILE = ACTION_DIR / "Object-Models-Old.xlsx"
UPDATED_FILE = ACTION_DIR / "Object-Models-Updated.xlsx"
BACKUP_DIR = ACTION_DIR / "Backup"

TODAY = date.today().isoformat()
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ============================================================
# 步骤定义
# ============================================================

STEPS = [
    {
        "number": 1,
        "name": "准备基线",
        "description": "复制 Object-Models.xlsx → Object-Models-Updated.xlsx",
        "script": None,  # 内置逻辑，不调用外部脚本
    },
    {
        "number": 2,
        "name": "录入腾讯研究院模型",
        "description": "将腾讯研究院AI速递中提取的新模型追加到表格",
        "script": ACTION_DIR / "Test" / "update_models.py",
    },
    {
        "number": 3,
        "name": "录入 llmstats 模型",
        "description": "将 llm-stats.com 排行榜中提取的新模型追加到表格",
        "script": ACTION_DIR / "Test" / "update_llmstats.py",
    },
    {
        "number": 4,
        "name": "综合更新",
        "description": "补充模型 + benchmark 数据更新 + 添加'是否新增'列",
        "script": ACTION_DIR / "Test" / "final_update.py",
    },
    {
        "number": 5,
        "name": "添加核实状态",
        "description": "添加'核实方式'和'核实情况'列，更新 HuggingFace 核实的尺寸",
        "script": ACTION_DIR / "Test" / "add_verify_status.py",
    },
    {
        "number": 6,
        "name": "填充模型发布时间",
        "description": "根据 llm-updates 时间线和腾讯研究院文章日期填充'模型发布时间'列",
        "script": ACTION_DIR / "Test" / "add_release_dates.py",
    },
    {
        "number": 7,
        "name": "数据完整性检查",
        "description": "检查更新后表格的字段完整性",
        "script": ACTION_DIR / "Test" / "check_result.py",
    },
    {
        "number": 8,
        "name": "生成更新报告",
        "description": "生成 Markdown 格式的更新报告（含统计图表）",
        "script": ACTION_DIR / "Report" / "generate_report.py",
    },
    {
        "number": 9,
        "name": "整理 Case 文件",
        "description": "将 Crawl/Arena_x/ 下的原始 Case 文件整理为标准 Markdown 表格",
        "script": ACTION_DIR / "Crawl" / "Arena_x" / "format_cases.py",
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


def run_script(script_path):
    """运行 Python 脚本，捕获输出"""
    if not script_path.exists():
        log(f"脚本不存在: {script_path}", "ERROR")
        return False

    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(script_path.parent),
    )

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            log(line)

    if result.returncode != 0:
        log(f"脚本执行失败（退出码 {result.returncode}）", "ERROR")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[:10]:
                log(f"  {line}", "ERROR")
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
    """
    if not BASELINE_FILE.exists():
        log(f"基线文件不存在: {BASELINE_FILE}", "ERROR")
        return False

    # 如果 Updated 已存在，先备份
    if UPDATED_FILE.exists():
        backup_current()

    # update_models.py 内部会从 Object-Models.xlsx 复制到 Updated.xlsx
    # 所以需要确保 Object-Models.xlsx 存在
    original_baseline = ACTION_DIR / "Object-Models.xlsx"
    if not original_baseline.exists():
        shutil.copy2(BASELINE_FILE, original_baseline)
        log(f"已创建: {original_baseline.name}（从 {BASELINE_FILE.name} 复制，供 update_models.py 使用）")

    # 同时也直接准备 Updated.xlsx（以防从步骤 3+ 开始时使用）
    shutil.copy2(BASELINE_FILE, UPDATED_FILE)
    log(f"已复制: {BASELINE_FILE.name} → {UPDATED_FILE.name}")

    # 验证
    import pandas as pd
    row_count = len(pd.read_excel(UPDATED_FILE))
    log(f"基线模型数量: {row_count}")
    return True


# ============================================================
# 主流程
# ============================================================

def run_pipeline(start_step=1, dry_run=False, skip_verify=False):
    """运行端到端流水线"""
    print(f"\n{'#'*60}")
    print(f"  AI 模型追踪 —— 端到端更新流水线")
    print(f"  日期: {TODAY}")
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

        # 跳过核实步骤
        if skip_verify and step_num == 5:
            print(f"\n  ⏭️ 跳过步骤 {step_num}: {step_name}（--skip-verify）")
            results[step_num] = "SKIPPED"
            continue

        log_header(step_num, step_name, step["description"])

        if dry_run:
            if step["script"]:
                log(f"将运行: {step['script']}", "STEP")
            else:
                log("将执行内置逻辑", "STEP")
            results[step_num] = "DRY_RUN"
            continue

        # 执行步骤
        success = False
        if step_num == 1:
            success = step_prepare_baseline()
        elif step["script"]:
            success = run_script(step["script"])
        else:
            log("无执行逻辑", "WARN")
            success = True

        results[step_num] = "SUCCESS" if success else "FAILED"

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
            "NOT_RUN": "⬜",
        }.get(status, "❓")
        print(f"  {icon} 步骤 {step_num}: {step['name']} — {status}")

    # 最终产出
    all_success = all(
        v in ("SUCCESS", "SKIPPED", "DRY_RUN") for v in results.values()
    )
    if all_success and not dry_run:
        print(f"\n{'='*60}")
        print(f"  🎉 流水线执行完成！")
        print(f"{'='*60}")
        if UPDATED_FILE.exists():
            print(f"  📊 更新表格: {UPDATED_FILE}")
        # 查找最新的报告文件（可能是硬编码日期或当天日期）
        report_dir = ACTION_DIR / "Report"
        report_files = sorted(report_dir.glob("update_report_*.md"), reverse=True)
        if report_files:
            print(f"  📝 更新报告: {report_files[0]}")
        formatted_path = ACTION_DIR / "Crawl" / "Arena_x" / "formatted_leaderboards.md"
        if formatted_path.exists():
            print(f"  📋 排行榜汇总: {formatted_path}")

    return all_success


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI 模型追踪 —— 端到端一键更新流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                  完整流水线
  python main.py --step 3         从第3步开始
  python main.py --step 5         只生成报告（假设表格已更新）
  python main.py --dry-run        预览流程
  python main.py --skip-verify    跳过核实状态步骤
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
        "--dry-run",
        action="store_true",
        help="预览模式：只显示将要执行的步骤，不实际运行",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="跳过核实状态步骤（步骤5）",
    )

    args = parser.parse_args()

    success = run_pipeline(
        start_step=args.step,
        dry_run=args.dry_run,
        skip_verify=args.skip_verify,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
