# AI-Sub

[English](README_EN.md) | 中文

自动监控 AI/ML 产品发布和技术博客，通过 LLM 智能分类后推送到 Telegram 和飞书。

## 功能特性

- **多源数据采集** — 从 [releasebot.io](https://releasebot.io)、RSS 订阅（91+ feeds）和 Sitemap 三种渠道并发抓取
- **LLM 智能过滤** — 基于 OpenAI 判断相关性、重要性分级（HIGH / MEDIUM / LOW），自动归类并翻译为中文
- **Vendor 分层** — T0 核心厂商（OpenAI、Anthropic、Google 等）全量推送，T1/T2 按重要性逐级过滤
- **双通道通知** — Telegram（Forum Topics 分区路由）+ 飞书（Interactive Card）
- **每日摘要** — 自动汇总当日更新，按 vendor / blog 分组推送
- **去重 & 自清理** — SQLite 去重，每周自动清除 30 天前的数据

## 架构概览

```
数据源                      处理管线                     通知渠道
┌──────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│ releasebot   │───▶│ 去重 → LLM 分类     │───▶│ Telegram Topics  │
│ RSS/OPML     │───▶│ → 存储 → 通知路由   │───▶│ 飞书 Webhook     │
│ Sitemap      │───▶│ → 每日摘要          │    └──────────────────┘
└──────────────┘    └─────────────────────┘
```

**数据流：** Fetch → Deduplicate → LLM Filter → SQLite Store → Notify → Daily Digest

## 快速开始

### 前提条件

- Python 3.11+ 或 Docker
- OpenAI API Key（用于 LLM 分类）
- Telegram Bot Token 或 飞书 Webhook URL（至少一个通知渠道）

### Docker 部署（推荐）

1. 克隆仓库并创建配置：

```bash
git clone https://github.com/your-repo/ai-sub.git
cd ai-sub
cp .env.example .env  # 编辑 .env 填入 API Key 和通知配置
```

2. 启动服务：

```bash
docker-compose up -d
docker-compose logs -f ai-sub
```

### 本地开发

```bash
pip install -e .
# 编辑 .env 文件
ai-sub
```

## 配置说明

所有配置通过环境变量管理，支持 `.env` 文件。

### 核心配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | 必填 |
| `OPENAI_MODEL` | 分类使用的模型 | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | 自定义 API 端点 | — |
| `DB_PATH` | SQLite 数据库路径 | `data/releases.db` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

### Telegram 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TELEGRAM_ENABLED` | 启用 Telegram 通知 | `true` |
| `TELEGRAM_BOT_TOKEN` | Bot API Token | — |
| `TELEGRAM_CHAT_ID` | 目标群组 / Forum ID | — |

### 飞书配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FEISHU_ENABLED` | 启用飞书通知 | `true` |
| `FEISHU_RELEASE_WEBHOOK_URL` | Release 通知 Webhook | — |
| `FEISHU_BLOG_WEBHOOK_URL` | Blog 通知 Webhook | — |

### 调度配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `RELEASE_FETCH_INTERVAL_MINUTES` | Release 抓取间隔 | `30` |
| `BLOG_FETCH_INTERVAL_MINUTES` | Blog 抓取间隔 | `60` |
| `SITEMAP_FETCH_INTERVAL_MINUTES` | Sitemap 抓取间隔 | `120` |
| `RELEASE_DIGEST_HOUR_UTC` | Release 摘要时间 (UTC) | `1` |
| `BLOG_DIGEST_HOUR_UTC` | Blog 摘要时间 (UTC) | `2` |

### Vendor 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VENDORS_T0` | T0 核心厂商列表 | `["openai","anthropic","google"]` |
| `VENDORS_T1` | T1 重要产品列表 | `["xai","meta","deepseek",...]` |
| `VENDORS_T2` | T2 生态厂商列表 | `["vercel"]` |

## Vendor 分层体系

通知规则按 vendor 层级递减：

| 层级 | 推送规则 | 代表厂商 |
|------|----------|----------|
| **T0** 核心 | HIGH + MEDIUM + LOW | OpenAI, Anthropic, Google, Meta, DeepSeek, xAI, Mistral, Qwen |
| **T1** 重要 | HIGH + MEDIUM | Cursor, Microsoft, Midjourney, Perplexity, Databricks 等 |
| **T2** 生态 | 仅 HIGH | Vercel, GitHub, Amazon, Cloudflare 等 |

完整列表见 [docs/vendors.md](docs/vendors.md)。

## 三条数据管线

### 1. Release 管线

**数据源：** releasebot.io API（按 vendor 抓取）
**流程：** 抓取 → 去重 → LLM 分类（相关性 + 重要性 + 中文翻译） → 按 tier 过滤通知 → 每日摘要

### 2. Blog 管线

**数据源：** 91+ RSS feeds（通过 `config/blogs.opml` 配置）
**流程：** OPML 解析 → 并发 RSS 抓取（semaphore=10） → 去重 → LLM 判断 AI 编程相关性 → 通知 HIGH/MEDIUM → 每日摘要

### 3. Sitemap 管线

**数据源：** 5 个 sitemap 源（通过 `config/sitemaps.yaml` 配置）
**流程：** Sitemap XML 解析 → 路径前缀过滤 → HTML 元数据抓取（semaphore=5） → 复用 Blog/Release 分类管线

## Telegram 通知

消息按来源和重要性路由到 Forum Topics：

| Topic | 颜色 | 内容 |
|-------|------|------|
| AI新闻 - 重要 | 🔴 | HIGH 级别的 Release |
| AI新闻 - 关注 | 🔵 | MEDIUM 级别的 Release |
| AI新闻 - 了解 | 🟢 | LOW 级别的 Release |
| AI新闻 - 每日摘要 | 🟡 | 每日 Release 汇总 |
| AI博客 - 重要 | 🔴 | HIGH 级别的 Blog |
| AI博客 - 关注 | 🔵 | MEDIUM 级别的 Blog |
| AI博客 - 每日摘要 | 🟣 | 每日 Blog 精选 |

## 调度任务

| 任务 | 触发方式 | 频率 |
|------|----------|------|
| Release 抓取 | Interval | 每 30 分钟 |
| Blog 抓取 | Interval | 每 60 分钟 |
| Sitemap 抓取 | Interval | 每 120 分钟（可按源配置） |
| Release 摘要 | Cron | 每天 1:00 UTC |
| Blog 摘要 | Cron | 每天 2:00 UTC |
| 数据清理 | Cron | 每周日 3:00 UTC |

## 手动触发摘要

```bash
python scripts/send_digest.py                # 发送所有摘要
python scripts/send_digest.py --release      # 仅 Release
python scripts/send_digest.py --blog         # 仅 Blog
python scripts/send_digest.py --hours 48     # 自定义时间范围
python scripts/send_digest.py --dry-run      # 预览模式
```

## 项目结构

```
src/ai_sub/
├── main.py                 # 入口，信号处理，启动 scheduler
├── config.py               # pydantic-settings 配置
├── models.py               # 数据模型
├── scheduler.py            # APScheduler 任务编排
├── fetcher/
│   ├── releasebot.py       # releasebot.io 数据抓取
│   ├── blog.py             # OPML + RSS feed 抓取
│   └── sitemap.py          # Sitemap XML 解析 + HTML 抓取
├── filter_release.py       # Release LLM 分类
├── filter_blog.py          # Blog LLM 分类
├── store_release.py        # Release SQLite 存储
├── store_blog.py           # Blog SQLite 存储
├── digest_release.py       # Release 摘要格式化
├── digest_blog.py          # Blog 摘要格式化
└── notifier/
    ├── __init__.py          # 通知路由
    ├── telegram.py          # Telegram Bot API
    ├── telegram_topics.py   # Forum Topics 管理
    └── feishu.py            # 飞书 Interactive Card
config/
├── blogs.opml              # RSS 订阅源
└── sitemaps.yaml           # Sitemap 订阅源
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ (async) |
| HTTP | httpx (async) |
| LLM | OpenAI API |
| 数据校验 | Pydantic v2 |
| 配置 | pydantic-settings (.env) |
| 调度 | APScheduler 3.x |
| Feed 解析 | feedparser |
| 数据库 | SQLite |
| 部署 | Docker + Docker Compose |

## License

[Apache License 2.0](LICENSE)
