"""OPML parsing + RSS feed fetching for blog articles."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from ai_sub.config import settings
from ai_sub.models import BlogArticle
from ai_sub.url import normalize_url

logger = logging.getLogger(__name__)


@dataclass
class FeedInfo:
    title: str
    xml_url: str
    html_url: str
    category: str
    notify_as: str = "blog"  # "blog" or "release"


def parse_opml(path: str) -> list[FeedInfo]:
    """Parse OPML file and extract feed info with category from parent outline."""
    tree = ET.parse(path)
    root = tree.getroot()
    feeds: list[FeedInfo] = []

    for category_outline in root.findall(".//body/outline"):
        category = category_outline.get("title") or category_outline.get("text") or ""
        for feed_outline in category_outline.findall("outline[@type='rss']"):
            xml_url = feed_outline.get("xmlUrl", "")
            if not xml_url:
                continue
            feeds.append(FeedInfo(
                title=feed_outline.get("title") or feed_outline.get("text") or "",
                xml_url=xml_url,
                html_url=feed_outline.get("htmlUrl") or "",
                category=category,
                notify_as=feed_outline.get("notifyAs") or "blog",
            ))

    logger.info("Parsed %d feeds from OPML: %s", len(feeds), path)
    return feeds


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _make_source_id(feed_title: str, entry_id: str) -> str:
    slug = _slugify(feed_title)
    normalized = normalize_url(entry_id)
    entry_hash = hashlib.md5(normalized.encode()).hexdigest()[:12]
    return f"blog:{slug}:{entry_hash}"


def _parse_date(entry: dict) -> datetime | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        for parse in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                dt = parse(raw)
            except Exception:
                continue
            # Guarantee tz-aware so downstream comparisons (e.g. backfill cutoff)
            # never mix naive/aware datetimes. RFC-822 "-0000" yields naive.
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return None


def _extract_content(entry: dict) -> str:
    """Extract best available content from a feed entry."""
    if entry.get("content"):
        for c in entry["content"]:
            if c.get("value"):
                return c["value"]
    return entry.get("summary") or entry.get("title") or ""


def _strip_html(html_text: str) -> str:
    """Simple HTML tag stripping."""
    return re.sub(r"<[^>]+>", "", html_text).strip()


async def _fetch_single_feed(
    client: httpx.AsyncClient, feed: FeedInfo
) -> list[BlogArticle]:
    """Fetch and parse a single RSS feed."""
    try:
        resp = await client.get(feed.xml_url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.debug("Failed to fetch feed %s: %s", feed.title, e)
        return []

    try:
        parsed = feedparser.parse(resp.text)
    except Exception as e:
        logger.debug("Failed to parse feed %s: %s", feed.title, e)
        return []

    articles: list[BlogArticle] = []
    cutoff = settings.backfill_cutoff
    limit = settings.backfill_max_items if cutoff else settings.blog_max_articles_per_feed

    for entry in parsed.entries[:limit]:
        entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
        if not entry_id:
            continue

        # Backfill: skip entries published before the cutoff (undated entries
        # are kept since a feed only exposes a bounded set of recent items).
        published = _parse_date(entry)
        if cutoff and published and published < cutoff:
            continue

        link = normalize_url(entry.get("link") or feed.html_url)
        raw_summary = entry.get("summary") or ""
        summary_text = _strip_html(raw_summary)[:500]
        content_text = _strip_html(_extract_content(entry))[:3000]

        articles.append(BlogArticle(
            source_id=_make_source_id(feed.title, entry_id),
            blog_name=feed.title,
            category=feed.category,
            title=entry.get("title", ""),
            url=link,
            summary=summary_text or entry.get("title", ""),
            published_date=published,
            content=content_text or None,
            notify_as=feed.notify_as,
        ))

    return articles


async def fetch_all_blogs() -> list[BlogArticle]:
    """Fetch articles from all OPML feeds concurrently."""
    feeds = parse_opml(settings.blog_opml_path)
    if not feeds:
        logger.warning("No feeds found in OPML")
        return []

    semaphore = asyncio.Semaphore(10)
    all_articles: list[BlogArticle] = []

    async def _limited_fetch(feed: FeedInfo) -> list[BlogArticle]:
        async with semaphore:
            return await _fetch_single_feed(client, feed)

    async with httpx.AsyncClient() as client:
        tasks = [_limited_fetch(f) for f in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.debug("Feed fetch error for %s: %s", feeds[i].title, result)
            elif isinstance(result, list):
                all_articles.extend(result)

    logger.info("Fetched %d articles from %d feeds", len(all_articles), len(feeds))
    return all_articles
