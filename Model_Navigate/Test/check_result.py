"""
Re 2026/05/09/11:08 数据完整性 + 逻辑一致性全字段校验
name: check_result
description: 流水线步骤 3 — 对 Updated.xlsx 中新增模型做全字段校验，
             覆盖填充率、逻辑一致性、可疑值检测，输出 PASS/WARN/FAIL。
"""
import sys
import pandas as pd
from pathlib import Path

_ROOT = Path(__file__).parent.parent

# 中国公司列表（与 auto_collect.py / config.py 保持一致）
CN_ORGS = {
    "alibaba", "qwen", "baidu", "bytedance", "tencent", "deepseek",
    "zhipu", "minimax", "moonshot", "stepfun", "sensetime", "01.ai",
    "iflytek", "kuaishou", "huawei", "xiaomi", "vivo", "meituan",
    "jd", "honor", "oppo", "bilibili", "netease",
}

# 必填字段（新增模型必须有值）
REQUIRED_FIELDS = ["模型名称", "公司", "国内外", "开闭源", "类型", "备注", "模型发布时间", "核实情况"]

# 合法枚举值
VALID_DOMESTIC = {"国内", "国外"}
VALID_OPEN_CLOSED = {"开源", "闭源", "未知", "集成产品"}
VALID_TYPES = {"基座", "多模态", "代码", "语音", "图像", "视频", "具身", "智能体", "领域", "未知"}
VALID_REASONING = {"thinking", "non-thinking", ""}


def safe_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator * 100:.0f}%"


def is_domestic(company: str) -> bool:
    company_lower = (company or "").lower().replace(" ", "").replace("-", "")
    return any(cn in company_lower for cn in CN_ORGS)


def run_check(excel_path: Path) -> int:
    """运行全字段校验，返回警告数。"""
    if not excel_path.exists():
        print(f"❌ 文件不存在: {excel_path}")
        return -1

    df = pd.read_excel(excel_path)
    new_mask = df["是否新增"].apply(lambda x: x == "New" if pd.notna(x) else False)
    new = df[new_mask]
    old_count = len(df) - len(new)

    print(f"总行数: {len(df)}  |  原有: {old_count}  |  新增: {len(new)}")
    if len(new) == 0:
        print("⚠️  无新增模型，跳过校验")
        return 0

    warnings = 0

    # ── 一、字段填充率检查 ──
    print("\n=== 一、字段填充率检查 ===")
    for col in REQUIRED_FIELDS:
        if col not in df.columns:
            print(f"  ❌ 缺失列: {col}")
            warnings += 1
            continue
        filled = new[col].notna().sum()
        total = len(new)
        pct = safe_pct(filled, total)
        status = "✅" if filled == total else "⚠️"
        if filled < total:
            warnings += 1
        print(f"  {status} {col}: {filled}/{total} ({pct})")

    # 选填字段（提示但不算警告）
    optional_fields = ["尺寸", "官网", "能否推理", "任务类型"]
    for col in optional_fields:
        if col not in df.columns:
            continue
        filled = new[col].notna().sum()
        total = len(new)
        print(f"  ℹ️  {col}: {filled}/{total} ({safe_pct(filled, total)})")

    # ── 二、逻辑一致性检查 ──
    print("\n=== 二、逻辑一致性检查 ===")

    # 2.1 国内外与公司是否匹配
    for idx, row in new.iterrows():
        company = str(row.get("公司", "")) if pd.notna(row.get("公司")) else ""
        domestic_label = str(row.get("国内外", "")) if pd.notna(row.get("国内外")) else ""
        if company and domestic_label:
            expected = "国内" if is_domestic(company) else "国外"
            if domestic_label != expected:
                model_name = row.get("模型名称", "?")
                print(f"  ⚠️  国内外不匹配: {model_name} — 公司={company}, 标记={domestic_label}, 预期={expected}")
                warnings += 1

    # 2.2 枚举值合法性
    for idx, row in new.iterrows():
        model_name = row.get("模型名称", "?")
        domestic = str(row.get("国内外", "")) if pd.notna(row.get("国内外")) else ""
        if domestic and domestic not in VALID_DOMESTIC:
            print(f"  ⚠️  非法国内外值: {model_name} — {domestic}")
            warnings += 1

        open_closed = str(row.get("开闭源", "")) if pd.notna(row.get("开闭源")) else ""
        if open_closed and open_closed not in VALID_OPEN_CLOSED:
            print(f"  ⚠️  非法开闭源值: {model_name} — {open_closed}")
            warnings += 1

        model_type = str(row.get("类型", "")) if pd.notna(row.get("类型")) else ""
        if model_type and model_type not in VALID_TYPES:
            print(f"  ⚠️  非法类型值: {model_name} — {model_type}")
            warnings += 1

        reasoning = str(row.get("能否推理", "")) if pd.notna(row.get("能否推理")) else ""
        if reasoning and reasoning not in VALID_REASONING:
            print(f"  ⚠️  非法推理值: {model_name} — {reasoning}")
            warnings += 1

    # 2.3 开源模型应有尺寸
    open_no_size = new[(new["开闭源"] == "开源") & (new["尺寸"].isna())]
    if len(open_no_size) > 0:
        print(f"  ⚠️  {len(open_no_size)} 个开源模型缺少尺寸:")
        for _, r in open_no_size.iterrows():
            company = r["公司"] if pd.notna(r["公司"]) else "?"
            print(f"      - {r['模型名称']} ({company})")
        warnings += len(open_no_size)

    # 2.4 官网是否为 llmstats 链接（非官方）
    if "官网" in df.columns:
        llmstats_urls = new[new["官网"].apply(
            lambda x: "llm-stats.com" in str(x) if pd.notna(x) else False
        )]
        if len(llmstats_urls) > 0:
            print(f"  ℹ️  {len(llmstats_urls)} 个模型的官网指向 llm-stats.com（非官方链接）:")
            for _, r in llmstats_urls.iterrows():
                print(f"      - {r['模型名称']}: {r['官网']}")

    if warnings == 0:
        print("  ✅ 逻辑一致性全部通过")

    # ── 三、可疑值检测 ──
    print("\n=== 三、可疑值检测 ===")
    suspicious = 0

    # 3.1 模型名称重复
    dup_names = new[new["模型名称"].duplicated(keep=False)]
    if len(dup_names) > 0:
        print(f"  ⚠️  新增模型中有重复名称:")
        for name in dup_names["模型名称"].unique():
            print(f"      - {name}")
        suspicious += 1

    # 3.2 发布时间格式检查
    if "模型发布时间" in df.columns:
        import re
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for idx, row in new.iterrows():
            release = str(row.get("模型发布时间", "")) if pd.notna(row.get("模型发布时间")) else ""
            if release and not date_pattern.match(release):
                print(f"  ⚠️  发布时间格式异常: {row.get('模型名称', '?')} — {release}")
                suspicious += 1

    # 3.3 类型为"未知"的模型
    unknown_type = new[new["类型"] == "未知"]
    if len(unknown_type) > 0:
        print(f"  ℹ️  {len(unknown_type)} 个模型类型为「未知」（需人工确认）:")
        for _, r in unknown_type.iterrows():
            print(f"      - {r['模型名称']}")

    if suspicious == 0:
        print("  ✅ 无可疑值")

    # ── 四、统计汇总 ──
    print("\n=== 四、统计汇总 ===")
    print("  按公司:")
    for company, count in new["公司"].value_counts().items():
        print(f"    {company}: {count}个")
    nan_company = new["公司"].isna().sum()
    if nan_company:
        print(f"    未知公司: {nan_company}个")

    print("  按类型:")
    for model_type, count in new["类型"].value_counts().items():
        print(f"    {model_type}: {count}个")

    print("  按开闭源:")
    for oc, count in new["开闭源"].value_counts().items():
        print(f"    {oc}: {count}个")

    # ── 总结 ──
    total_issues = warnings + suspicious
    print(f"\n{'='*50}")
    if total_issues == 0:
        print("✅ 全字段校验通过，无问题")
    else:
        print(f"⚠️  共发现 {total_issues} 个问题（{warnings} 个警告 + {suspicious} 个可疑值）")
    print(f"{'='*50}")
    return total_issues


if __name__ == "__main__":
    excel_path = _ROOT / "data" / "Object-Models-Updated.xlsx"
    issues = run_check(excel_path)
    sys.exit(1 if issues < 0 else 0)
