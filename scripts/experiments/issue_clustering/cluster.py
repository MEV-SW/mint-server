"""Step 3 — near-dup + event clustering over the embeddings, with a threshold sweep.

Pipeline:
  near-dup group : cosine >= --near-dup                       (single-linkage / union-find)
  event cluster  : cosine >= --event-sim AND |Δpublished| <= --window days

Outputs:
  data/clusters.csv              every article with its event-cluster + dup-group id
  data/clusters_for_review.md    multi-article event clusters, for human labeling
  stdout                         threshold sweep + summary stats

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/cluster.py
  .venv/bin/python scripts/experiments/issue_clustering/cluster.py --event-sim 0.82 --window 7
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            out.setdefault(self.find(i), []).append(i)
        return out


def load() -> tuple[np.ndarray, list[dict]]:
    mat = np.load(DATA / "embeddings.npy")
    ids = json.loads((DATA / "embed_ids.json").read_text(encoding="utf-8"))
    by_id = {
        json.loads(line)["id"]: json.loads(line)
        for line in (DATA / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    }
    rows = [by_id[i] for i in ids]
    return mat, rows


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # feed date fields are sometimes garbage (year 6273, 8674, ...) — drop the obviously bogus
    if not (2000 <= dt.year <= datetime.now(dt.tzinfo).year + 1):
        return None
    return dt


def cluster(sim: np.ndarray, rows: list[dict], threshold: float, window_days: float | None) -> UnionFind:
    n = len(rows)
    uf = UnionFind(n)
    dts = [parse_dt(r.get("published_at")) for r in rows]
    iu = np.triu_indices(n, k=1)
    for i, j in zip(*iu):
        if sim[i, j] < threshold:
            continue
        if window_days is not None and dts[i] and dts[j]:
            if abs((dts[i] - dts[j]).total_seconds()) > window_days * 86400:
                continue
        uf.union(int(i), int(j))
    return uf


def summarize(uf: UnionFind, rows: list[dict]) -> dict:
    groups = [g for g in uf.groups().values()]
    multi = [g for g in groups if len(g) > 1]
    in_multi = sum(len(g) for g in multi)
    cross_source = sum(1 for g in multi if len({rows[i]["source"] for i in g}) > 1)
    largest = max((len(g) for g in groups), default=0)
    return {
        "clusters": len(groups),
        "multi_article_clusters": len(multi),
        "articles_in_multi": in_multi,
        "cross_source_clusters": cross_source,
        "largest_cluster": largest,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--near-dup", type=float, default=0.90)
    ap.add_argument("--event-sim", type=float, default=0.80)
    ap.add_argument("--window", type=float, default=7.0, help="event time window in days")
    args = ap.parse_args()

    mat, rows = load()
    n = len(rows)
    sim = mat @ mat.T
    np.fill_diagonal(sim, 0.0)

    # --- embedding-space sanity: nearest-neighbour similarity distribution ---
    nn = sim.max(axis=1)
    pct = {p: round(float(np.percentile(nn, p)), 3) for p in (50, 75, 90, 95, 99)}
    print(f"corpus: {n} articles, dim {mat.shape[1]}")
    print(f"nearest-neighbour cosine  p50={pct[50]}  p75={pct[75]}  p90={pct[90]}  p95={pct[95]}  p99={pct[99]}")

    # --- threshold sweep for the event-cluster step ---
    print("\nevent-sim sweep (window = %.0f d):" % args.window)
    print(f"  {'thr':>5} {'clusters':>9} {'multi':>6} {'in_multi':>9} {'x-source':>9} {'largest':>8}")
    for thr in (0.74, 0.76, 0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90):
        s = summarize(cluster(sim, rows, thr, args.window), rows)
        print(f"  {thr:>5.2f} {s['clusters']:>9} {s['multi_article_clusters']:>6} "
              f"{s['articles_in_multi']:>9} {s['cross_source_clusters']:>9} {s['largest_cluster']:>8}")

    # --- final clustering at chosen thresholds ---
    dup_uf = cluster(sim, rows, args.near_dup, None)
    evt_uf = cluster(sim, rows, args.event_sim, args.window)
    dup_gid = {i: dup_uf.find(i) for i in range(n)}
    evt_groups = evt_uf.groups()

    # stable, human-friendly cluster numbering (largest first)
    ordered = sorted(evt_groups.values(), key=lambda g: (-len(g), g[0]))
    evt_id = {i: cid for cid, g in enumerate(ordered) for i in g}
    dup_ids = sorted(set(dup_gid.values()))
    dup_num = {root: k for k, root in enumerate(dup_ids)}

    with (DATA / "clusters.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["event_cluster", "cluster_size", "dup_group", "id", "published_at", "source", "title"])
        for cid, g in enumerate(ordered):
            for i in sorted(g, key=lambda x: rows[x].get("published_at") or ""):
                r = rows[i]
                w.writerow([cid, len(g), dup_num[dup_gid[i]], r["id"],
                            r.get("published_at") or "", r["source"], r["title"]])

    dup_multi_groups = [g for g in dup_uf.groups().values() if len(g) > 1]
    dup_multi = len(dup_multi_groups)
    evt_summary = summarize(evt_uf, rows)
    lines = [
        f"# Issue clustering — multi-article event clusters",
        "",
        f"- corpus: {n} articles from {len({r['source'] for r in rows})} sources",
        f"- near-dup (cosine >= {args.near_dup}): {dup_multi} duplicate groups",
        f"- event clusters (cosine >= {args.event_sim}, window {args.window:.0f}d): "
        f"{evt_summary['multi_article_clusters']} multi-article "
        f"({evt_summary['articles_in_multi']} articles, "
        f"{evt_summary['cross_source_clusters']} span >1 source)",
        "",
    ]
    for cid, g in enumerate(ordered):
        if len(g) < 2:
            continue
        lines.append(f"## cluster {cid}  ({len(g)} articles, "
                     f"{len({rows[i]['source'] for i in g})} sources)")
        for i in sorted(g, key=lambda x: rows[x].get("published_at") or ""):
            r = rows[i]
            day = (r.get("published_at") or "")[:10]
            lines.append(f"- [{day}] ({r['source']}) {r['title']}")
        lines.append("")

    lines.append(f"# Near-dup groups (cosine >= {args.near_dup})")
    lines.append("")
    for k, g in enumerate(sorted(dup_multi_groups, key=lambda g: (-len(g), g[0]))):
        lines.append(f"## dup group {dup_num[dup_gid[g[0]]]}  ({len(g)} articles)")
        for i in sorted(g, key=lambda x: rows[x].get("published_at") or ""):
            r = rows[i]
            sims = sorted((float(sim[i, j]) for j in g if j != i), reverse=True)
            lines.append(f"- ({r['source']}) {r['title']}  [max sim {sims[0]:.3f}]")
        lines.append("")
    (DATA / "clusters_for_review.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\nchosen: near-dup {args.near_dup}, event-sim {args.event_sim}, window {args.window:.0f}d")
    for k, v in evt_summary.items():
        print(f"  {k}: {v}")
    print(f"\nwrote {DATA / 'clusters.csv'}")
    print(f"wrote {DATA / 'clusters_for_review.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
