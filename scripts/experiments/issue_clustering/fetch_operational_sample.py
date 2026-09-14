"""B3 step 1 — pull a real operational posts sample (not an RSS snapshot).

B2 used a single RSS crawl-now snapshot, pre-relevance-gate. B3 re-runs the
same pipeline against actual DB posts (post-classification, post-AI-summary)
to check whether the B2 thresholds hold on the real distribution.

Output: data/op_corpus.jsonl — same schema as data/corpus.jsonl, so the
existing embed_corpus.py / cluster.py work unchanged via --corpus/--out.
  {id, source, lang, title, summary, url, published_at}

Usage:
  cd MINT_Backend
  .venv/bin/python scripts/experiments/issue_clustering/fetch_operational_sample.py --days 30 --limit 400
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
ROOT = HERE.parents[2]  # MINT_Backend/
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--organization-id", default=None)
    ap.add_argument("--out", default="op_corpus.jsonl")
    args = ap.parse_args()

    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.core.database import SessionLocal
    from app.models.ai_output import AIOutput
    from app.models.enums import PostStatus
    from app.models.post import Post

    since = datetime.now(timezone.utc) - timedelta(days=args.days)

    db = SessionLocal()
    try:
        q = (
            select(Post)
            .options(joinedload(Post.source), joinedload(Post.ai_outputs))
            .where(
                Post.status.not_in([PostStatus.deleted, PostStatus.hidden]),
                Post.collected_at >= since,
            )
            .order_by(Post.collected_at.desc())
            .limit(args.limit)
        )
        if args.organization_id:
            q = q.where(Post.organization_id == args.organization_id)

        rows = db.scalars(q).unique().all()
        print(f"fetched {len(rows)} posts from DB (last {args.days}d)")

        out_path = DATA / args.out
        with out_path.open("w", encoding="utf-8") as f:
            for post in rows:
                latest_ai = max(post.ai_outputs, key=lambda a: a.created_at) if post.ai_outputs else None
                summary = (latest_ai.summary if latest_ai else "") or ""
                record = {
                    "id": str(post.id),
                    "source": post.source.name if post.source else "",
                    "lang": "ko",
                    "title": post.title or "",
                    "summary": summary,
                    "url": post.original_url or "",
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"saved -> {out_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
