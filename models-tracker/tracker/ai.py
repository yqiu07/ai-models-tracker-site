"""LLM 双槽位调用：字段分类 + 备注浓缩。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import ssl
from dataclasses import dataclass
from typing import Optional

import aiohttp
import certifi


@dataclass
class ModelSlot:
    """一个 LLM 槽位的配置。"""
    api_key: str
    api_base: str
    model: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_base and self.model
                    and not self.api_key.startswith("sk-your"))


def load_slots() -> tuple[ModelSlot, ModelSlot]:
    """从环境变量加载两个槽位。NOTE 槽位未单独配置时复用 FIELD 槽位。"""
    field_slot = ModelSlot(
        api_key=os.getenv("TRACKER_FIELD_API_KEY", ""),
        api_base=os.getenv("TRACKER_FIELD_API_BASE", ""),
        model=os.getenv("TRACKER_FIELD_MODEL", ""),
    )
    note_slot = ModelSlot(
        api_key=os.getenv("TRACKER_NOTE_API_KEY") or field_slot.api_key,
        api_base=os.getenv("TRACKER_NOTE_API_BASE") or field_slot.api_base,
        model=os.getenv("TRACKER_NOTE_MODEL") or field_slot.model,
    )
    return field_slot, note_slot


async def _call_chat(
    session: aiohttp.ClientSession,
    slot: ModelSlot,
    messages: list[dict],
    *,
    max_tokens: int = 500,
    temperature: float = 0.2,
    proxy: Optional[str] = None,
) -> Optional[str]:
    """通用 OpenAI 兼容 Chat Completion 调用。"""
    if not slot.is_configured:
        logging.warning(f"LLM 槽位未配置，跳过调用 model={slot.model}")
        return None
    payload = {
        "model": slot.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {slot.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{slot.api_base.rstrip('/')}/chat/completions"
    try:
        async with session.post(url, json=payload, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                body = await resp.text()
                if is_network_blocked_response(resp.status, body):
                    logging.warning(
                        f"LLM API 被网络层拦截 (HTTP {resp.status}): "
                        f"域名可能被透明防火墙封锁，请配置 TRACKER_PROXY 或走系统代理"
                    )
                else:
                    logging.warning(f"LLM API 失败 HTTP {resp.status}: {body[:200]}")
                return None
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.warning(f"LLM API 异常: {e}")
        return None


def _strip_json_fence(text: str) -> str:
    """从可能含 ```json ... ``` 的回复中提取 JSON 主体。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def classify_fields(
    session: aiohttp.ClientSession,
    slot: ModelSlot,
    prompt_template: str,
    raw_name: str,
    company: str,
    evidence_summary: str,
    proxy: Optional[str] = None,
) -> Optional[dict]:
    """调用字段分类模型，返回 7 个字段的 JSON dict。"""
    user_content = (
        f"模型名: {raw_name}\n"
        f"公司: {company}\n"
        f"多源信息：\n{evidence_summary}"
    )
    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_content},
    ]
    raw = await _call_chat(session, slot, messages, max_tokens=400, temperature=0.1, proxy=proxy)
    if not raw:
        return None
    try:
        return json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        logging.warning(f"字段分类返回非 JSON: {e} | 原文: {raw[:200]}")
        return None


async def distill_note(
    session: aiohttp.ClientSession,
    slot: ModelSlot,
    prompt_template: str,
    raw_name: str,
    company: str,
    evidence_summary: str,
    proxy: Optional[str] = None,
) -> Optional[str]:
    """调用备注浓缩模型，返回一句话备注。"""
    user_content = (
        f"模型名: {raw_name}\n"
        f"公司: {company}\n"
        f"多源信息：\n{evidence_summary}"
    )
    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_content},
    ]
    raw = await _call_chat(session, slot, messages, max_tokens=300, temperature=0.3, proxy=proxy)
    if not raw:
        return None
    # 去除可能的引号包裹
    return raw.strip().strip("\"'\u201c\u201d\u300c\u300d")


def make_ssl_context(verify: bool = True) -> ssl.SSLContext:
    """统一的 SSL 上下文。verify=False 时跳过证书验证（用于公司网络代理环境）。"""
    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context(cafile=certifi.where())

def should_skip_ssl_verify() -> bool:
    """根据环境变量决定是否跳过 SSL 验证。"""
    return os.getenv("TRACKER_SKIP_SSL_VERIFY", "").lower() in ("1", "true", "yes")

def detect_system_proxy() -> Optional[str]:
    """检测系统代理（Windows 注册表 / IE 设置 / 环境变量）。

    优先级：
    1. TRACKER_PROXY 环境变量（显式配置）
    2. HTTPS_PROXY / HTTP_PROXY 环境变量
    3. Windows 系统代理（urllib 自动读取注册表）

    返回代理 URL 字符串，无代理时返回 None。

    说明：aiohttp 的 trust_env=True 在 Windows 上不可靠，
    不会自动读取系统注册表代理。必须用本函数显式检测后
    通过 proxy= 参数传入 session.get/post。
    """
    import urllib.request

    explicit = os.getenv("TRACKER_PROXY")
    if explicit:
        logging.debug(f"[proxy] 使用显式代理 TRACKER_PROXY={explicit}")
        return explicit

    env_proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if env_proxy:
        logging.debug(f"[proxy] 使用环境变量代理: {env_proxy}")
        return env_proxy

    system_proxies = urllib.request.getproxies()
    system_proxy = system_proxies.get("https") or system_proxies.get("http")
    if system_proxy:
        logging.debug(f"[proxy] 检测到系统代理: {system_proxy}")
        return system_proxy

    return None


_NETWORK_BLOCK_SIGNATURES = [
    "不在安全策略默认允许的范围内",
    "not allowed by the default security policy",
    "云壳",
    "Cloud Shell",
    "域名拦截",
    "Domain Blocking",
]


def is_network_blocked_response(status: int, body: str) -> bool:
    """判断 HTTP 响应是否为网络层拦截（透明防火墙/安全网关），
    而非 API 服务端本身的拒绝。

    区分意义：
    - 网络拦截 → 需要走代理或申请域名白名单
    - API 拒绝 → 需要检查 API Key / 模型名 / 请求参数
    """
    if status != 403:
        return False
    return any(sig in body for sig in _NETWORK_BLOCK_SIGNATURES)