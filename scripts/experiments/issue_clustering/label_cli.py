"""B3 step 3 — human labels each candidate pair. This is the one step in the
B3 pipeline that cannot be automated: "담당자가 수치 합격선을 정한다 (임의
수치 아님)" means a person has to look at real pairs and decide.

Resumable: re-running skips pairs already in data/op_labels.jsonl.

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/label_cli.py --tag op

  # after auto_label.py: review AI pre-labels instead of labeling from scratch
  .venv/bin/python scripts/experiments/issue_clustering/label_cli.py --tag op --review

Keys: n = near-dup(같은 기사 재작성) · e = event(같은 사건, 다른 전개)
      u = unrelated · s = skip · q = quit (progress is saved as you go)
      --review 모드: [Enter] = AI 라벨 그대로 승인
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

LABELS = {"n": "near_dup", "e": "event", "u": "unrelated", "s": "skip"}


def _load_last_write_wins(labels_path: Path) -> dict[tuple[str, str], dict]:
    """Later rows override earlier ones for the same (a_id, b_id) — lets a
    human override an AI pre-label by just appending a new row."""
    latest: dict[tuple[str, str], dict] = {}
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            latest[(row["a_id"], row["b_id"])] = row
    return latest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="op")
    ap.add_argument("--review", action="store_true", help="review AI pre-labels (auto_label.py) instead")
    args = ap.parse_args()
    prefix = f"{args.tag}_" if args.tag else ""

    candidates_path = DATA / f"{prefix}candidates.jsonl"
    labels_path = DATA / f"{prefix}labels.jsonl"

    candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line]
    latest = _load_last_write_wins(labels_path)

    if args.review:
        queue = [c for c in candidates if latest.get((c["a_id"], c["b_id"]), {}).get("source") == "ai"]
        print(f"{len(queue)}개 AI 라벨 검토 대상\n")
    else:
        queue = [c for c in candidates if (c["a_id"], c["b_id"]) not in latest]
        print(f"{len(latest)}개 이미 라벨링됨, {len(queue)}개 남음\n")

    with labels_path.open("a", encoding="utf-8") as out:
        for idx, pair in enumerate(queue, 1):
            print(f"--- {idx}/{len(queue)}  cosine={pair['cosine']}  day_gap={pair['day_gap']} ---")
            print(f"A: {pair['a_title']}")
            if pair.get("a_url"):
                print(f"   {pair['a_url']}")
            print(f"B: {pair['b_title']}")
            if pair.get("b_url"):
                print(f"   {pair['b_url']}")

            if args.review:
                prior = latest[(pair["a_id"], pair["b_id"])]
                print(f"AI 라벨: {prior['label']}  ({prior.get('reason', '')})")
                choice = input("[Enter]승인 / [n/e/u]재분류 / [s]건너뜀 / [q]종료 > ").strip().lower()
            else:
                choice = input("[n]ear-dup / [e]vent / [u]nrelated / [s]kip / [q]uit > ").strip().lower()
            print()

            if choice == "q":
                break
            if args.review and choice == "":
                record = {**pair, "label": prior["label"], "source": "human_confirmed"}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                continue
            if choice == "s":
                continue
            if choice not in LABELS:
                print("모르는 키, 건너뜀\n")
                continue
            record = {**pair, "label": LABELS[choice], "source": "human"}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

    print(f"저장됨 -> {labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
