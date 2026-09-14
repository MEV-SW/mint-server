"""B3 step 3 — human labels each candidate pair. This is the one step in the
B3 pipeline that cannot be automated: "담당자가 수치 합격선을 정한다 (임의
수치 아님)" means a person has to look at real pairs and decide.

Resumable: re-running skips pairs already in data/op_labels.jsonl.

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/label_cli.py --tag op

Keys: n = near-dup(같은 기사 재작성) · e = event(같은 사건, 다른 전개)
      u = unrelated · s = skip · q = quit (progress is saved as you go)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

LABELS = {"n": "near_dup", "e": "event", "u": "unrelated", "s": "skip"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="op")
    args = ap.parse_args()
    prefix = f"{args.tag}_" if args.tag else ""

    candidates_path = DATA / f"{prefix}candidates.jsonl"
    labels_path = DATA / f"{prefix}labels.jsonl"

    candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line]
    done: set[tuple[str, str]] = set()
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            done.add((row["a_id"], row["b_id"]))

    remaining = [c for c in candidates if (c["a_id"], c["b_id"]) not in done]
    print(f"{len(done)} already labeled, {len(remaining)} remaining\n")

    with labels_path.open("a", encoding="utf-8") as out:
        for idx, pair in enumerate(remaining, 1):
            print(f"--- {idx}/{len(remaining)}  cosine={pair['cosine']}  day_gap={pair['day_gap']} ---")
            print(f"A: {pair['a_title']}")
            if pair.get("a_url"):
                print(f"   {pair['a_url']}")
            print(f"B: {pair['b_title']}")
            if pair.get("b_url"):
                print(f"   {pair['b_url']}")
            choice = input("[n]ear-dup / [e]vent / [u]nrelated / [s]kip / [q]uit > ").strip().lower()
            print()
            if choice == "q":
                break
            if choice not in LABELS:
                print("모르는 키, 건너뜀\n")
                continue
            record = {**pair, "label": LABELS[choice]}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

    print(f"저장됨 -> {labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
