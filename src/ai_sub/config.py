from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # OpenAI (shared)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None

    # Telegram (shared)
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_topics_path: str = "data/telegram_topics.json"

    # Feishu (shared)
    feishu_enabled: bool = True

    # Database (shared)
    db_path: str = "data/releases.db"

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
    vendors_t0: list[str] = ["openai", "anthropic", "google"]
    vendors_t1: list[str] = ["xai", "meta", "deepseek", "qwen", "minimax", "zai", "volcengine", "cursor"]
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

    log_level: str = "INFO"

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
