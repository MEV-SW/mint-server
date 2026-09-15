"""B3 step 2 — pick a labeling sample of candidate pairs across the similarity
range, not just the top-K. A precision/recall sweep needs negative examples
(low-similarity pairs) as much as positive ones (high-similarity pairs).

Output: data/op_candidates.jsonl — one pair per line, unlabeled:
  {a_id, a_title, a_url, a_published_at, b_id, b_title, b_url, b_published_at,
   cosine, day_gap}

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/build_candidate_pairs.py \
      --tag op --per-bucket 25 --window-days 14
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# (low, high] similarity buckets — spans the B2 near-dup(0.90)/event(0.84) neighborhood
# plus clear negatives, so calibrate_thresholds.py has coverage on both sides.
BUCKETS = [
    (0.50, 0.70),
    (0.70, 0.80),
    (0.80, 0.84),
    (0.84, 0.90),
    (0.90, 0.95),
    (0.95, 1.01),
]


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="op")
    ap.add_argument("--per-bucket", type=int, default=25)
    ap.add_argument("--window-days", type=float, default=14)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    prefix = f"{args.tag}_" if args.tag else ""

    mat = np.load(DATA / f"{prefix}embeddings.npy")
    ids = json.loads((DATA / f"{prefix}embed_ids.json").read_text(encoding="utf-8"))
    by_id = {
        json.loads(line)["id"]: json.loads(line)
        for line in (DATA / f"{prefix}corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    rows = [by_id[i] for i in ids]
    dts = [parse_dt(r.get("published_at")) for r in rows]

    n = len(rows)
    sim = mat @ mat.T
    print(f"{n} posts, {n * (n - 1) // 2} candidate pairs before filtering")

    bucketed: list[list[tuple[int, int, float]]] = [[] for _ in BUCKETS]
    for i in range(n):
        for j in range(i + 1, n):
            if dts[i] and dts[j]:
                gap = abs((dts[i] - dts[j]).days)
                if gap > args.window_days:
                    continue
            score = float(sim[i, j])
            for bi, (lo, hi) in enumerate(BUCKETS):
                if lo <= score < hi:
                    bucketed[bi].append((i, j, score))
                    break

    random.seed(args.seed)
    picked: list[tuple[int, int, float]] = []
    for bi, (lo, hi) in enumerate(BUCKETS):
        pool = bucketed[bi]
        random.shuffle(pool)
        take = pool[: args.per_bucket]
        picked.extend(take)
        print(f"  [{lo:.2f}, {hi:.2f}): {len(pool)} available, took {len(take)}")

    # interleave difficulty — without this, low-similarity buckets (mostly
    # unrelated by construction) all come first and the labeler burns through
    # 20+ obvious "unrelated" pairs before ever seeing a near-dup/event one.
    random.shuffle(picked)

    out_path = DATA / f"{prefix}candidates.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for i, j, score in picked:
            a, b = rows[i], rows[j]
            gap = abs((dts[i] - dts[j]).days) if dts[i] and dts[j] else None
            record = {
                "a_id": a["id"], "a_title": a["title"], "a_url": a.get("url"),
                "a_published_at": a.get("published_at"),
                "b_id": b["id"], "b_title": b["title"], "b_url": b.get("url"),
                "b_published_at": b.get("published_at"),
                "cosine": round(score, 4), "day_gap": gap,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n{len(picked)} candidate pairs -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
