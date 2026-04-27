"""YouTube channel RSS feed fetching and transcript retrieval."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import yaml

from ai_sub.config import settings
from ai_sub.models import YouTubeVideo

logger = logging.getLogger(__name__)

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


@dataclass
class YouTubeChannel:
    name: str
    channel_id: str
    category: str = ""


def load_youtube_channels(path: str) -> list[YouTubeChannel]:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("YouTube channels config not found: %s", path)
        return []

    channels: list[YouTubeChannel] = []
    for item in data.get("channels") or []:
        channels.append(YouTubeChannel(
            name=item["name"],
            channel_id=item["channel_id"],
            category=item.get("category", ""),
        ))

    logger.info("Loaded %d YouTube channels from %s", len(channels), path)
    return channels


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _make_source_id(channel_name: str, video_id: str) -> str:
    return f"yt:{_slugify(channel_name)}:{video_id}"


def _parse_published(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def _fetch_channel_feed(
    client: httpx.AsyncClient,
    channel: YouTubeChannel,
    semaphore: asyncio.Semaphore,
) -> list[YouTubeVideo]:
    async with semaphore:
        await asyncio.sleep(2)
        url = RSS_URL_TEMPLATE.format(channel_id=channel.channel_id)
        try:
            resp = await client.get(url, timeout=20, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch YouTube feed for %s: %s", channel.name, e)
            return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.warning("Failed to parse YouTube feed XML for %s: %s", channel.name, e)
            return []

        videos: list[YouTubeVideo] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            video_id = entry.findtext("yt:videoId", namespaces=ATOM_NS)
            if not video_id:
                continue

            title = entry.findtext("atom:title", default="", namespaces=ATOM_NS)
            published = _parse_published(
                entry.findtext("atom:published", namespaces=ATOM_NS)
            )

            description = ""
            media_group = entry.find("media:group", ATOM_NS)
            if media_group is not None:
                description = media_group.findtext(
                    "media:description", default="", namespaces=ATOM_NS
                )

            videos.append(YouTubeVideo(
                source_id=_make_source_id(channel.name, video_id),
                video_id=video_id,
                channel_name=channel.name,
                category=channel.category,
                title=title,
                url=f"https://www.youtube.com/watch?v={video_id}",
                description=description[:2000],
                published_date=published,
            ))

        max_per = settings.youtube_max_videos_per_channel
        videos.sort(
            key=lambda v: v.published_date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return videos[:max_per]


async def fetch_youtube_videos() -> list[YouTubeVideo]:
    channels = load_youtube_channels(settings.youtube_channels_path)
    if not channels:
        return []

    semaphore = asyncio.Semaphore(2)
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_channel_feed(client, ch, semaphore) for ch in channels
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_videos: list[YouTubeVideo] = []
    for r in results:
        if isinstance(r, list):
            all_videos.extend(r)
        elif isinstance(r, Exception):
            logger.error("YouTube feed fetch error: %s", r, exc_info=r)

    return all_videos


_transcript_lock = asyncio.Lock()


async def fetch_transcript(video_id: str) -> tuple[str, list[dict]]:
    """Fetch transcript using youtube-transcript-api. Returns (plain_text, segments).

    Uses a lock + delay to serialize requests and avoid YouTube IP blocks.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    def _sync_fetch() -> tuple[str, list[dict]]:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(
            video_id,
            languages=["zh-Hans", "zh-Hant", "zh", "en"],
        )
        segments = [{"start": s.start, "text": s.text} for s in transcript]
        plain = " ".join(s.text for s in transcript)
        return plain, segments

    async with _transcript_lock:
        try:
            result = await asyncio.to_thread(_sync_fetch)
            await asyncio.sleep(3)
            return result
        except Exception as e:
            logger.warning("Failed to fetch transcript for %s: %s", video_id, e)
            await asyncio.sleep(3)
            return "", []
