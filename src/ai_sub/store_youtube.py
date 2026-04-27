"""SQLite storage for YouTube videos (seen_youtube_videos table)."""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from ai_sub.config import settings
from ai_sub.models import FilteredYouTubeVideo

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS seen_youtube_videos (
    source_id          TEXT PRIMARY KEY,
    video_id           TEXT NOT NULL,
    channel_name       TEXT NOT NULL,
    category           TEXT NOT NULL,
    title              TEXT NOT NULL,
    url                TEXT NOT NULL,
    description        TEXT,
    published_date     TEXT,
    fetched_at         TEXT NOT NULL,
    relevant           INTEGER DEFAULT 1,
    importance         TEXT,
    ai_category        TEXT,
    title_zh           TEXT,
    summary_zh         TEXT,
    key_points         TEXT,
    timeline_outline   TEXT,
    notified_at        TEXT,
    digest_included_at TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    db = Path(settings.db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    return conn


def is_youtube_seen(source_id: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM seen_youtube_videos WHERE source_id = ?", (source_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_youtube_video(v: FilteredYouTubeVideo) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO seen_youtube_videos
            (source_id, video_id, channel_name, category, title, url,
             description, published_date, fetched_at, relevant, importance,
             ai_category, title_zh, summary_zh, key_points, timeline_outline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                v.source_id, v.video_id, v.channel_name, v.category,
                v.title, v.url, v.description,
                v.published_date.isoformat() if v.published_date else None,
                datetime.now(timezone.utc).isoformat(),
                1 if v.relevant else 0,
                v.importance.value, v.ai_category,
                v.title_zh, v.summary_zh, v.key_points, v.timeline_outline,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_youtube_notified(source_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE seen_youtube_videos SET notified_at = ? WHERE source_id = ?",
            (datetime.now(timezone.utc).isoformat(), source_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_undigested_youtube(since_hours: int = 24) -> list[dict]:
    conn = _get_conn()
    try:
        cutoff = datetime.now(timezone.utc).isoformat()
        rows = conn.execute(
            """SELECT * FROM seen_youtube_videos
            WHERE digest_included_at IS NULL
              AND relevant = 1
              AND fetched_at >= datetime(?, '-' || ? || ' hours')
            ORDER BY importance ASC, fetched_at DESC""",
            (cutoff, since_hours),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_youtube_digested(source_ids: list[str]) -> None:
    if not source_ids:
        return
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "UPDATE seen_youtube_videos SET digest_included_at = ? WHERE source_id = ?",
            [(now, sid) for sid in source_ids],
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_old_youtube(days: int = 30) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM seen_youtube_videos WHERE fetched_at < datetime('now', '-' || ? || ' days')",
            (days,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
