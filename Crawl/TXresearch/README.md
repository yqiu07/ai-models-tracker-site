# 搜狐号「腾讯研究院」文章爬虫

## 项目目标

从搜狐号"腾讯研究院"主页批量爬取文章列表，整理为结构化表格（CSV + Excel）。

## 文件结构

```
TXresearch/
├── README.md                    # 本文件 - 项目说明
├── crawl_sohu.py                # 爬虫主程序
├── Case                         # 页面 HTML 样本（用于分析/调试页面结构）
├── 腾讯研究院文章列表.csv        # 输出 - CSV 格式
└── 腾讯研究院文章列表.xlsx       # 输出 - Excel 格式（带样式美化）
```

## 技术方案

**Selenium 浏览器自动化**：搜狐号主页是懒加载页面，文章列表通过 JavaScript 异步渲染，无法直接 HTTP 请求获取。

### 工作流程

1. 启动 Chrome 浏览器，打开腾讯研究院搜狐号主页
2. 模拟滚动触发懒加载，持续加载更多文章
3. 每次滚动后解析页面中的文章卡片，提取字段
4. 达到目标数量（默认 100 篇）或遇到停止关键词时结束
5. 导出为 CSV 和 Excel（蓝色表头、斑马纹、链接可点击、冻结首行）

### 页面结构（两种文章卡片）

| 卡片类型 | CSS 类名 | 说明 |
|---------|---------|------|
| 纯文本卡片 | `TPLTextFeedItem` | 仅标题+摘要，如"AI速递"系列 |
| 图文卡片 | `TPLImageTextFeedItem` | 左图右文，如研究报告、调研文章 |

两种卡片的内部字段选择器一致：
- 标题：`.item-text-content-title`
- 摘要：`.item-text-content-description`
- 时间/阅读/评论：`.extra-info-item`

### 输出字段

| 字段 | 说明 |
|------|------|
| 序号 | 自增编号 |
| 标题 | 文章标题 |
| 简介 | 文章摘要/描述 |
| 链接 | 文章完整 URL |
| 发布时间 | 相对时间（如"14小时前"、"昨天17:41"） |
| 阅读数 | 如"145阅读" |
| 评论数 | 如"0评论" |

## 使用方法

### 依赖安装

```bash
pip install selenium pandas openpyxl
```

还需要本地安装 Chrome 浏览器（ChromeDriver 会自动匹配）。

### 运行

```bash
python crawl_sohu.py
```

### 配置项（在 crawl_sohu.py 顶部）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TARGET_URL` | 腾讯研究院主页 | 目标搜狐号主页 URL |
| `MIN_ARTICLES` | 100 | 最少抓取文章数 |
| `STOP_KEYWORD` | "AI速递 20260301" | 遇到此关键词停止（备选条件） |
| `MAX_SCROLL_RETRIES` | 15 | 连续无新文章时的最大重试次数 |
| `SCROLL_PAUSE_SECONDS` | 2.5 | 每次滚动后等待秒数 |

## Case 文件说明

`Case` 文件保存了搜狐号主页的实际 HTML 源码片段，用于：
- 分析页面 DOM 结构，确定 CSS 选择器
- 当页面结构变化时，对比新旧 HTML 定位问题
- 作为 AI 辅助调试的参考样本

## 常见问题

**Q: 只抓到了"AI速递"类文章，其他文章没有？**
A: 检查 `extract_articles` 中的 CSS 选择器是否同时包含 `TPLTextFeedItem` 和 `TPLImageTextFeedItem`。

**Q: Excel 文件没有更新？**
A: 确保 Excel 文件未被其他程序打开（文件被占用时 Python 无法写入）。
