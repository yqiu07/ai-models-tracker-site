"""
Case 文件整理脚本
将 Crawl/Arena_x/ 下的原始 Case 文件（从网页复制的不规整数据）
整理为人机都可读的标准 Markdown 表格格式。

使用方式：
    python format_cases.py

输入：当前目录下所有 Case-*.md 和其他 .md 文件
输出：formatted_leaderboards.md（整理后的汇总文件）
"""
import re
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / "formatted_leaderboards.md"


def parse_code_arena(lines):
    """解析 Code Arena / Chat Arena 排行榜（STT.md 实际内容）"""
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 找到排名行（纯数字）
        if re.match(r"^\d+$", line):
            rank = int(line)
            # 下一行是公司，再下一行是模型名
            company = lines[i + 1].strip() if i + 1 < len(lines) else ""
            model = lines[i + 2].strip() if i + 2 < len(lines) else ""
            # 跳过重复的公司名
            company2 = lines[i + 3].strip() if i + 3 < len(lines) else ""
            # 数据行
            data_line = lines[i + 4].strip() if i + 4 < len(lines) else ""
            parts = data_line.split("\t")

            code_arena = parts[0] if len(parts) > 0 else "—"
            chat_arena = parts[1] if len(parts) > 1 else "—"
            gpqa = parts[2] if len(parts) > 2 else "—"
            swe = parts[3] if len(parts) > 3 else "—"
            context = parts[4] if len(parts) > 4 else "—"
            input_price = parts[5] if len(parts) > 5 else "—"
            output_price = parts[6] if len(parts) > 6 else "—"

            # License 在后面的行
            license_val = ""
            for j in range(i + 5, min(i + 8, len(lines))):
                if "Proprietary" in lines[j] or "Open Source" in lines[j]:
                    license_val = lines[j].strip()
                    break

            rows.append({
                "rank": rank,
                "model": model,
                "company": company,
                "code_arena": code_arena,
                "chat_arena": chat_arena,
                "gpqa": gpqa,
                "swe_bench": swe,
                "context": context,
                "input_price": input_price,
                "output_price": output_price,
                "license": license_val,
            })
            i += 6
        else:
            i += 1
    return rows


def parse_image_gen(lines):
    """解析 Image Generation 排行榜"""
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^\d+$", line):
            rank = int(line)
            company = lines[i + 1].strip() if i + 1 < len(lines) else ""
            model = lines[i + 2].strip() if i + 2 < len(lines) else ""
            data_line = lines[i + 4].strip() if i + 4 < len(lines) else ""
            parts = data_line.split("\t")

            img_gen = parts[0] if len(parts) > 0 else "—"
            img_edit = parts[1] if len(parts) > 1 else "—"
            price = parts[2] if len(parts) > 2 else "—"

            license_val = ""
            for j in range(i + 5, min(i + 8, len(lines))):
                if "Proprietary" in lines[j] or "Open Source" in lines[j]:
                    license_val = lines[j].strip()
                    break

            rows.append({
                "rank": rank,
                "model": model,
                "company": company,
                "image_gen": img_gen,
                "image_edit": img_edit,
                "price": price,
                "license": license_val,
            })
            i += 6
        else:
            i += 1
    return rows


def parse_video_gen(lines):
    """解析 Video Generation / TTS 排行榜"""
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^\d+$", line):
            rank = int(line)
            company = lines[i + 1].strip() if i + 1 < len(lines) else ""
            model = lines[i + 2].strip() if i + 2 < len(lines) else ""
            data_line = lines[i + 4].strip() if i + 4 < len(lines) else ""
            parts = data_line.split("\t")

            score = parts[0] if len(parts) > 0 else "—"
            price = parts[1] if len(parts) > 1 else "—"

            license_val = ""
            for j in range(i + 5, min(i + 8, len(lines))):
                if "Proprietary" in lines[j] or "Open Source" in lines[j]:
                    license_val = lines[j].strip()
                    break

            rows.append({
                "rank": rank,
                "model": model,
                "company": company,
                "score": score,
                "price": price,
                "license": license_val,
            })
            i += 6
        else:
            i += 1
    return rows


def parse_stt(lines):
    """解析 STT（语音转文字）排行榜"""
    return parse_video_gen(lines)  # 格式相同


def parse_llm_leaderboard(lines):
    """
    解析 LLM Leaderboards / Open LLM Leaderboard。
    格式：logo行 → 模型名 → 国旗行(含tab分隔数据) → 后续数据行 → 发布时间 → 公司名
    """
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.endswith("logo"):
            i += 1
            continue

        # logo行后面是模型名
        model_name = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not model_name or model_name in ("Model", "Country", "License"):
            i += 2
            continue

        # 国旗行：包含国旗emoji + Open/Closed
        flag_line = lines[i + 2].strip() if i + 2 < len(lines) else ""

        country = ""
        if "\U0001F1FA\U0001F1F8" in flag_line:
            country = "美国"
        elif "\U0001F1E8\U0001F1F3" in flag_line:
            country = "中国"
        elif "\U0001F1EB\U0001F1F7" in flag_line:
            country = "法国"
        elif "\U0001F1EE\U0001F1F3" in flag_line:
            country = "印度"

        license_val = "Open" if "Open" in flag_line else ("Closed" if "Closed" in flag_line else "")

        # 收集从国旗行开始的所有tab分隔数据，直到遇到下一个logo行或公司名行
        all_data = []
        for part in flag_line.split("\t"):
            part = part.strip()
            if part and part not in ("Open", "Closed") and not any(
                c in part for c in "\U0001F1E6\U0001F1E8\U0001F1EA\U0001F1EB\U0001F1EE\U0001F1F3\U0001F1FA\U0001F1F8\U0001F1F7"
            ):
                all_data.append(part)

        # 继续收集后续行的数据（直到遇到发布时间或公司名）
        released = ""
        company = ""
        j = i + 3
        while j < len(lines) and j < i + 10:
            jline = lines[j].strip()
            if jline.endswith("logo"):
                break
            # 发布时间行
            if re.match(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s*\d{4}", jline):
                released = jline
                j += 1
                continue
            # 公司名行（短文本，在发布时间之后）
            if released and jline and len(jline) < 30 and jline not in ("Open", "Closed", model_name):
                if "%" not in jline and "$" not in jline and "\t" not in jline:
                    company = jline
                    break
            # 数据行（包含tab或百分号或美元符号）
            if "\t" in jline or "%" in jline or "$" in jline:
                for part in jline.split("\t"):
                    part = part.strip()
                    if part:
                        all_data.append(part)
            j += 1

        # 从 all_data 中提取关键字段
        context = ""
        input_price = ""
        output_price = ""
        speed = ""
        code_arena = ""
        params = ""

        # 上下文窗口（如 200k, 262.1k, 1M 等）
        for d in all_data:
            if re.match(r"^\d+\.?\d*[kKmM]$", d):
                context = d
                break

        # 价格（$开头）
        dollar_fields = [d for d in all_data if d.startswith("$")]
        if len(dollar_fields) >= 1:
            input_price = dollar_fields[0]
        if len(dollar_fields) >= 2:
            output_price = dollar_fields[1]

        # 速度（含 c/s 或 tok/s）
        for d in all_data:
            if "c/s" in d or "tok/s" in d:
                speed = d
                break

        # Code Arena（纯数字，通常是3-4位）
        for d in all_data:
            if re.match(r"^-?\d{2,4}$", d):
                val = int(d)
                if -2000 <= val <= 3000:
                    code_arena = d
                    break

        # 百分号字段（GPQA, AIME, SWE-bench, MMMLU等）
        pct_fields = [d for d in all_data if "%" in d]
        gpqa = pct_fields[0] if len(pct_fields) >= 1 else ""
        aime = pct_fields[1] if len(pct_fields) >= 2 else ""
        swe_bench = pct_fields[2] if len(pct_fields) >= 3 else ""
        mmmlu = pct_fields[4] if len(pct_fields) >= 5 else ""

        # 参数量（纯数字或小数，排除已被识别为 code_arena 的值）
        for d in reversed(all_data):
            if d == code_arena:
                continue
            if re.match(r"^\d+\.?\d*$", d):
                try:
                    val = float(d)
                    if 0.1 <= val <= 2000:
                        params = d
                        break
                except ValueError:
                    pass

        rows.append({
            "model": model_name,
            "country": country,
            "license": license_val,
            "context": context,
            "input_price": input_price,
            "output_price": output_price,
            "speed": speed,
            "code_arena": code_arena,
            "gpqa": gpqa,
            "aime": aime,
            "swe_bench": swe_bench,
            "mmmlu": mmmlu,
            "params": params,
            "released": released,
            "company": company,
        })
        i = j + 1

    return rows


def parse_llm_updates(lines):
    """
    解析 LLM updates 时间线。
    格式：日期行 → "· N releases" → [公司名, 模型名, 类型, License, 重复公司名, "•", "Xw ago", GPQA行] × N
    注意：文件开头有重复公司名列表（如 "MetaMeta"），需要跳过。
    """
    rows = []
    current_date = ""
    i = 0

    # 跳过文件头部（直到第一个日期行）
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$", line):
            break
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        # 日期行
        date_match = re.match(
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$",
            line,
        )
        if date_match:
            current_date = line
            i += 1
            # 跳过 "· N release(s)" 行
            if i < len(lines) and lines[i].strip().startswith("·"):
                i += 1
            continue

        # 模型块：公司名 → 模型名 → 类型 → License → 重复公司名 → • → Xw ago → GPQA(可选)
        if current_date and line and not line.startswith("·") and not line.startswith("•"):
            company = line
            model = ""
            release_type = ""
            license_val = ""
            gpqa = ""

            if i + 1 < len(lines):
                model = lines[i + 1].strip()

            if i + 2 < len(lines):
                rt = lines[i + 2].strip()
                if rt in ("Release", "Preview", "Pro", "Fast", "Update", "Turbo", "Lite", "Max", "Mini"):
                    release_type = rt

            if i + 3 < len(lines):
                lic = lines[i + 3].strip()
                if lic in ("Proprietary", "Open Source"):
                    license_val = lic

            # 查找 GPQA
            for j in range(i + 4, min(i + 9, len(lines))):
                if j < len(lines) and "GPQA:" in lines[j]:
                    gpqa_match = re.search(r"GPQA:\s*([\d.]+)", lines[j])
                    if gpqa_match:
                        gpqa = gpqa_match.group(1)
                    break

            if model and release_type:
                rows.append({
                    "date": current_date,
                    "model": model,
                    "company": company,
                    "release_type": release_type,
                    "license": license_val,
                    "gpqa": gpqa,
                })
                # 跳过整个模型块（公司+模型+类型+License+重复公司+•+ago+GPQA）
                i += 8
                continue

        i += 1

    return rows


def format_table(headers, rows, key_map):
    """生成 Markdown 表格"""
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "|" + "|".join(["---"] * len(headers)) + "|"
    body_lines = []
    for row in rows:
        cells = [str(row.get(k, "—")).strip() for k in key_map]
        body_lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([header_line, sep_line] + body_lines)


def process_file(filepath):
    """处理单个 Case 文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return None, None

    lines = content.split("\n")
    filename = os.path.basename(filepath)

    # 提取数据来源
    source_line = ""
    for line in lines[:3]:
        if "数据来源" in line or "https://" in line:
            source_line = line.strip()
            break

    # 判断文件类型并解析
    header_line = ""
    for line in lines:
        if "Rank" in line and "Model" in line:
            header_line = line
            break

    if "Code Arena" in content and "Chat Arena" in content:
        category = "LLM 排行榜（Code Arena + Chat Arena）"
        rows = parse_code_arena(lines)
        if rows:
            headers = ["#", "模型", "公司", "Code Arena", "Chat Arena", "GPQA", "SWE-bench", "上下文", "Input $/M", "Output $/M", "License"]
            keys = ["rank", "model", "company", "code_arena", "chat_arena", "gpqa", "swe_bench", "context", "input_price", "output_price", "license"]
            table = format_table(headers, rows, keys)
            return category, table

    elif "Image Gen" in content and "Image Edit" in content:
        category = "图像生成排行榜"
        rows = parse_image_gen(lines)
        if rows:
            headers = ["#", "模型", "公司", "Image Gen ELO", "Image Edit ELO", "$/Image", "License"]
            keys = ["rank", "model", "company", "image_gen", "image_edit", "price", "license"]
            table = format_table(headers, rows, keys)
            return category, table

    elif "TTS" in header_line:
        # 检查实际内容：如果有 elevenlabs/deepgram 等 TTS 厂商
        if "elevenlabs" in content.lower() or "deepgram" in content.lower() or "cartesia" in content.lower():
            category = "TTS（文字转语音）排行榜"
        else:
            category = "视频生成排行榜"
        rows = parse_video_gen(lines)
        if rows:
            headers = ["#", "模型", "公司", "ELO", "$/单位", "License"]
            keys = ["rank", "model", "company", "score", "price", "license"]
            table = format_table(headers, rows, keys)
            return category, table

    elif "STT" in header_line:
        category = "STT（语音转文字）排行榜"
        rows = parse_stt(lines)
        if rows:
            headers = ["#", "模型", "公司", "ELO", "$/Minute", "License"]
            keys = ["rank", "model", "company", "score", "price", "license"]
            table = format_table(headers, rows, keys)
            return category, table

    # LLM updates 时间线（必须在 LLM Leaderboard 之前判断，因为两者都含 "Organization"）
    # 特征：包含 "Version Timeline" 和日期格式的发布记录，不含 "logo" 行
    if "Version Timeline" in content and "logo" not in content:
        category = "模型更新时间线"
        rows = parse_llm_updates(lines)
        if rows:
            headers = ["日期", "模型", "公司", "类型", "License", "GPQA"]
            keys = ["date", "model", "company", "release_type", "license", "gpqa"]
            table = format_table(headers, rows, keys)
            return category, table
        return category, None

    # LLM Leaderboards / Open LLM Leaderboard（含 "logo" 行的格式）
    if "logo" in content and ("Organization" in content or "Released" in content):
        category = "LLM 排行榜（综合）"
        rows = parse_llm_leaderboard(lines)
        if rows:
            headers = ["模型", "国家", "License", "上下文", "Input $/M", "Output $/M",
                        "Speed", "Code Arena", "GPQA", "AIME", "SWE-bench", "MMMLU",
                        "参数量(B)", "发布时间", "公司"]
            keys = ["model", "country", "license", "context", "input_price", "output_price",
                     "speed", "code_arena", "gpqa", "aime", "swe_bench", "mmmlu",
                     "params", "released", "company"]
            table = format_table(headers, rows, keys)
            return category, table
        return category, None

    return None, None


def main():
    output_lines = []
    output_lines.append("# llm-stats.com 排行榜数据汇总")
    output_lines.append("")
    output_lines.append("> **数据来源**：https://llm-stats.com")
    output_lines.append("> **整理时间**：自动生成")
    output_lines.append("> **整理方式**：由 `format_cases.py` 从原始 Case 文件解析")
    output_lines.append("")
    output_lines.append("---")
    output_lines.append("")

    # 按顺序处理文件
    case_files = [
        "Case-llmstats-AI leaderboards STT.md",
        "Case-llmstats-AI leaderboards TTS.md",
        "Case-llmstats-AI leaderboards video generation.md",
        "Case-llmstats-AI leaderboards-image generation.md",
        "Case-llmstats-LLM Leaderboards.md",
        "Open LLM Leaderboard.md",
        "LLM-updates-byllmstats.md",
    ]

    processed_count = 0
    for filename in case_files:
        filepath = SCRIPT_DIR / filename
        if not filepath.exists():
            output_lines.append("### {} （文件不存在）".format(filename))
            output_lines.append("")
            continue

        category, table = process_file(filepath)

        if category is None:
            output_lines.append("### {} （空文件或无法解析）".format(filename))
            output_lines.append("")
            continue

        output_lines.append("### {}".format(category))
        output_lines.append("")
        output_lines.append("> 原始文件：`{}`".format(filename))
        output_lines.append("")

        if table:
            output_lines.append(table)
            processed_count += 1
        else:
            # 对于无法解析为表格的文件，提供原始内容的摘要
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            # 提取模型名称
            model_names = []
            for line in content.split("\n"):
                line = line.strip()
                # 跳过空行和纯数字行
                if not line or re.match(r"^\d+$", line):
                    continue
                # 跳过 logo/图片/链接行
                if "logo" in line or "![" in line or "http" in line:
                    continue
                # 跳过纯数据行（包含大量数字/百分号/美元符号）
                if line.count("%") > 2 or line.count("$") > 2:
                    continue
                if line.count("\t") > 3:
                    continue
                # 跳过表头
                if "Rank" in line or "Model" in line or "Organization" in line:
                    continue
                # 跳过公司名重复行
                if line in ["Google", "OpenAI", "Anthropic", "Meta", "Zhipu AI", "ZAI",
                            "Qwen", "Xiaomi", "MiniMax", "Mistral", "Nvidia", "Sarvam AI"]:
                    continue
                # 可能是模型名称
                if len(line) > 2 and len(line) < 50 and not line.startswith("-"):
                    model_names.append(line)

            if model_names:
                output_lines.append("**包含的模型**：")
                output_lines.append("")
                for name in model_names[:30]:
                    output_lines.append("- {}".format(name))
                if len(model_names) > 30:
                    output_lines.append("- ...（共 {} 个）".format(len(model_names)))
                processed_count += 1

        output_lines.append("")
        output_lines.append("---")
        output_lines.append("")

    # 写入文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print("整理完成！")
    print("  输入文件: {} 个".format(len(case_files)))
    print("  成功解析: {} 个".format(processed_count))
    print("  输出文件: {}".format(OUTPUT_FILE))


if __name__ == "__main__":
    main()
