"""
Model Navigate — 统一配置文件
============================
所有工程可变参数集中管理，按类别分区。

参数分三层：
  1. `.env`（脱敏参数）：API Key、Webhook、Token、API Base URL
  2. `config.py`（本文件，工程可变参数）：URL、超时、UA、数据常量、阈值等
  3. 各脚本内部（不变核心逻辑）：CSS 选择器、去重算法、CLI 参数解析、步骤定义

使用方式：
  from config import cfg
  print(cfg.CHROME_USER_AGENT)
  print(cfg.LLMSTATS_PAGES)
"""

from __future__ import annotations

import os
from pathlib import Path


# ── 项目根目录（所有路径基于此推导）──
ROOT = Path(__file__).parent.resolve()


# ============================================================
#  一、数据源 URL
# ============================================================

# llmstats.com 页面配置
LLMSTATS_PAGES = {
    "ai": {
        "url": "https://llm-stats.com",
        "label": "AI Leaderboard (首页)",
    },
    "llm": {
        "url": "https://llm-stats.com/leaderboards/llm-leaderboard",
        "label": "LLM Leaderboard (详情)",
    },
    "open": {
        "url": "https://llm-stats.com/leaderboards/open-llm-leaderboard",
        "label": "Open LLM Leaderboard",
    },
    "updates": {
        "url": "https://llm-stats.com/llm-updates",
        "label": "LLM Updates (时间线)",
    },
}

# llmstats 模型详情 URL 模板（用于填写"官网"列）
LLMSTATS_MODEL_URL_TEMPLATE = "https://llm-stats.com/models/{model_id}"

# HuggingFace API
HUGGINGFACE_API_TEMPLATE = "https://huggingface.co/api/models/{search_name}"

# 腾讯研究院搜狐号主页
TXRESEARCH_SOHU_URL = (
    "https://mp.sohu.com/profile?xpt="
    "bGl1amluc29uZzIwMDBAMTI2LmNvbQ=="
    "&spm=smpc.content.author.1.1776311557025E5eBJ3T"
)


# ============================================================
#  二、HTTP / 浏览器配置
# ============================================================

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

HTTP_HEADERS = {
    "User-Agent": CHROME_USER_AGENT,
}

# Selenium 浏览器窗口大小
CHROME_WINDOW_SIZE = "1920,1080"

# SSL 验证（生产环境建议开启）
SSL_VERIFY = False


# ============================================================
#  三、超时 / 重试 / 运行参数
# ============================================================

# 子进程通用心跳配置
SUBPROCESS_TIMEOUT_MINUTES = 30      # 子进程最大运行时间
SUBPROCESS_HEARTBEAT_SECONDS = 60    # 心跳探测间隔
SUBPROCESS_SILENT_LIMIT = 300        # 无输出判定不健康（秒）

# 各脚本超时覆盖（分钟）
TIMEOUT_AUTO_COLLECT = 30            # 数据采集
TIMEOUT_LLM_EXTRACT_LIST = 2        # LLM 提取 --list 查询
TIMEOUT_LLM_EXTRACT_SINGLE = 10     # LLM 提取单篇文章
TIMEOUT_REVIEW = 10                 # GPT-5.5 审核
TIMEOUT_PUSH = 5                    # 钉钉推送

# HTTP 请求超时（秒）
HTTP_TIMEOUT_LLMSTATS = 30          # llmstats 页面抓取
HTTP_TIMEOUT_HUGGINGFACE = 15       # HuggingFace API
HTTP_TIMEOUT_LLM_API = 300          # LLM API 调用
HTTP_TIMEOUT_REVIEW_API = 180       # GPT-5.5 审核 API
HTTP_TIMEOUT_DINGTALK = 15          # 钉钉推送
HTTP_TIMEOUT_FULLTEXT = 30          # 全文抓取

# 爬虫控制
CRAWL_MAX_SCROLL_RETRIES = 15       # 滚动无新文章后放弃次数
CRAWL_SCROLL_PAUSE_SECONDS = 2.5    # 每次滚动后等待秒数
CRAWL_FULLTEXT_DELAY = 1.0          # 每篇文章抓取间隔（秒）
CRAWL_PAGE_LOAD_WAIT = 5            # 页面加载等待（秒）

# 默认时间窗口
DEFAULT_LOOKBACK_DAYS = 7           # 未指定 --since 时的回溯天数

# LLM 调用参数
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS_EXTRACT = 4000      # LLM 提取
LLM_MAX_TOKENS_REVIEW = 8000       # GPT-5.5 审核
LLM_ARTICLE_TRUNCATE = 8000        # 文章截断长度（字符）
LLM_POLITE_DELAY = 1               # LLM 调用间隔（秒）

# GPT-5.5 审核
REVIEW_BATCH_SIZE = 20              # 每批审核模型数
REVIEW_BATCH_DELAY = 2              # 批次间间隔（秒）


# ============================================================
#  四、文件路径（基于 ROOT 推导，换机器不用改）
# ============================================================

DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "Report"
EXTRACT_DIR = ROOT / "Extract"
CRAWL_DIR = ROOT / "Crawl"

# Excel 文件
EXCEL_BASELINE = DATA_DIR / "Object-Models-Old.xlsx"
EXCEL_UPDATED = DATA_DIR / "Object-Models-Updated.xlsx"
EXCEL_MEDIUM = DATA_DIR / "Object-Models-Medium.xlsx"
EXCEL_ONLY = DATA_DIR / "Object-Models-Updated - only.xlsx"
EXCEL_ORIGINAL = DATA_DIR / "Object-Models.xlsx"

# 报告文件
TEST_REPORT = REPORT_DIR / "E2E-Test-Report.md"
UPDATE_LOG = REPORT_DIR / "Update-Log.md"
REVIEW_REPORT = REPORT_DIR / "review_report.md"

# 数据采集输出
LLMSTATS_DIR = CRAWL_DIR / "Arena_x"
TX_DIR = ROOT / "TXresearch"
ARTICLES_DIR = EXTRACT_DIR / "articles"
TXCRAWL_XLSX = EXTRACT_DIR / "TXCrawl.xlsx"
TXCRAWL_RESULT_XLSX = EXTRACT_DIR / "TXCrawl_result.xlsx"
LLM_EXTRACT_JSON = EXTRACT_DIR / "extracted_models_llm.json"
LLMSTATS_JSON = LLMSTATS_DIR / "llmstats_models.json"

# llmstats 本地 HTML 缓存文件名
LLMSTATS_LOCAL_FILES = {
    "ai": LLMSTATS_DIR / "llm-stats-ai.com",
    "llm": LLMSTATS_DIR / "llm-stats-LLM.com",
    "open": LLMSTATS_DIR / "llm-stats-open-llm.com",
    "updates": LLMSTATS_DIR / "llm-stats-updates.com",
}

# 子脚本路径
SCRIPT_AUTO_COLLECT = ROOT / "auto_collect.py"
SCRIPT_REVIEW = ROOT / "review_models.py"
SCRIPT_PUSH = ROOT / "push_dingtalk.py"
SCRIPT_LLM_EXTRACT = EXTRACT_DIR / "extract_models_llm.py"
SCRIPT_CRAWL_SOHU = CRAWL_DIR / "TXresearch" / "crawl_sohu.py"
SCRIPT_CHECK_RESULT = ROOT / "Test" / "check_result.py"
SCRIPT_GENERATE_REPORT = REPORT_DIR / "generate_report.py"
SCRIPT_FORMAT_CASES = CRAWL_DIR / "Arena_x" / "format_cases.py"

# 备份目录
BACKUP_DIR = ROOT / "Backup"


# ============================================================
#  五、LLM 模型配置（默认值，可被 .env 覆盖）
# ============================================================

# 主 API（kuai — 用于 LLM 提取和审核）
DEFAULT_KUAI_API_BASE = "https://api.kuai.host/v1"
DEFAULT_KUAI_MODEL_EXTRACT = "claude-opus-4-6"    # LLM 提取用模型
DEFAULT_KUAI_MODEL_REVIEW = "gpt-5.5"             # 审核用模型

# 备选 API（DashScope — Qwen）
DEFAULT_DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"


# ============================================================
#  六、数据常量（随业务变化需更新）
# ============================================================

# 中国公司列表（用于判断国内/国外）
CN_ORGS = {
    "alibaba", "qwen", "baidu", "bytedance", "tencent", "deepseek",
    "zhipu", "minimax", "moonshot", "stepfun", "sensetime", "01.ai",
    "iflytek", "kuaishou", "huawei", "xiaomi", "vivo", "meituan",
    "jd", "honor", "oppo", "bilibili", "netease",
}

# HuggingFace 组织映射（llmstats org_id → HF org slug）
HF_ORG_MAP = {
    "google": "google",
    "meta": "meta-llama",
    "mistral": "mistralai",
    "microsoft": "microsoft",
    "alibaba": "Qwen",
    "deepseek": "deepseek-ai",
    "zhipu": "THUDM",
    "01ai": "01-ai",
    "cohere": "CohereForAI",
    "nvidia": "nvidia",
    "apple": "apple",
    "databricks": "databricks",
    "ai21": "AI21Labs",
    "together": "togethercomputer",
    "stability": "stabilityai",
    "tencent": "Tencent-Hunyuan",
    "baichuan": "baichuan-inc",
    "internlm": "internlm",
    "yi": "01-ai",
    "xai": "xai-org",
}

# 产品泛称黑名单（LLM 提取时过滤）
GENERIC_PRODUCT_NAMES = {
    "chatgpt", "gpt", "claude", "gemini", "cursor", "copilot",
    "sora", "manus", "豆包", "元宝", "千问", "即梦", "文心一言",
    "通义", "kimi", "deepseek", "perplexity", "midjourney",
    "stable diffusion", "dall-e", "firefly", "ideogram",
    "flux", "runway", "pika", "luma", "kling", "可灵",
    "windsurf", "replit", "v0", "bolt",
}

# Excel 列结构（16 列）
EXCEL_COLUMNS = [
    "模型名称", "是否接入", "workflow接入进展", "公司",
    "国内外", "开闭源", "尺寸", "类型",
    "能否推理", "任务类型", "官网", "备注",
    "模型发布时间", "记录创建时间", "是否新增", "核实情况",
]


# ============================================================
#  七、推理阈值（用于自动分类和备注生成）
# ============================================================

# 模型类型推理
PARAM_THRESHOLD_FOUNDATION = 50_000_000_000     # >= 50B → 基座
PARAM_THRESHOLD_DOMAIN = 1_000_000_000          # >= 1B → 领域（否则微调）

# 推理能力判定
REASONING_INDEX_THRESHOLD = 40                   # index_reasoning > 40 → thinking

# 备注生成阈值
GPQA_THRESHOLD_TOP = 90        # GPQA >= 90 → "顶级"
GPQA_THRESHOLD_STRONG = 80     # GPQA >= 80 → "强"
SWE_THRESHOLD_TOP = 70         # SWE-bench >= 70 → "顶级"
SWE_THRESHOLD_STRONG = 50      # SWE-bench >= 50 → "强"
PRICE_THRESHOLD_LOW = 1        # 价格 <= 1 → "低成本"
PRICE_THRESHOLD_HIGH = 20      # 价格 >= 20 → "高端"
CONTEXT_THRESHOLD_NOTABLE = 100_000  # 上下文 >= 100k 才提及

# 文本截断
SUMMARY_MAX_LENGTH = 150       # 全文简介截断字符数
FILENAME_MAX_LENGTH = 80       # TXT 文件名最大字符数


# ============================================================
#  八、钉钉配置
# ============================================================

DINGTALK_MAX_LENGTH = 18000    # 钉钉 Markdown 最大长度
DINGTALK_REPORT_TITLE = "AI 模型追踪日报"
DINGTALK_DATA_SOURCE_TEXT = "llm-stats.com · 腾讯研究院 · HuggingFace"


# ============================================================
#  九、排行榜配置（extract_llmstats_json.py）
# ============================================================

TOP_N_OPEN_SOURCE = 20         # Top N 开源模型
TOP_N_COMPANIES = 25           # Top N 公司
TOP_N_MULTIMODAL = 30          # Top N 多模态每子类
TOP_N_CROSS_CATEGORY = 20     # Top N 跨类别公司
RECENT_MONTHS_BACK = 3         # 最近模型筛选月数


# ============================================================
#  十、显示 / UI 参数
# ============================================================

PROGRESS_BAR_WIDTH = 30        # 流水线进度条宽度
QUALITY_BAR_WIDTH = 20         # 数据质量汇总进度条宽度
DIFF_LIST_TRUNCATE = 20        # 新增模型列表截断数


# ============================================================
#  便捷别名：cfg 对象（供 `from config import cfg` 使用）
# ============================================================

class _Cfg:
    """将本模块所有顶层变量暴露为属性，方便 IDE 补全。"""
    def __getattr__(self, name):
        mod = __import__(__name__)
        if hasattr(mod, name):
            return getattr(mod, name)
        raise AttributeError(f"config has no attribute '{name}'")

cfg = _Cfg()
