from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from ai_sub.config import settings
from ai_sub.models import FilteredRelease

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS seen_releases (
    source_id       TEXT PRIMARY KEY,
    vendor          TEXT NOT NULL,
    product         TEXT NOT NULL,
    title           TEXT NOT NULL,
    version         TEXT,
    url             TEXT NOT NULL,
    summary         TEXT NOT NULL,
    published_date  TEXT,
    fetched_at      TEXT NOT NULL,
    relevant        INTEGER DEFAULT 1,
    importance      TEXT,
    category        TEXT,
    title_zh        TEXT,
    summary_zh      TEXT,
    notified_at     TEXT,
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


def is_seen(source_id: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM seen_releases WHERE source_id = ?", (source_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_release(r: FilteredRelease) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO seen_releases
            (source_id, vendor, product, title, version, url, summary,
             published_date, fetched_at, relevant, importance, category,
             title_zh, summary_zh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.source_id, r.vendor, r.product, r.title, r.version,
                r.url, r.summary,
                r.published_date.isoformat() if r.published_date else None,
                datetime.now(timezone.utc).isoformat(),
                1 if r.relevant else 0, r.importance.value, r.category,
                r.title_zh, r.summary_zh,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_notified(source_id: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE seen_releases SET notified_at = ? WHERE source_id = ?",
            (datetime.now(timezone.utc).isoformat(), source_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_undigested(since_hours: int = 24) -> list[dict]:
    conn = _get_conn()
    try:
        cutoff = datetime.now(timezone.utc).isoformat()
        rows = conn.execute(
            """SELECT * FROM seen_releases
            WHERE digest_included_at IS NULL
              AND relevant = 1
              AND fetched_at >= datetime(?, '-' || ? || ' hours')
            ORDER BY importance ASC, fetched_at DESC""",
            (cutoff, since_hours),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_digested(source_ids: list[str]) -> None:
    if not source_ids:
        return
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "UPDATE seen_releases SET digest_included_at = ? WHERE source_id = ?",
            [(now, sid) for sid in source_ids],
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_old(days: int = 30) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM seen_releases WHERE fetched_at < datetime('now', '-' || ? || ' days')",
            (days,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
