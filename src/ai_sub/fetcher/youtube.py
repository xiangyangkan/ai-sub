"""YouTube channel RSS feed fetching and transcript retrieval."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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

        videos.sort(
            key=lambda v: v.published_date or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        cutoff = settings.backfill_cutoff
        if cutoff:
            # Backfill: keep every video on/after the cutoff (undated kept),
            # capped for safety. YouTube RSS only exposes ~15 recent videos.
            videos = [v for v in videos if v.published_date is None or v.published_date >= cutoff]
            return videos[:settings.backfill_max_items]
        return videos[:settings.youtube_max_videos_per_channel]


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


def _build_transcript_api() -> "YouTubeTranscriptApi":
    from youtube_transcript_api import YouTubeTranscriptApi

    if settings.youtube_proxy_username and settings.youtube_proxy_password:
        from youtube_transcript_api.proxies import WebshareProxyConfig

        proxy = WebshareProxyConfig(
            proxy_username=settings.youtube_proxy_username,
            proxy_password=settings.youtube_proxy_password,
        )
        return YouTubeTranscriptApi(proxy_config=proxy)

    return YouTubeTranscriptApi()


def _whisper_transcribe_sync(video_id: str) -> tuple[str, list[dict]]:
    """Download audio via yt-dlp and transcribe with OpenAI Whisper API."""
    import yt_dlp
    from openai import OpenAI

    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, f"{video_id}.m4a")

    try:
        ydl_opts = {
            "format": "ba[filesize<25M]/ba[abr<=64]/ba",
            "outtmpl": os.path.join(tmp_dir, f"{video_id}.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }],
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        audio_file = Path(tmp_dir) / f"{video_id}.m4a"
        if not audio_file.exists():
            for f in Path(tmp_dir).iterdir():
                if f.suffix in (".m4a", ".mp3", ".opus", ".webm", ".wav"):
                    audio_file = f
                    break

        if not audio_file.exists():
            logger.warning("yt-dlp produced no audio file for %s", video_id)
            return "", []

        if audio_file.stat().st_size > 25 * 1024 * 1024:
            logger.warning("Audio file too large for Whisper API (%s): %d bytes",
                           video_id, audio_file.stat().st_size)
            return "", []

        client_kwargs = {}
        if settings.openai_api_key:
            client_kwargs["api_key"] = settings.openai_api_key
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url

        client = OpenAI(**client_kwargs)

        with open(audio_file, "rb") as af:
            response = client.audio.transcriptions.create(
                model=settings.whisper_model,
                file=af,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        plain_parts = []
        for seg in response.segments or []:
            segments.append({"start": seg["start"], "text": seg["text"].strip()})
            plain_parts.append(seg["text"].strip())

        plain = " ".join(plain_parts) if plain_parts else (response.text or "")
        if not segments and response.text:
            segments = [{"start": 0.0, "text": response.text}]

        return plain, segments

    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)


async def fetch_transcript(video_id: str) -> tuple[str, list[dict], bool]:
    """Fetch transcript using youtube-transcript-api, with Whisper fallback.

    Uses a lock + delay to serialize requests and avoid YouTube IP blocks.
    Returns (plain_text, segments, permanently_failed).
    permanently_failed=True means subtitles are disabled and no fallback is available.
    """
    from youtube_transcript_api._errors import TranscriptsDisabled

    def _sync_fetch() -> tuple[str, list[dict]]:
        ytt = _build_transcript_api()
        transcript = ytt.fetch(
            video_id,
            languages=["en", "en-US", "en-GB", "en-AU", "en-CA", "en-IE", "en-IN", "zh-Hans", "zh-Hant", "zh"],
        )
        segments = [{"start": s.start, "text": s.text} for s in transcript]
        plain = " ".join(s.text for s in transcript)
        return plain, segments

    subtitles_disabled = False

    async with _transcript_lock:
        try:
            result = await asyncio.to_thread(_sync_fetch)
            await asyncio.sleep(3)
            return result[0], result[1], False
        except TranscriptsDisabled:
            logger.warning("Subtitles are disabled for %s", video_id)
            subtitles_disabled = True
        except Exception as e:
            logger.warning("Failed to fetch transcript for %s: %s", video_id, e)

        if (subtitles_disabled or True) and settings.youtube_whisper_fallback and settings.openai_api_key:
            logger.info("Attempting Whisper fallback for %s", video_id)
            try:
                result = await asyncio.to_thread(_whisper_transcribe_sync, video_id)
                await asyncio.sleep(3)
                if result[0]:
                    logger.info("Whisper transcription successful for %s", video_id)
                    return result[0], result[1], False
            except Exception as e:
                logger.warning("Whisper fallback failed for %s: %s", video_id, e)

        await asyncio.sleep(3)
        permanently_failed = subtitles_disabled and not settings.youtube_whisper_fallback
        return "", [], permanently_failed
