# AI-Sub

English | [中文](README.md)

Automated monitoring service for AI/ML product releases and tech blogs — powered by LLM-based intelligent filtering, with notifications delivered to Telegram and Feishu (Lark).

## Features

- **Multi-Source Ingestion** — Concurrent fetching from [releasebot.io](https://releasebot.io), RSS feeds (91+ sources), and Sitemaps
- **LLM-Powered Filtering** — OpenAI-based relevance scoring, importance classification (HIGH / MEDIUM / LOW), auto-categorization, and Chinese translation
- **Vendor Tiering** — T0 core vendors (OpenAI, Anthropic, Google, etc.) get full coverage; T1/T2 filtered by importance
- **Dual Notification Channels** — Telegram (Forum Topics routing) + Feishu (Interactive Card)
- **Daily Digests** — Automated daily summaries grouped by vendor / blog
- **Dedup & Auto-Cleanup** — SQLite-based deduplication with weekly purge of 30-day-old data

## Architecture

```
Data Sources                Pipeline                      Notifications
┌──────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│ releasebot   │───▶│ Dedup → LLM Filter  │───▶│ Telegram Topics  │
│ RSS/OPML     │───▶│ → Store → Route     │───▶│ Feishu Webhook   │
│ Sitemap      │───▶│ → Daily Digest      │    └──────────────────┘
└──────────────┘    └─────────────────────┘
```

**Data Flow:** Fetch → Deduplicate → LLM Filter → SQLite Store → Notify → Daily Digest

## Quick Start

### Prerequisites

- Python 3.11+ or Docker
- OpenAI API Key (for LLM classification)
- Telegram Bot Token or Feishu Webhook URL (at least one notification channel)

### Docker Deployment (Recommended)

1. Clone the repo and configure:

```bash
git clone https://github.com/your-repo/ai-sub.git
cd ai-sub
cp .env.example .env  # Edit .env with your API keys and notification settings
```

2. Start the service:

```bash
docker-compose up -d
docker-compose logs -f ai-sub
```

### Local Development

```bash
pip install -e .
# Edit .env file
ai-sub
```

## Configuration

All settings are managed via environment variables, with `.env` file support.

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | Model for classification | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | Custom API endpoint | — |
| `DB_PATH` | SQLite database path | `data/releases.db` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Telegram Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_ENABLED` | Enable Telegram notifications | `true` |
| `TELEGRAM_BOT_TOKEN` | Bot API token | — |
| `TELEGRAM_CHAT_ID` | Target group / forum ID | — |

### Feishu Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `FEISHU_ENABLED` | Enable Feishu notifications | `true` |
| `FEISHU_RELEASE_WEBHOOK_URL` | Release notification webhook | — |
| `FEISHU_BLOG_WEBHOOK_URL` | Blog notification webhook | — |

### Scheduling Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `RELEASE_FETCH_INTERVAL_MINUTES` | Release fetch interval | `30` |
| `BLOG_FETCH_INTERVAL_MINUTES` | Blog fetch interval | `60` |
| `SITEMAP_FETCH_INTERVAL_MINUTES` | Sitemap fetch interval | `120` |
| `RELEASE_DIGEST_HOUR_UTC` | Release digest hour (UTC) | `1` |
| `BLOG_DIGEST_HOUR_UTC` | Blog digest hour (UTC) | `2` |

### Vendor Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `VENDORS_T0` | T0 core vendor list | `["openai","anthropic","google"]` |
| `VENDORS_T1` | T1 important product list | `["xai","meta","deepseek",...]` |
| `VENDORS_T2` | T2 ecosystem vendor list | `["vercel"]` |

## Vendor Tier System

Notification rules decrease by tier:

| Tier | Notification Rule | Representative Vendors |
|------|-------------------|------------------------|
| **T0** Core | HIGH + MEDIUM + LOW | OpenAI, Anthropic, Google, Meta, DeepSeek, xAI, Mistral, Qwen |
| **T1** Important | HIGH + MEDIUM | Cursor, Microsoft, Midjourney, Perplexity, Databricks, etc. |
| **T2** Ecosystem | HIGH only | Vercel, GitHub, Amazon, Cloudflare, etc. |

See [docs/vendors.md](docs/vendors.md) for the full list.

## Three Data Pipelines

### 1. Release Pipeline

**Source:** releasebot.io API (per-vendor fetching)
**Flow:** Fetch → Dedup → LLM classify (relevance + importance + Chinese translation) → Tier-based notification → Daily digest

### 2. Blog Pipeline

**Source:** 91+ RSS feeds (configured via `config/blogs.opml`)
**Flow:** OPML parse → Concurrent RSS fetch (semaphore=10) → Dedup → LLM classify AI/programming relevance → Notify HIGH/MEDIUM → Daily digest

### 3. Sitemap Pipeline

**Source:** 5 sitemap sources (configured via `config/sitemaps.yaml`)
**Flow:** Sitemap XML parse → Path prefix filter → HTML metadata extraction (semaphore=5) → Reuses Blog/Release classification pipeline

## Telegram Notifications

Messages are routed to Forum Topics by source and importance:

| Topic | Color | Content |
|-------|-------|---------|
| AI News - Important | Red | HIGH-level releases |
| AI News - Notable | Blue | MEDIUM-level releases |
| AI News - FYI | Green | LOW-level releases |
| AI News - Daily Digest | Yellow | Daily release summary |
| AI Blog - Important | Red | HIGH-level blogs |
| AI Blog - Notable | Blue | MEDIUM-level blogs |
| AI Blog - Daily Digest | Purple | Daily blog highlights |

## Scheduled Tasks

| Task | Trigger | Frequency |
|------|---------|-----------|
| Release fetch | Interval | Every 30 minutes |
| Blog fetch | Interval | Every 60 minutes |
| Sitemap fetch | Interval | Every 120 minutes (per-source override) |
| Release digest | Cron | Daily at 1:00 UTC |
| Blog digest | Cron | Daily at 2:00 UTC |
| Data cleanup | Cron | Every Sunday at 3:00 UTC |

## Manual Digest

```bash
python scripts/send_digest.py                # Send all digests
python scripts/send_digest.py --release      # Release only
python scripts/send_digest.py --blog         # Blog only
python scripts/send_digest.py --hours 48     # Custom time range
python scripts/send_digest.py --dry-run      # Preview mode
```

## Project Structure

```
src/ai_sub/
├── main.py                 # Entry point, signal handling, scheduler startup
├── config.py               # pydantic-settings configuration
├── models.py               # Data models
├── scheduler.py            # APScheduler task orchestration
├── fetcher/
│   ├── releasebot.py       # releasebot.io data fetching
│   ├── blog.py             # OPML + RSS feed fetching
│   └── sitemap.py          # Sitemap XML parsing + HTML fetching
├── filter_release.py       # Release LLM classification
├── filter_blog.py          # Blog LLM classification
├── store_release.py        # Release SQLite storage
├── store_blog.py           # Blog SQLite storage
├── digest_release.py       # Release digest formatting
├── digest_blog.py          # Blog digest formatting
└── notifier/
    ├── __init__.py          # Notification routing
    ├── telegram.py          # Telegram Bot API
    ├── telegram_topics.py   # Forum Topics management
    └── feishu.py            # Feishu Interactive Card
config/
├── blogs.opml              # RSS feed subscriptions
└── sitemaps.yaml           # Sitemap subscriptions
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ (async) |
| HTTP | httpx (async) |
| LLM | OpenAI API |
| Validation | Pydantic v2 |
| Configuration | pydantic-settings (.env) |
| Scheduling | APScheduler 3.x |
| Feed Parsing | feedparser |
| Database | SQLite |
| Deployment | Docker + Docker Compose |

## License

[Apache License 2.0](LICENSE)
