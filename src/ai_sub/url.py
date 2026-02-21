"""URL normalization utilities for deduplication."""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Query parameters that are tracking/cache-busting noise and should be stripped
_NOISE_PARAMS = {
    # Cache busting
    "_", "__", "cb", "t", "ts", "timestamp", "nocache", "rand", "random",
    # UTM tracking
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    # Social / ad click tracking
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid",
    # Email tracking
    "mc_cid", "mc_eid", "_hsenc", "_hsmi",
    # Misc
    "oly_enc_id", "oly_anon_id", "_openstat", "yclid", "spm",
}


def normalize_url(url: str) -> str:
    """Strip tracking / cache-busting query params and fragment for dedup.

    If the input is not a valid URL (no scheme or netloc), it is returned as-is.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    if not parsed.scheme or not parsed.netloc:
        return url

    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k.lower() not in _NOISE_PARAMS}
    new_query = urlencode(sorted(cleaned.items()), doseq=True) if cleaned else ""

    return urlunparse(parsed._replace(query=new_query, fragment=""))
