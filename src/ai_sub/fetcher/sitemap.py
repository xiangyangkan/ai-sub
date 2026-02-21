"""Sitemap-based blog article fetching for sites without RSS feeds."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import yaml

from ai_sub.config import settings
from ai_sub.models import BlogArticle
from ai_sub.url import normalize_url

logger = logging.getLogger(__name__)

# Default namespaces (some sites use https:// variant for the sitemap schema)
NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}

# Browser-like User-Agent to avoid 403 from sites that block default httpx UA
SITEMAP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


@dataclass
class SitemapSource:
    name: str
    category: str
    sitemap_url: str
    path_prefixes: list[str] = field(default_factory=list)
    max_articles: int = 10
    notify_as: str = "blog"  # "blog" or "release"
    fetch_interval_minutes: int = 0  # 0 = use global default


def load_sitemap_sources(path: str) -> list[SitemapSource]:
    """Parse YAML config and return list of SitemapSource."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("Sitemap config not found: %s", path)
        return []

    sources: list[SitemapSource] = []
    for item in data.get("sitemaps") or []:
        sources.append(SitemapSource(
            name=item["name"],
            category=item.get("category", ""),
            sitemap_url=item["sitemap_url"],
            path_prefixes=item.get("path_prefixes", []),
            max_articles=item.get("max_articles", 10),
            notify_as=item.get("notify_as", "blog"),
            fetch_interval_minutes=item.get("fetch_interval_minutes", 0),
        ))

    logger.info("Loaded %d sitemap sources from %s", len(sources), path)
    return sources


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _make_source_id(source_name: str, url: str) -> str:
    slug = _slugify(source_name)
    url_hash = hashlib.md5(normalize_url(url).encode()).hexdigest()[:12]
    return f"blog:{slug}:{url_hash}"


def _parse_lastmod(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_meta(html: str) -> tuple[str, str]:
    """Extract title and description from HTML page."""
    title = ""
    description = ""

    # <title>
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()

    # <meta name="description"> or <meta property="og:description">
    for pattern in [
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+content=["\'](.*?)["\']\s+name=["\']description["\']',
        r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']',
        r'<meta\s+content=["\'](.*?)["\']\s+property=["\']og:description["\']',
    ]:
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if m:
            description = m.group(1).strip()
            break

    return title, description


async def fetch_sitemap_articles(
    client: httpx.AsyncClient, source: SitemapSource
) -> list[BlogArticle]:
    """Fetch articles from a single sitemap source."""
    try:
        resp = await client.get(source.sitemap_url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch sitemap %s: %s", source.name, e)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.warning("Failed to parse sitemap XML %s: %s", source.name, e)
        return []

    # Auto-detect sitemap namespace from root tag (handles http:// vs https:// variants)
    ns = dict(NS)
    m = re.match(r"\{(.*)\}", root.tag)
    if m:
        ns["sm"] = m.group(1)

    # Collect matching URLs with lastmod
    entries: list[tuple[str, datetime | None]] = []
    for url_elem in root.findall("sm:url", ns):
        loc = url_elem.findtext("sm:loc", namespaces=ns)
        if not loc:
            continue

        path = urlparse(loc).path
        if source.path_prefixes and not any(path.startswith(p) for p in source.path_prefixes):
            continue

        lastmod = _parse_lastmod(
            url_elem.findtext("sm:lastmod", namespaces=ns)
            or url_elem.findtext("news:news/news:publication_date", namespaces=ns)
        )
        entries.append((loc, lastmod))

    # Sort by lastmod descending (None last)
    entries.sort(key=lambda e: e[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    entries = entries[:source.max_articles]

    if not entries:
        logger.debug("No matching URLs in sitemap %s", source.name)
        return []

    logger.info("Found %d matching URLs in sitemap %s", len(entries), source.name)

    # Fetch page metadata concurrently
    semaphore = asyncio.Semaphore(5)
    articles: list[BlogArticle] = []

    async def _fetch_page(url: str, lastmod: datetime | None) -> BlogArticle | None:
        async with semaphore:
            try:
                resp = await client.get(url, timeout=20, follow_redirects=True)
                resp.raise_for_status()
                title, description = _extract_meta(resp.text)
            except httpx.HTTPError as e:
                logger.debug("Failed to fetch page %s: %s", url, e)
                title, description = "", ""

            if not title:
                # Fallback: use last path segment
                title = urlparse(url).path.rstrip("/").split("/")[-1].replace("-", " ").title()

            return BlogArticle(
                source_id=_make_source_id(source.name, url),
                blog_name=source.name,
                category=source.category,
                title=title,
                url=url,
                summary=description or title,
                published_date=lastmod,
                content=description[:3000] or None,
                notify_as=source.notify_as,
            )

    tasks = [_fetch_page(url, lastmod) for url, lastmod in entries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, BlogArticle):
            articles.append(result)
        elif isinstance(result, Exception):
            logger.debug("Page fetch error: %s", result)

    return articles
