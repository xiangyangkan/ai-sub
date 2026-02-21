"""Parse releasebot.io SvelteKit __data.json endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ai_sub.config import settings
from ai_sub.models import ReleaseItem

logger = logging.getLogger(__name__)

BASE_URL = "https://releasebot.io/updates"


def _resolve(data: list, shape: dict, base_idx: int) -> dict:
    """Resolve a SvelteKit deduped shape + flat data array into a dict."""
    result = {}
    for key, offset in shape.items():
        idx = base_idx + offset if isinstance(offset, int) and offset < len(data) else offset
        if isinstance(idx, int) and 0 <= idx < len(data):
            val = data[idx]
            if isinstance(val, dict) and all(isinstance(v, int) for v in val.values()):
                result[key] = _resolve(data, val, 0)
            else:
                result[key] = val
        else:
            result[key] = None
    return result


async def fetch_vendor(client: httpx.AsyncClient, vendor: str) -> list[ReleaseItem]:
    """Fetch releases for a vendor from releasebot.io __data.json."""
    url = f"{BASE_URL}/{vendor}/__data.json"
    try:
        resp = await client.get(url, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch %s: %s", vendor, e)
        return []

    try:
        payload = resp.json()
    except Exception:
        logger.error("Invalid JSON from %s", vendor)
        return []

    return _parse_sveltekit(payload, vendor)


def _parse_sveltekit(payload: dict, vendor: str) -> list[ReleaseItem]:
    """Parse the SvelteKit __data.json response into ReleaseItems."""
    items: list[ReleaseItem] = []
    nodes = payload.get("nodes", [])

    # Find the node with releases data (usually node index 3)
    data_array: list | None = None
    for node in nodes:
        if node.get("type") != "data":
            continue
        d = node.get("data", [])
        if not isinstance(d, list) or len(d) < 6:
            continue
        # Look for the node whose first element (shape) has a "releases" key
        if isinstance(d[0], dict) and "releases" in d[0]:
            data_array = d
            break

    if data_array is None:
        logger.warning("No releases data found for vendor %s", vendor)
        return []

    shape = data_array[0]  # Top-level shape: {"vendor": 1, "releases": 5, ...}
    releases_idx = shape.get("releases")
    if releases_idx is None or releases_idx >= len(data_array):
        return []

    release_indices = data_array[releases_idx]
    if not isinstance(release_indices, list):
        return []

    limit = settings.max_releases_per_vendor
    for ridx in release_indices[:limit]:
        if not isinstance(ridx, int) or ridx >= len(data_array):
            continue
        release_shape = data_array[ridx]
        if not isinstance(release_shape, dict):
            continue

        try:
            rel = _resolve(data_array, release_shape, 0)
            item = _build_item(rel, vendor)
            if item:
                items.append(item)
        except Exception as e:
            logger.debug("Failed to parse release at index %d for %s: %s", ridx, vendor, e)

    logger.info("Fetched %d releases from releasebot.io/%s", len(items), vendor)
    return items


def _build_item(rel: dict, vendor: str) -> ReleaseItem | None:
    """Build a ReleaseItem from a resolved release dict."""
    release_id = rel.get("id")
    if release_id is None:
        return None

    details = rel.get("release_details", {}) or {}
    product_info = rel.get("product", {}) or {}
    source_info = rel.get("source", {}) or {}

    title = details.get("release_name") or rel.get("slug", "")
    summary = details.get("release_summary") or ""
    version = details.get("release_number")
    product = product_info.get("display_name") or vendor

    source_url = source_info.get("source_url") or f"{BASE_URL}/{vendor}"
    if not source_url or source_url is None:
        source_url = f"{BASE_URL}/{vendor}"

    release_date = None
    raw_date = rel.get("release_date") or rel.get("created_at")
    if raw_date and isinstance(raw_date, str):
        try:
            release_date = datetime.fromisoformat(raw_date)
            if release_date.tzinfo is None:
                release_date = release_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    content = rel.get("formatted_content") or summary

    return ReleaseItem(
        source_id=f"{vendor}:{release_id}",
        vendor=vendor,
        product=product,
        title=title,
        version=str(version) if version is not None else None,
        summary=summary[:500] if summary else title,
        url=source_url,
        published_date=release_date,
        content=content[:2000] if content else None,
    )
