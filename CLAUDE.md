# CLAUDE.md

## Project Overview

AI-Sub is an async Python service that monitors AI/ML product releases and tech blogs, classifies them via LLM, and pushes notifications to Telegram (Forum Topics) and Feishu (Interactive Card). It runs four parallel data pipelines: Release (releasebot.io), Blog (RSS/OPML), Sitemap (XML + HTML scraping), and YouTube (channel RSS + transcript summarization).

## Quick Reference

```bash
# Install locally
pip install -e .

# Run the service
ai-sub
# or: python -m ai_sub.main

# Docker
docker-compose up -d
docker-compose logs -f ai-sub

# Manual digest
python scripts/send_digest.py --dry-run      # Preview
python scripts/send_digest.py --release      # Release digest only
python scripts/send_digest.py --blog         # Blog digest only
```

## Project Structure

```
src/ai_sub/
├── main.py              # Entry point, signal handling, logging setup
├── config.py            # pydantic-settings, vendor tier logic (T0/T1/T2)
├── models.py            # Pydantic models: ReleaseItem, FilteredRelease, BlogArticle, FilteredBlogArticle, YouTubeVideo, FilteredYouTubeVideo
├── scheduler.py         # APScheduler job orchestration (fetch, notify, digest, cleanup)
├── filter_release.py    # LLM classification for releases (relevance, importance, zh translation)
├── filter_blog.py       # LLM classification for blogs (AI relevance, category)
├── filter_youtube.py    # Two-step LLM: classify relevance + summarize transcript
├── store_release.py     # SQLite CRUD for releases
├── store_blog.py        # SQLite CRUD for blog articles
├── store_youtube.py     # SQLite CRUD for YouTube videos
├── digest_release.py    # Daily release digest formatting
├── digest_blog.py       # Daily blog digest formatting
├── digest_youtube.py    # Daily YouTube video digest formatting
├── fetcher/
│   ├── releasebot.py    # releasebot.io API (SvelteKit data decompression)
│   ├── blog.py          # OPML parsing + concurrent RSS fetching (semaphore=10)
│   ├── sitemap.py       # Sitemap XML parsing + HTML metadata scraping (semaphore=5)
│   └── youtube.py       # YouTube channel RSS + transcript fetching (youtube-transcript-api)
└── notifier/
    ├── __init__.py      # notify_all() / notify_blog() / notify_youtube() routing
    ├── telegram.py      # Telegram Bot API, HTML formatting, message splitting
    ├── telegram_topics.py  # Forum Topics creation and caching
    └── feishu.py        # Feishu webhook, Interactive Card builder
config/
├── blogs.opml           # 91+ RSS feed sources
├── sitemaps.yaml        # Sitemap sources with prefix filters and intervals
└── youtube_channels.yaml # YouTube channel subscriptions (channel_id + category)
```

## Architecture & Data Flow

**Pipeline:** Fetch → Deduplicate (SQLite source_id) → LLM Classify → Store → Notify → Daily Digest

Four pipelines share the same pattern:
1. **Release pipeline** (`scheduler.py:fetch_and_notify`): releasebot.io → `filter_release.classify_and_translate` → `store_release` → `notifier.notify_all`
2. **Blog pipeline** (`scheduler.py:fetch_and_notify_blogs`): OPML/RSS → `filter_blog.classify_blog_article` → `store_blog` → `notifier.notify_blog`
3. **Sitemap pipeline** (`scheduler.py:fetch_and_notify_sitemaps`): sitemap XML → routes to blog or release pipeline via `notify_as` field
4. **YouTube pipeline** (`scheduler.py:fetch_and_notify_youtube`): channel RSS → transcript fetch → two-step LLM (classify + summarize) → `store_youtube` → `notifier.notify_youtube`

### Vendor Tier System (`config.py`)

- **T0** (core): All importance levels pushed (openai, anthropic, google, meta, deepseek, xai, mistral, qwen, minimax, zai)
- **T1** (important): HIGH + MEDIUM only (cursor, microsoft, perplexity, etc.)
- **T2** (ecosystem): HIGH only (vercel, github, amazon, etc.)

Use `settings.vendor_tier(vendor)` to get the tier.

### Telegram Topic Routing

Messages route to 10 Forum Topics by source type (release/blog/youtube) and importance level (HIGH/MEDIUM/LOW/digest). Topic IDs are cached in `data/telegram_topics.json`.

## Key Conventions

- **Async-first**: All I/O uses `async/await` with `httpx.AsyncClient`. Concurrency via `asyncio.Semaphore`.
- **Pydantic v2**: All data models and settings use Pydantic v2. Config via `pydantic-settings` with `.env` support.
- **SQLite dedup**: `source_id` is the primary key for deduplication. Format: `{vendor}:{release_id}` for releases, `blog:{slug}:{entry_hash}` for blogs, `yt:{channel_slug}:{video_id}` for YouTube.
- **LLM prompts**: System prompts are inline strings in `filter_release.py`, `filter_blog.py`, and `filter_youtube.py`. They return structured JSON via `response_format`.
- **Notification formatting**: Telegram uses HTML format. Feishu uses Interactive Card JSON.
- **Scheduling**: APScheduler 3.x (not 4.x). Interval jobs for fetching, cron jobs for digests.
- **No test framework configured**: Project currently has no tests directory or test configuration.

## Environment Variables

Required: `OPENAI_API_KEY` plus at least one notification channel (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, or `FEISHU_*_WEBHOOK_URL`).

Key optional settings:
- `OPENAI_MODEL` (default: `gpt-4o-mini`), `OPENAI_BASE_URL` (custom endpoint)
- `DB_PATH` (default: `data/releases.db`), `LOG_LEVEL` (default: `INFO`)
- `RELEASE_ENABLED`, `BLOG_ENABLED`, `SITEMAP_ENABLED`, `YOUTUBE_ENABLED` — toggle individual pipelines
- `*_FETCH_INTERVAL_MINUTES` — per-pipeline fetch frequency
- `VENDORS_T0`, `VENDORS_T1`, `VENDORS_T2` — JSON arrays for tier membership

Full config defined in `src/ai_sub/config.py:Settings`.

## Database

SQLite at `data/releases.db` with three tables:
- `seen_releases`: source_id (PK), vendor, release metadata, LLM results, timestamps
- `seen_blog_articles`: source_id (PK), blog metadata, LLM results, notify_as field, timestamps
- `seen_youtube_videos`: source_id (PK), video metadata, LLM results (summary, key_points, timeline), timestamps

Weekly cleanup removes entries older than 30 days (Sunday 3:00 UTC).

## Common Tasks

**Adding a new vendor**: Update `VENDORS_T0`/`T1`/`T2` in `.env` or the defaults in `config.py`.

**Adding a new RSS feed**: Edit `config/blogs.opml` — add an `<outline>` element with `xmlUrl` attribute.

**Adding a new sitemap source**: Edit `config/sitemaps.yaml` — add entry with `url`, `prefix`, `interval_minutes`, `max_articles`, and optional `notify_as`.

**Adding a YouTube channel**: Edit `config/youtube_channels.yaml` — add entry with `name`, `channel_id`, and `category`.

**Modifying LLM classification**: Edit the system prompt in `filter_release.py`, `filter_blog.py`, or `filter_youtube.py`. The prompt defines the JSON response schema.

**Adding a new notification channel**: Create a new module in `src/ai_sub/notifier/`, then integrate it in `notifier/__init__.py`'s `notify_all()`, `notify_blog()`, and `notify_youtube()` functions.
