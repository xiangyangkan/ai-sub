"""SQLite storage for blog articles (seen_blog_articles table)."""
from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from ai_sub.config import settings
from ai_sub.models import FilteredBlogArticle

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS seen_blog_articles (
    source_id       TEXT PRIMARY KEY,
    blog_name       TEXT NOT NULL,
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    summary         TEXT NOT NULL,
    published_date  TEXT,
    fetched_at      TEXT NOT NULL,
    relevant        INTEGER DEFAULT 1,
    importance      TEXT,
    ai_category     TEXT,
    title_zh        TEXT,
    summary_zh      TEXT,
    notified_at     TEXT,
    digest_included_at TEXT,
    notify_as       TEXT DEFAULT 'blog'
);
"""


def _get_conn() -> sqlite3.Connection:
    db = Path(settings.db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    return conn


def is_blog_seen(source_id: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM seen_blog_articles WHERE source_id = ?", (source_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_blog_article(r: FilteredBlogArticle) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO seen_blog_articles
            (source_id, blog_name, category, title, url, summary,
             published_date, fetched_at, relevant, importance,
             ai_category, title_zh, summary_zh, notify_as)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.source_id, r.blog_name, r.category, r.title, r.url,
                r.summary,
                r.published_date.isoformat() if r.published_date else None,
                datetime.now(timezone.utc).isoformat(),
                1 if r.relevant else 0,
                r.importance.value, r.ai_category, r.title_zh, r.summary_zh,
                r.notify_as,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_blog_notified(source_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE seen_blog_articles SET notified_at = ? WHERE source_id = ?",
            (datetime.now(timezone.utc).isoformat(), source_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_undigested_blogs(since_hours: int = 24) -> list[dict]:
    conn = _get_conn()
    try:
        cutoff = datetime.now(timezone.utc).isoformat()
        rows = conn.execute(
            """SELECT * FROM seen_blog_articles
            WHERE digest_included_at IS NULL
              AND relevant = 1
              AND fetched_at >= datetime(?, '-' || ? || ' hours')
            ORDER BY importance ASC, fetched_at DESC""",
            (cutoff, since_hours),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_blogs_digested(source_ids: list[str]) -> None:
    if not source_ids:
        return
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "UPDATE seen_blog_articles SET digest_included_at = ? WHERE source_id = ?",
            [(now, sid) for sid in source_ids],
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_old_blogs(days: int = 30) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM seen_blog_articles WHERE fetched_at < datetime('now', '-' || ? || ' days')",
            (days,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
