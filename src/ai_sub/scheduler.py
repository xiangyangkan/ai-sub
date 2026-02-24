"""APScheduler: periodic fetch, daily digest, weekly cleanup."""
from __future__ import annotations

import asyncio
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ai_sub.config import settings
from ai_sub.digest_blog import build_feishu_blog_digest_elements, build_telegram_blog_digest
from ai_sub.digest_release import build_feishu_digest_elements, build_telegram_digest
from ai_sub.fetcher.blog import fetch_all_blogs
from ai_sub.fetcher.releasebot import fetch_vendor
from ai_sub.fetcher.sitemap import SITEMAP_HEADERS, SitemapSource, fetch_sitemap_articles, load_sitemap_sources
from ai_sub.filter_blog import classify_blog_article
from ai_sub.filter_release import classify_and_translate
from ai_sub.models import Importance, ReleaseItem
from ai_sub.notifier import notify_all, notify_blog, notify_blog_digest, notify_digest
from ai_sub.store_blog import (
    cleanup_old_blogs,
    get_undigested_blogs,
    is_blog_seen,
    mark_blog_notified,
    mark_blogs_digested,
    save_blog_article,
)
from ai_sub.store_release import (
    cleanup_old,
    get_undigested,
    is_seen,
    mark_digested,
    mark_notified,
    save_release,
)

logger = logging.getLogger(__name__)

# Tier -> which importance levels to push
TIER_ALLOWED = {
    "t0": {Importance.HIGH, Importance.MEDIUM, Importance.LOW},
    "t1": {Importance.HIGH, Importance.MEDIUM},
    "t2": {Importance.HIGH},
}


async def fetch_and_notify() -> None:
    """Fetch from all sources, filter, classify, and notify."""
    logger.info("Starting fetch cycle")
    all_items: list[ReleaseItem] = []

    async with httpx.AsyncClient() as client:
        tasks = [fetch_vendor(client, v) for v in settings.all_vendors]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error("Fetch error: %s", r, exc_info=r)
            elif isinstance(r, list):
                all_items.extend(r)

    # Dedup
    new_items = [item for item in all_items if not is_seen(item.source_id)]
    logger.info("Found %d new items out of %d total", len(new_items), len(all_items))

    if not new_items:
        return

    # Classify and notify
    for item in new_items:
        filtered = await classify_and_translate(item)
        save_release(filtered)

        if not filtered.relevant:
            continue

        tier = settings.vendor_tier(filtered.vendor)
        allowed = TIER_ALLOWED.get(tier, TIER_ALLOWED["t2"])

        if filtered.importance in allowed:
            try:
                await notify_all(filtered)
                mark_notified(filtered.source_id)
            except Exception as e:
                logger.error("Failed to notify for %s: %s", filtered.source_id, e, exc_info=True)


async def daily_digest() -> None:
    """Send daily digest of all releases in the last 24 hours."""
    logger.info("Building daily digest")
    releases = get_undigested(since_hours=24)
    if not releases:
        logger.info("No releases for digest")
        return

    tg_text = build_telegram_digest(releases)
    feishu_elements = build_feishu_digest_elements(releases)

    await notify_digest(tg_text, feishu_elements)
    mark_digested([r["source_id"] for r in releases])
    logger.info("Daily digest sent with %d releases", len(releases))


async def fetch_and_notify_blogs() -> None:
    """Fetch blog articles, classify with LLM, and notify."""
    if not settings.blog_enabled:
        return

    logger.info("Starting blog fetch cycle")
    all_articles = await fetch_all_blogs()

    # Split by notify_as: route "release" articles through release pipeline
    blog_articles = [a for a in all_articles if a.notify_as != "release"]
    release_articles = [a for a in all_articles if a.notify_as == "release"]

    # Process blog articles
    new_blogs = [a for a in blog_articles if not is_blog_seen(a.source_id)]
    logger.info("Found %d new blog articles out of %d total", len(new_blogs), len(blog_articles))

    for article in new_blogs:
        filtered = await classify_blog_article(article)
        save_blog_article(filtered)

        if not filtered.relevant:
            continue

        # Push HIGH and MEDIUM articles
        if filtered.importance in {Importance.HIGH, Importance.MEDIUM}:
            try:
                await notify_blog(filtered)
                mark_blog_notified(filtered.source_id)
            except Exception as e:
                logger.error("Failed to notify blog %s: %s", filtered.source_id, e, exc_info=True)

    # Process release articles (from RSS feeds with notifyAs="release")
    new_releases = [a for a in release_articles if not is_seen(a.source_id)]
    logger.info("Found %d new release articles from RSS out of %d total", len(new_releases), len(release_articles))

    for article in new_releases:
        release_item = ReleaseItem(
            source_id=article.source_id,
            vendor=article.blog_name,
            product=article.blog_name,
            title=article.title,
            url=article.url,
            summary=article.summary,
            published_date=article.published_date,
            content=article.content,
        )
        filtered_release = await classify_and_translate(release_item)
        save_release(filtered_release)

        if not filtered_release.relevant:
            continue

        if filtered_release.importance in {Importance.HIGH, Importance.MEDIUM}:
            try:
                await notify_all(filtered_release)
                mark_notified(filtered_release.source_id)
            except Exception as e:
                logger.error("Failed to notify release %s: %s", filtered_release.source_id, e, exc_info=True)


async def fetch_and_notify_sitemap(source: SitemapSource) -> None:
    """Fetch sitemap articles from a single source, classify with LLM, and notify."""
    if not settings.sitemap_enabled:
        return

    logger.info("Starting sitemap fetch for %s", source.name)

    async with httpx.AsyncClient(headers=SITEMAP_HEADERS) as client:
        try:
            all_articles = await fetch_sitemap_articles(client, source)
        except Exception as e:
            logger.error("Sitemap fetch error for %s: %s", source.name, e, exc_info=True)
            return

    if source.notify_as == "release":
        await _process_sitemap_as_release(source, all_articles)
    else:
        await _process_sitemap_as_blog(source, all_articles)


async def _process_sitemap_as_release(source: SitemapSource, all_articles: list) -> None:
    """Process sitemap articles through the release pipeline."""
    new_articles = [a for a in all_articles if not is_seen(a.source_id)]
    logger.info("[%s] Found %d new sitemap articles out of %d total", source.name, len(new_articles), len(all_articles))

    if not new_articles:
        return

    for article in new_articles:
        release_item = ReleaseItem(
            source_id=article.source_id,
            vendor=article.blog_name,
            product=article.blog_name,
            title=article.title,
            url=article.url,
            summary=article.summary,
            published_date=article.published_date,
            content=article.content,
        )
        filtered = await classify_and_translate(release_item)
        save_release(filtered)

        if not filtered.relevant:
            continue

        if filtered.importance in {Importance.HIGH, Importance.MEDIUM}:
            try:
                await notify_all(filtered)
                mark_notified(filtered.source_id)
            except Exception as e:
                logger.error("Failed to notify sitemap %s: %s", filtered.source_id, e, exc_info=True)


async def _process_sitemap_as_blog(source: SitemapSource, all_articles: list) -> None:
    """Process sitemap articles through the blog pipeline."""
    new_articles = [a for a in all_articles if not is_blog_seen(a.source_id)]
    logger.info("[%s] Found %d new sitemap articles out of %d total", source.name, len(new_articles), len(all_articles))

    if not new_articles:
        return

    for article in new_articles:
        filtered = await classify_blog_article(article)
        save_blog_article(filtered)

        if not filtered.relevant:
            continue

        if filtered.importance in {Importance.HIGH, Importance.MEDIUM}:
            try:
                await notify_blog(filtered)
                mark_blog_notified(filtered.source_id)
            except Exception as e:
                logger.error("Failed to notify sitemap %s: %s", filtered.source_id, e, exc_info=True)


async def daily_blog_digest() -> None:
    """Send daily digest of blog articles.

    Only includes notify_as='blog' articles. Release sitemap articles
    are stored in the release store and handled by daily_digest().
    """
    if not settings.blog_enabled:
        return

    logger.info("Building daily blog digest")
    articles = get_undigested_blogs(since_hours=24)
    if not articles:
        logger.info("No blog articles for digest")
        return

    tg_text = build_telegram_blog_digest(articles)
    feishu_elements = build_feishu_blog_digest_elements(articles)
    await notify_blog_digest(tg_text, feishu_elements)
    logger.info("Daily blog digest sent with %d articles", len(articles))

    mark_blogs_digested([a["source_id"] for a in articles])


async def weekly_cleanup() -> None:
    deleted = cleanup_old(days=30)
    logger.info("Cleaned up %d old release entries", deleted)
    if settings.blog_enabled:
        deleted_blogs = cleanup_old_blogs(days=30)
        logger.info("Cleaned up %d old blog entries", deleted_blogs)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Release tasks
    has_release_sitemaps = False
    if settings.release_enabled:
        scheduler.add_job(
            fetch_and_notify,
            trigger=IntervalTrigger(minutes=settings.release_fetch_interval_minutes),
            id="fetch_and_notify",
            name="Fetch and notify releases",
            max_instances=1,
        )

    # Check if any sitemap source routes to release pipeline
    if settings.sitemap_enabled:
        sitemap_sources = load_sitemap_sources(settings.sitemap_config_path)
        has_release_sitemaps = any(s.notify_as == "release" for s in sitemap_sources)

    # Schedule release digest if releasebot or release sitemaps are active
    if settings.release_enabled or has_release_sitemaps:
        scheduler.add_job(
            daily_digest,
            trigger=CronTrigger(hour=settings.release_digest_hour_utc, minute=0),
            id="daily_digest",
            name="Daily release digest",
        )

    # Blog tasks
    if settings.blog_enabled:
        scheduler.add_job(
            fetch_and_notify_blogs,
            trigger=IntervalTrigger(minutes=settings.blog_fetch_interval_minutes),
            id="fetch_and_notify_blogs",
            name="Fetch and notify blogs",
            max_instances=1,
        )

        scheduler.add_job(
            daily_blog_digest,
            trigger=CronTrigger(hour=settings.blog_digest_hour_utc, minute=0),
            id="daily_blog_digest",
            name="Daily blog digest",
        )

    # Sitemap tasks (per-source intervals)
    if settings.sitemap_enabled:
        for source in sitemap_sources:
            interval = source.fetch_interval_minutes or settings.sitemap_fetch_interval_minutes
            slug = source.name.lower().replace(" ", "_")
            scheduler.add_job(
                fetch_and_notify_sitemap,
                args=[source],
                trigger=IntervalTrigger(minutes=interval),
                id=f"sitemap_{slug}",
                name=f"Fetch sitemap: {source.name} (every {interval}min)",
                max_instances=1,
            )

    # Weekly cleanup on Sunday at 3 AM UTC
    scheduler.add_job(
        weekly_cleanup,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="weekly_cleanup",
        name="Weekly cleanup",
    )

    return scheduler
