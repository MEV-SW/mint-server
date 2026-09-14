"""Step 1 — build a real article corpus by crawling the seed RSS feeds now.

Output: data/corpus.jsonl  (one article per line)
  {id, source, lang, title, summary, url, published_at}

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/fetch_corpus.py \
      --days 21 --per-feed 80
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)

sys.path.insert(0, str(HERE))
from feeds import FEEDS  # noqa: E402

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "fbclid", "gclid", "ref", "ref_src", "spm", "ncid"}


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return _WS_RE.sub(" ", text).strip()


def norm_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if not parts.scheme:
        return url.strip()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    query = "&".join(
        p for p in parts.query.split("&")
        if p and p.split("=", 1)[0].lower() not in _TRACKING
    )
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
            except (OverflowError, ValueError):
                pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21, help="keep articles published within N days")
    ap.add_argument("--per-feed", type=int, default=80)
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    seen_urls: set[str] = set()
    rows: list[dict] = []
    headers = {"User-Agent": "Mozilla/5.0 (MINT issue-clustering experiment)"}

    with httpx.Client(follow_redirects=True, timeout=args.timeout, headers=headers) as client:
        for feed in FEEDS:
            try:
                resp = client.get(feed["url"])
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {feed['name']}: fetch failed ({exc.__class__.__name__})")
                continue
            parsed = feedparser.parse(resp.content)
            kept = 0
            for entry in parsed.entries[: args.per_feed * 2]:
                if kept >= args.per_feed:
                    break
                url = norm_url(entry.get("link", ""))
                title = clean_text(entry.get("title", ""))
                if not url or not title or url in seen_urls:
                    continue
                published = entry_published(entry)
                if published and published < cutoff:
                    continue
                summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
                seen_urls.add(url)
                rows.append({
                    "id": hashlib.sha1(url.encode()).hexdigest()[:16],
                    "source": feed["name"],
                    "lang": feed["lang"],
                    "title": title,
                    "summary": summary[:2000],
                    "url": url,
                    "published_at": published.isoformat() if published else None,
                })
                kept += 1
            print(f"  + {feed['name']}: {kept}")

    out = DATA / "corpus.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    dated = sum(1 for r in rows if r["published_at"])
    print(f"\ncorpus: {len(rows)} articles ({dated} with a date) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
