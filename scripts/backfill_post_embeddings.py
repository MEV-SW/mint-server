#!/usr/bin/env python3
"""One-time backfill: index recent posts into Elasticsearch with embeddings.

Re-runs the normal ES sync path (title + AI summary -> Bedrock Cohere
embedding) for posts collected in the last N days, for orgs where the
posts index predates the `embedding` field, or where indexing failed
before B0 existed.

Usage:
  cd MINT_Backend
  python3 scripts/backfill_post_embeddings.py --days 30
  python3 scripts/backfill_post_embeddings.py --days 7 --organization-id UUID
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_post_embeddings")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--organization-id", type=UUID, default=None)
    args = parser.parse_args()

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.core.config import get_settings
    from app.models.enums import PostStatus
    from app.models.organization import Organization
    from app.models.post import Post
    from app.search.post_content import sync_post_metadata

    if not get_settings().search_uses_elasticsearch:
        logger.error("SEARCH_BACKEND is not elasticsearch/dual — nothing to backfill")
        return 1

    since = datetime.now(timezone.utc) - timedelta(days=max(1, args.days))

    db = SessionLocal()
    try:
        org_ids: list[UUID]
        if args.organization_id:
            org_ids = [args.organization_id]
        else:
            org_ids = list(db.scalars(select(Organization.id)).all())

        total_ok = 0
        total_fail = 0
        for org_id in org_ids:
            posts = list(
                db.scalars(
                    select(Post)
                    .where(
                        Post.organization_id == org_id,
                        Post.status.not_in([PostStatus.deleted, PostStatus.hidden]),
                        Post.collected_at >= since,
                    )
                    .order_by(Post.collected_at.desc())
                ).all()
            )
            logger.info("org=%s posts=%s", org_id, len(posts))
            for post in posts:
                try:
                    ok = sync_post_metadata(db, post)
                    db.commit()
                    if ok:
                        total_ok += 1
                    else:
                        total_fail += 1
                        logger.warning("post=%s enqueued for retry (ES write did not confirm)", post.id)
                except Exception as exc:  # noqa: BLE001 — batch must continue
                    db.rollback()
                    total_fail += 1
                    logger.warning("post=%s failed: %s", post.id, exc)
        logger.info("done ok=%s fail=%s", total_ok, total_fail)
        return 0 if total_fail == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
