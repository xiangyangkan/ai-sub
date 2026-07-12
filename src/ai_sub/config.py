from datetime import datetime, timezone

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM provider: "openai" or "anthropic"
    llm_provider: str = "anthropic"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_base_url: str | None = None

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_base_url: str | None = None

    # Telegram (shared)
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_topics_path: str = "data/telegram_topics.json"

    # Feishu (shared)
    feishu_enabled: bool = True

    # Database (shared)
    db_path: str = "data/releases.db"

    # ── Backfill (shared) ──
    # Backfill is fully opt-in and OFF by default: when disabled, every fetcher
    # behaves exactly as before (latest N per source via the count limits below).
    # When enabled, fetchers instead pull ALL items published on/after
    # `backfill_since`. SQLite dedup skips already-seen items, so no
    # re-notification happens. After the initial backfill you can turn it back
    # off to save work.
    backfill_enabled: bool = False
    # ISO date cutoff, used only when backfill is enabled (e.g. "2026-06-01").
    backfill_since: str = "2026-06-01"
    # Safety cap: max items a single source will backfill per cycle (guards
    # against very large sitemaps / feeds).
    backfill_max_items: int = 500

    # ── Release 数据源 ──
    release_enabled: bool = True
    release_fetch_interval_minutes: int = 30
    release_digest_hour_utc: int = 1  # 9 AM Beijing = 1 AM UTC
    max_releases_per_vendor: int = 1

    # Release 通知频道
    feishu_release_webhook_url: str = ""

    # Vendors to monitor, grouped by tier
    # t0: push all (high/medium/low)
    # t1: push high + medium
    # t2: push high only
    vendors_t0: list[str] = ["openai", "anthropic", "google", "codex", "openclaw"]
    vendors_t1: list[str] = ["xai", "meta", "deepseek", "qwen", "kimi", "minimax", "zai", "volcengine", "cursor", "eleven-labs", "huggingface"]
    vendors_t2: list[str] = ["vercel"]

    # ── Sitemap 数据源 ──
    sitemap_enabled: bool = True
    sitemap_config_path: str = "config/sitemaps.yaml"
    sitemap_fetch_interval_minutes: int = 120

    # ── Blog 数据源 ──
    blog_enabled: bool = True
    blog_opml_path: str = "config/blogs.opml"
    blog_fetch_interval_minutes: int = 60
    blog_max_articles_per_feed: int = 1
    blog_digest_hour_utc: int = 2  # 10 AM Beijing = 2 AM UTC

    # Blog 通知频道
    feishu_blog_webhook_url: str = ""

    # ── YouTube 数据源 ──
    youtube_enabled: bool = True
    youtube_channels_path: str = "config/youtube_channels.yaml"
    youtube_fetch_interval_minutes: int = 120
    youtube_max_videos_per_channel: int = 3
    youtube_digest_hour_utc: int = 3  # 11 AM Beijing = 3 AM UTC

    # YouTube Whisper fallback (when subtitles are disabled)
    youtube_whisper_fallback: bool = False
    whisper_model: str = "whisper-1"

    # YouTube proxy (Webshare residential rotating proxy)
    youtube_proxy_username: str = ""
    youtube_proxy_password: str = ""

    # YouTube 通知频道
    feishu_youtube_webhook_url: str = ""

    # Card image generation
    card_image_enabled: bool = True

    log_level: str = "INFO"

    @property
    def backfill_cutoff(self) -> datetime | None:
        """Parsed `backfill_since`, or None when backfill is off/misconfigured.

        Returns None unless backfill is explicitly enabled AND the date parses,
        so every fetcher falls back to its original count-limited behavior.
        """
        if not self.backfill_enabled or not self.backfill_since:
            return None
        try:
            dt = datetime.fromisoformat(self.backfill_since)
        except ValueError:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    @property
    def all_vendors(self) -> list[str]:
        return self.vendors_t0 + self.vendors_t1 + self.vendors_t2

    def vendor_tier(self, vendor: str) -> str:
        if vendor in self.vendors_t0:
            return "t0"
        if vendor in self.vendors_t1:
            return "t1"
        return "t2"


settings = Settings()
