"""B3 step 4 — sweep thresholds against the human-labeled pairs, print
precision/recall, and (on --commit) freeze the chosen cutoffs as the golden
regression asset.

near-dup positive = label in {near_dup}         (== issue_revision duplicate)
event positive    = label in {near_dup, event}   (near-dup implies same event too)

Usage:
  # just look at the sweep, decide nothing yet
  .venv/bin/python scripts/experiments/issue_clustering/calibrate_thresholds.py --tag op

  # after eyeballing the table, freeze a decision
  .venv/bin/python scripts/experiments/issue_clustering/calibrate_thresholds.py --tag op \
      --near-dup 0.90 --event 0.84 --commit --decided-by 채윤성
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

SWEEP = [round(0.50 + 0.02 * i, 2) for i in range(26)]  # 0.50 .. 1.00


def prf(labels: list[dict], threshold: float, positive_labels: set[str]) -> tuple[float, float, float, int]:
    tp = fp = fn = tn = 0
    for row in labels:
        predicted_positive = row["cosine"] >= threshold
        actual_positive = row["label"] in positive_labels
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and actual_positive:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    return precision, recall, tp + fp, tp + fn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="op")
    ap.add_argument("--near-dup", type=float, default=None)
    ap.add_argument("--event", type=float, default=None)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--decided-by", default="")
    args = ap.parse_args()
    prefix = f"{args.tag}_" if args.tag else ""

    labels_path = DATA / f"{prefix}labels.jsonl"
    # last write wins per (a_id, b_id) — a human override (label_cli.py --review)
    # appends a new row rather than editing the AI pre-label in place.
    latest: dict[tuple[str, str], dict] = {}
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        latest[(row["a_id"], row["b_id"])] = row
    labels = [row for row in latest.values() if row["label"] != "skip"]
    ai_only = sum(1 for row in labels if row.get("source") == "ai")
    if ai_only:
        print(f"주의: {ai_only}개는 AI 예비 라벨이 사람 검토 없이 그대로 쓰였습니다 "
              f"(label_cli.py --tag {args.tag} --review로 검토 권장)\n")
    counts = {}
    for row in labels:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    print(f"{len(labels)} labeled pairs: {counts}\n")

    print("near-dup sweep (positive = near_dup only)")
    print(f"{'thr':>5}  {'prec':>6}  {'recall':>6}  {'n_pred':>6}  {'n_actual':>8}")
    for t in SWEEP:
        p, r, npred, nact = prf(labels, t, {"near_dup"})
        print(f"{t:>5}  {p:>6.2f}  {r:>6.2f}  {npred:>6}  {nact:>8}")

    print("\nevent sweep (positive = near_dup or event)")
    print(f"{'thr':>5}  {'prec':>6}  {'recall':>6}  {'n_pred':>6}  {'n_actual':>8}")
    for t in SWEEP:
        p, r, npred, nact = prf(labels, t, {"near_dup", "event"})
        print(f"{t:>5}  {p:>6.2f}  {r:>6.2f}  {npred:>6}  {nact:>8}")

    if not args.commit:
        print("\n(--commit 없이 실행됨 — 표만 보여주고 아무것도 저장하지 않았습니다)")
        return 0

    if args.near_dup is None or args.event is None:
        print("\n--commit 하려면 --near-dup, --event 둘 다 지정하세요.")
        return 1

    dup_p, dup_r, _, _ = prf(labels, args.near_dup, {"near_dup"})
    ev_p, ev_r, _, _ = prf(labels, args.event, {"near_dup", "event"})

    golden_path = DATA.parent / "golden_set.jsonl"  # committed to git, not under data/
    golden_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in labels) + "\n",
        encoding="utf-8",
    )
    thresholds_path = DATA.parent / "thresholds.json"
    thresholds_path.write_text(
        json.dumps(
            {
                "near_dup_cosine": args.near_dup,
                "event_cosine": args.event,
                "near_dup_precision": round(dup_p, 3),
                "near_dup_recall": round(dup_r, 3),
                "event_precision": round(ev_p, 3),
                "event_recall": round(ev_r, 3),
                "labeled_pairs": len(labels),
                "decided_by": args.decided_by or "(미기록)",
                "decided_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n확정: near-dup >= {args.near_dup} (P={dup_p:.2f} R={dup_r:.2f}), "
          f"event >= {args.event} (P={ev_p:.2f} R={ev_r:.2f})")
    print(f"저장 -> {golden_path}, {thresholds_path}")
    print("이 둘은 커밋 대상(data/ 밖). THRESHOLDS.md에 근거를 적어 같이 커밋하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
