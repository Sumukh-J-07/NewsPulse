"""News deduplication (FR-04).

Rules, applied in ingestion order (earliest article wins and becomes canonical):
1. Same source and provider source ID           -> duplicate ("source_id").
2. Same normalized URL                          -> duplicate ("normalized_url").
3. Same normalized headline (case/whitespace/punctuation-insensitive)
   published within 24 hours by another outlet  -> duplicate ("normalized_headline").

URL normalization strips tracking parameters, fragments, ``www.``, default ports and
trailing slashes and sorts the remaining query parameters. The original URL is always
retained unchanged on the article record.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "hsa_", "guce_")
TRACKING_KEYS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "ref", "ref_src", "referrer", "cmpid",
    "ncid", "guccounter", "soc_src", "soc_trk", "src", "source", "cid", "ito", "smid", "taid", "tpcc",
    ".tsrc", "sr_share", "feed", "rss", "mbid",
}
HEADLINE_WINDOW = timedelta(hours=24)


def normalize_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS
    ]
    query.sort()
    return urlunsplit(("https", netloc, path, urlencode(query), ""))


def normalize_headline(headline: str | None) -> str | None:
    if not headline:
        return None
    text = re.sub(r"[^\w\s]", " ", headline.casefold())
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def ingest_key(source_id: str | None, url: str | None, headline: str | None, published: str | None) -> str:
    """Key used to ignore exact re-deliveries of the same record by the same provider."""
    if source_id:
        return f"sid:{source_id}"
    if url:
        return f"url:{url.strip()}"
    digest = hashlib.sha1(f"{headline or ''}|{published or ''}".encode("utf-8")).hexdigest()
    return f"hash:{digest}"


@dataclass
class DedupIndex:
    """In-memory index of canonical articles used to classify new records."""

    by_source_id: dict[tuple[str, str], int] = field(default_factory=dict)
    by_url: dict[str, int] = field(default_factory=dict)
    by_headline: dict[str, list[tuple[int, datetime | None, str]]] = field(default_factory=dict)

    def check(self, source: str, source_id: str | None, norm_url: str | None, headline: str | None,
              published: datetime | None) -> tuple[int | None, str | None]:
        if source_id and (source, source_id) in self.by_source_id:
            return self.by_source_id[(source, source_id)], "source_id"
        if norm_url and norm_url in self.by_url:
            return self.by_url[norm_url], "normalized_url"
        key = normalize_headline(headline)
        if key and key in self.by_headline and published is not None:
            for article_id, other_pub, other_source in self.by_headline[key]:
                if other_pub is not None and abs(other_pub - published) <= HEADLINE_WINDOW:
                    return article_id, "normalized_headline"
        return None, None

    def add(self, article_id: int, source: str, source_id: str | None, norm_url: str | None,
            headline: str | None, published: datetime | None) -> None:
        if source_id:
            self.by_source_id.setdefault((source, source_id), article_id)
        if norm_url:
            self.by_url.setdefault(norm_url, article_id)
        key = normalize_headline(headline)
        if key:
            self.by_headline.setdefault(key, []).append((article_id, published, source))

    def classify(self, article_id: int, source: str, source_id: str | None, norm_url: str | None,
                 headline: str | None, published: datetime | None) -> tuple[int | None, str | None]:
        """Check then register (if canonical). Returns (duplicate_of, reason)."""
        dup_of, reason = self.check(source, source_id, norm_url, headline, published)
        if dup_of is None:
            self.add(article_id, source, source_id, norm_url, headline, published)
        return dup_of, reason
