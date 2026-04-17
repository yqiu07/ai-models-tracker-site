"""
基于AI逐篇阅读文章后提取的新兴模型，与Object-Models对比，生成结果表格。
提取标准（参考Taxonomy.xlsx）：
- 具体的模型名称（基座/领域/微调/多模态/智能体/集成产品）
- 新发布的版本号模型
- 新发布的产品/智能体平台
排除：纯硬件、纯算法论文、纯商业事件、纯功能更新、benchmark/评测工具
"""
import pandas as pd
import re

# ============================================================
# AI逐篇阅读后提取的新兴模型
# ============================================================
ARTICLE_MODELS = {
    1: [  # 20260416 - 阅读全文后提取
        "Claude Opus 4.7",                          # Anthropic旗舰模型，本周上线
        "GPT-5.4-Cyber",                             # OpenAI面向网络安全的微调模型
        "Spark 2.0 (World Labs)",                    # 李飞飞团队开源3D渲染引擎/世界模型
        "Gemini Robotics-ER 1.6",                    # 谷歌具身机器人模型
        "Meoo/秒悟 (阿里ATH)",                       # 阿里AI开发工具，集成多模型
        "Gemini Skills (Chrome)",                    # 谷歌浏览器内置智能体技能
        "Ising (英伟达)",                             # 全球首个开源量子AI模型系列
    ],
    3: [  # 20260415
        "Lantay (面壁智能)",                          # 文档智能体工作台
        "Seedance 2.0 API (火山引擎)",               # 视频生成模型API开放
        "Being-H 0.7 (智在无界)",                    # 具身世界模型，全球评测第一
        "Spud (OpenAI)",                             # OpenAI新模型代号，备忘录透露
    ],
    5: [  # 20260414
        "MiniMax M2.7",                              # MiniMax开源自进化模型
        "Vidu Q3",                                   # 视频生成模型升级
        "YOYO Claw (荣耀)",                          # 荣耀端侧智能体
        "XChat (马斯克/X Corp.)",                    # 集成Grok AI的社交应用
        "HY-Embodied-0.5 (腾讯混元)",               # 腾讯具身基础模型
    ],
    7: [  # 20260413
        "Hermes Agent (Nous Research)",              # 开源Agent，内置学习循环
        "GBrain (YC CEO开源)",                       # AI Agent第二大脑系统
        "MiniMax Music 2.6",                         # MiniMax音乐生成模型
        "Music Skill (MiniMax)",                     # MiniMax Agent音乐技能
        "JoyAI-Image-Edit (京东)",                   # 京东开源240B图像编辑模型
        "Psi-R2 (灵初智能)",                         # 策略模型，登顶MolmoSpaces
        "Psi-W0 (灵初智能)",                         # 世界模型
        "Revo 3 (强脑科技)",                         # 灵巧手硬件+算法（具身智能）
    ],
    9: [  # 20260410
        "Muse Spark (Meta MSL)",                     # Meta超级智能实验室首个模型
        "Claude Managed Agents (Anthropic)",         # Anthropic全托管智能体平台
        "MMX-CLI (MiniMax)",                         # MiniMax Agent命令行工具
        "Marble 1.1 (World Labs)",                   # 世界模型
        "Marble 1.1-Plus (World Labs)",              # 世界模型增强版
        "Seeduplex (字节)",                          # 全双工语音大模型
        "QClaw V2 (腾讯)",                           # 腾讯智能体V2版本
        "HY-Embodied-0.5 (腾讯混元)",               # 腾讯具身模型（重复提及）
    ],
    12: [  # 20260409
        "Claude Mythos Preview (Anthropic)",         # 安全漏洞发现模型
        "GLM-5.1 (智谱)",                            # 智谱开源旗舰，支持8小时长程任务
        "DeepSeek V4 (疑似准备中)",                  # 前端代码暗示V4即将发布
        "HappyHorse-1.0",                            # 匿名视频模型登顶Video Arena
        "PixVerse C1 (爱诗科技)",                    # 影视行业大模型
        "VoxCPM 2 (面壁智能)",                       # 开源语音模型，2B参数30国语言
        "QBotClaw (QQ浏览器)",                       # 浏览器内置AI智能体
        "MemPalace",                                 # 开源AI记忆系统，LongMemEval满分
        "DeepXiv (智源研究院)",                      # 2亿篇论文转化为Agent工具
    ],
    14: [  # 20260408
        "Codex (OpenAI)",                            # OpenAI编程助手加码
        "Sciverse (上海AI实验室)",                   # 100PB级科学智能数据库
    ],
    15: [  # 20260407
        "Gemma 4 (Google)",                          # Google开源模型系列
        "Gemma 4 E2B (Google)",                      # 2B参数手机可跑版本
        "Gemma 4 31B Dense (Google)",                # 31B稠密版
        "MAI-Transcribe-1 (微软)",                   # 微软自研语音转写模型
        "MAI-Voice-1 (微软)",                        # 微软自研语音生成模型
        "MAI-Image-2 (微软)",                        # 微软自研图像生成模型
        "GPT-Image-2 (OpenAI)",                      # OpenAI新一代图像模型
        "Cursor 3",                                  # 编辑器重构，多Agent并行
        "Composer 2 (Cursor)",                       # Cursor内置编程模型
    ],
    17: [  # 20260403
        "Conway (Anthropic)",                        # Anthropic Always-On智能体
        "GLM-5V-Turbo (智谱)",                       # 智谱多模态Coding基座模型
        "Qwen3.6-Plus (阿里)",                       # 阿里新模型，100万上下文
        "Step 3.5 Flash (阶跃星辰)",                 # 阶跃星辰优化版模型
        "LongCat-AudioDiT (美团)",                   # 美团开源语音克隆模型
        "CaP-X (英伟达)",                            # 英伟达开源机器人控制框架
        "Spud (OpenAI)",                             # OpenAI新基座模型代号
    ],
    19: [  # 20260402
        "Veo 3.1 Lite (Google DeepMind)",            # 谷歌视频生成模型，成本减半
        "Wan2.7-Image (阿里通义)",                   # 阿里图像生成模型
        "claw-code",                                 # Claude Code的Python开源复刻
    ],
    21: [  # 20260401
        "WorkBuddy 小程序 (腾讯)",                   # 腾讯AI助手微信小程序版
        "TRAE SOLO (字节)",                          # 字节双端智能体产品
        "JoyStreamer (京东)",                         # 京东数字人大模型
        "JoyStreamer-Flash (京东)",                   # 京东数字人轻量版
    ],
    24: [  # 20260331
        "EchoZ-1.0 (UniPat AI)",                     # 预测专用模型，排行榜第一
        "Qwen3.5-Omni (阿里)",                      # 阿里全模态模型，215项SOTA
        "PixVerse V6 (爱诗科技)",                    # 视频模型+实时世界模型R1
        "PixVerse R1 (爱诗科技)",                    # 实时世界模型
    ],
    26: [  # 20260330
        "Claude Mythos 5.0 (Anthropic)",             # Anthropic顶配模型内测
        "Gemini 3.1 Flash Live (Google)",            # 谷歌实时语音Agent模型
        "GLM-5.1 (智谱)",                            # 智谱模型正式上线
        "Multi-Shot App (Runway)",                   # Runway多镜头视频生成
        "GLM-5 Turbo (智谱)",                        # 智谱长程任务优化模型
    ],
    29: [  # 20260327
        "Lyria 3 Pro (Google)",                      # 谷歌AI音乐模型
        "AI Scientist (Sakana AI)",                  # 端到端自动化科研系统
    ],
    31: [  # 20260326
        "Office Skills (MiniMax)",                   # MiniMax开源文档引擎
        "Ψ₀ (南加州大学)",                           # 人形机器人基座模型
    ],
    35: [  # 20260324
        "GPT-5.4 (OpenAI)",                          # OpenClaw默认模型升级
        "MiniMax M2.7",                              # MiniMax升级并统一插件入口
        "StepClaw (阶跃星辰)",                       # 阶跃星辰龙虾智能体
        "Kimi Claw (月之暗面)",                      # 月之暗面龙虾智能体
        "OneClaw (月之暗面)",                        # 月之暗面本地部署方案
        "LobsterAI (网易有道)",                      # 网易有道龙虾智能体
        "AutoClaw (智谱)",                           # 智谱龙虾智能体
        "MaxClaw (MiniMax)",                         # MiniMax龙虾智能体
    ],
    37: [  # 20260323
        "Antigravity (Google/Windsurf)",             # 谷歌编码Agent（收购Windsurf）
        "Janus (Google)",                            # Gemini Mac桌面端代号
        "Cowork (Anthropic)",                        # Anthropic智能体协作产品
        "Dispatch (Anthropic)",                      # Anthropic远程Agent产品
        "Claude Code Channels (Anthropic)",          # Anthropic产品线扩展
        "ClawBot (微信)",                            # 微信官方龙虾插件
        "Kimi K2.5 (月之暗面)",                      # 被Cursor套壳的模型
    ],
    39: [  # 20260320
        "NemoClaw (英伟达)",                         # 英伟达开源Agent软件栈
        "Mamba-3 (CMU/普林斯顿)",                    # 新架构模型
        "MiMo-V2-Pro (小米)",                        # 小米旗舰模型，1T参数
        "EdgeClaw Box (面壁智能)",                   # 面壁智能本地Agent硬件+软件
        "StepClaw (阶跃星辰)",                       # 阶跃星辰桌面端智能体
        "Midjourney V8 Alpha",                       # Midjourney图像模型新版
    ],
    41: [  # 20260319
        "GPT-5.4 mini (OpenAI)",                     # OpenAI轻量模型
        "GPT-5.4 nano (OpenAI)",                     # OpenAI超轻量模型
        "Dispatch (Anthropic)",                      # Anthropic远程Agent
        "MiniMax M2.7",                              # MiniMax首个自进化模型
        "QClaw (腾讯)",                              # 腾讯智能体
        "LibTV (LiblibAI)",                          # AI视频创作平台
        "可灵 3.0 (快手)",                           # 快手视频模型
        "Kimi Linear (月之暗面)",                    # 月之暗面底层架构创新
        "MuonClip (月之暗面)",                       # 月之暗面开源优化器
    ],
}


def normalize(name):
    """标准化模型名称用于匹配"""
    n = name.lower().strip()
    n = re.sub(r'\s*[\(（].*?[\)）]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def load_existing_models():
    """加载Object-Models.xlsx中已追踪的模型名称"""
    df = pd.read_excel(r"D:\yuwang\action\Object-Models.xlsx")
    models = set()
    for name in df.iloc[:, 0].dropna():
        models.add(normalize(str(name)))
    return models


# 手动等价映射：文章中的名称在Object-Models中已有对应记录
KNOWN_TRACKED = {
    "minimax m2.7",          # MiniMax M2.5 系列已追踪
    "kimi k2.5",             # kimi-k2.5-thinking 已追踪
    "glm-5.1",               # GLM-5 系列已追踪
    "glm-5 turbo",           # GLM-5 系列已追踪
    "qwen3.5-397b-a17b",     # 已追踪
    "doubao-seed-2.0",       # 已追踪
    "autoclaw",              # 已追踪
    "codex",                 # Codex 已追踪
    "可灵 3.0",              # Kling 3.0 series 已追踪
    "seedance 2.0 api",      # Seedance 2.0 Pro 已追踪
    "qwen3.5-omni",          # qwen3.5系列已追踪
    "workbuddy 小程序",      # WorkBuddy 已追踪
}


def is_tracked(model_name, existing_models):
    """检查模型是否已被追踪"""
    n = normalize(model_name)
    if n in existing_models:
        return True
    if n in KNOWN_TRACKED:
        return True
    for existing in existing_models:
        if len(n) > 4 and len(existing) > 4:
            if n in existing or existing in n:
                return True
    return False


def main():
    existing = load_existing_models()
    print(f"已追踪模型数量: {len(existing)}")

    txcrawl_df = pd.read_excel(r"D:\yuwang\action\Extract\TXCrawl.xlsx")
    models_col = []
    new_col = []

    for _, row in txcrawl_df.iterrows():
        seq = int(row.iloc[0])
        models = ARTICLE_MODELS.get(seq, [])
        # 去除括号说明，只保留模型名
        display_models = [m.split(" (")[0] if " (" in m else m for m in models]
        models_str = "\n".join(models) if models else "无明确新模型"

        new_models = [m for m in models if not is_tracked(m, existing)]
        new_str = "\n".join(new_models) if new_models else "均已追踪"

        models_col.append(models_str)
        new_col.append(new_str)

    txcrawl_df["文章提及的新兴模型"] = models_col
    txcrawl_df["未追踪的新模型"] = new_col

    output_path = r"D:\yuwang\action\Extract\TXCrawl_result.xlsx"
    txcrawl_df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"\n结果已保存至: {output_path}")

    # 打印汇总
    print("\n" + "=" * 80)
    for _, row in txcrawl_df.iterrows():
        seq = int(row.iloc[0])
        title = row.iloc[1]
        m = row["文章提及的新兴模型"].replace("\n", " | ")
        n = row["未追踪的新模型"].replace("\n", " | ")
        print(f"\n[{seq}] {title}")
        print(f"  提及: {m}")
        print(f"  新增: {n}")

    # 去重汇总
    print("\n" + "=" * 80)
    print("所有未追踪的新模型（去重汇总）")
    print("=" * 80)
    all_new = {}
    for _, row in txcrawl_df.iterrows():
        ns = row["未追踪的新模型"]
        if ns != "均已追踪":
            for m in ns.split("\n"):
                core = normalize(m)
                if core not in all_new:
                    all_new[core] = m.strip()

    for i, (_, display) in enumerate(sorted(all_new.items()), 1):
        print(f"  {i}. {display}")
    print(f"\n共发现 {len(all_new)} 个未追踪的新模型/产品")


if __name__ == "__main__":
    main()
