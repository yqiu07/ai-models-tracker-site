"""钉钉推送：渲染 ActionCard / Markdown 消息并发送。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import ssl
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, quote_plus

import aiohttp
import certifi

from .persistence import today_cst_date
from .schema import ModelRecord


# ─────────────────────────────────────────────────────────────
# 钉钉签名（从 news-digest 复用）
# ─────────────────────────────────────────────────────────────

def _dingtalk_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256).digest()
    return quote_plus(base64.b64encode(code))


def _build_url(webhook: str, secret: Optional[str]) -> str:
    if not secret:
        return webhook
    ts = str(round(time.time() * 1000))
    sign = _dingtalk_sign(secret, ts)
    return f"{webhook}&timestamp={ts}&sign={sign}"


def _dingtalk_link(url: str) -> str:
    """外链转钉钉深链接。"""
    return f"dingtalk://dingtalkclient/page/link?url={quote(url, safe='')}&pc_slide=false"


# ─────────────────────────────────────────────────────────────
# 消息渲染
# ─────────────────────────────────────────────────────────────

def render_message(
    records: list[ModelRecord],
    window: tuple[str, str],
    daily_url: str,
    excel_url: str = "",
    max_preview: int = 5,
) -> dict:
    """渲染钉钉 Markdown 消息。无新增时返回简短提示。"""
    date_str = today_cst_date()
    if not records:
        text = (
            f'<font color="#6366F1">**📭 AI 模型/智能体追踪**</font>\n\n'
            f"###### {window[0]} ~ {window[1]}\n\n"
            "本时段暂无新模型/智能体发布。"
        )
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"AI 模型追踪 · {date_str} · 无更新",
                "text": text,
            },
        }

    lines = [
        f'<font color="#6366F1">**📊 AI 模型/智能体日报**</font> '
        f'<font color="#999999" size="2">{date_str}</font>',
        "",
        f"###### 时间窗口：{window[0]} ~ {window[1]}",
        f"###### 本次新增：**{len(records)}** 个",
        "",
        "---",
        "",
    ]
    for i, rec in enumerate(records[:max_preview], 1):
        badges = []
        if rec.company:
            badges.append(rec.company)
        if rec.category and rec.category != "未知":
            badges.append(rec.category)
        if rec.thinking_mode == "thinking":
            badges.append("thinking")
        badge_str = " · ".join(badges) if badges else ""
        title_line = f"**{i}. {rec.raw_name}**"
        if badge_str:
            title_line += f' <font color="#94a3b8" size="2">[{badge_str}]</font>'
        lines.append(title_line)
        if rec.note:
            lines.append(f"###### {rec.note}")
        lines.append("")

    if len(records) > max_preview:
        lines.append(f"###### …… 还有 {len(records) - max_preview} 个，详见日报")
        lines.append("")

    lines.append("---")
    lines.append("")
    actions = []
    if daily_url:
        actions.append(f'<font color="#818CF8">[📄 查看完整日报]({_dingtalk_link(daily_url)})</font>')
    if excel_url:
        actions.append(f'<font color="#818CF8">[📥 下载 xlsx]({_dingtalk_link(excel_url)})</font>')
    if actions:
        lines.append(f"###### {' · '.join(actions)}")

    text = "\n".join(lines)
    if len(text) > 18000:
        text = text[:18000] + "\n\n> ...内容过长已截断"
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": f"AI 模型追踪 · {date_str} · 新增 {len(records)} 个",
            "text": text,
        },
    }


# ─────────────────────────────────────────────────────────────
# 推送
# ─────────────────────────────────────────────────────────────

async def push_to_webhook(
    webhook: str,
    secret: Optional[str],
    message: dict,
) -> bool:
    """推送 Markdown 消息到单个钉钉 webhook。"""
    url = _build_url(webhook, secret)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=message,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                body = await resp.text()
                if resp.status == 200:
                    try:
                        data = json.loads(body)
                        if data.get("errcode") == 0:
                            logging.info(f"[notify] 钉钉推送成功")
                            return True
                        logging.warning(f"[notify] 钉钉返回错误: {data}")
                    except Exception:
                        logging.warning(f"[notify] 钉钉响应非 JSON: {body[:200]}")
                else:
                    logging.warning(f"[notify] HTTP {resp.status}: {body[:200]}")
    except Exception as e:
        logging.warning(f"[notify] 推送异常: {e}")
    return False


async def notify(
    records: list[ModelRecord],
    window: tuple[str, str],
    daily_url: str,
    excel_url: str = "",
    *,
    dry_run: bool = False,
) -> bool:
    """主入口：根据环境变量推送。dry_run 模式只打印不发送。"""
    message = render_message(records, window, daily_url, excel_url)

    if dry_run:
        import sys
        separator = "=" * 60
        preview_text = json.dumps(message, ensure_ascii=False, indent=2)
        dry_run_output = (
            f"\n{separator}\n"
            f"[DRY RUN] DingTalk message preview (not sent):\n"
            f"{separator}\n"
            f"{preview_text}\n"
            f"{separator}\n"
        )
        # Windows GBK 终端无法输出 emoji，直接写字节流绕过编码
        try:
            sys.stdout.write(dry_run_output)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(dry_run_output.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")
        logging.info("[notify] DRY RUN: message rendered, not sent")
        return True

    # 测试 webhook
    webhook = os.getenv("DINGTALK_WEBHOOK")
    secret = os.getenv("DINGTALK_SECRET")
    if not webhook:
        logging.warning("[notify] 未配置 DINGTALK_WEBHOOK，跳过推送")
        return False

    return await push_to_webhook(webhook, secret, message)
