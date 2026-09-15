"""B3 step 3b (optional) — LLM pre-labels candidates so a human only has to
spot-check/correct instead of judging every pair from scratch.

This weakens the "no AI judging AI" guarantee B3 was designed around — see
README.md. Use label_cli.py --review afterward to accept/override each
AI label; the final threshold decision (calibrate_thresholds.py --commit)
still needs a human to actually look at the results.

Resumable: skips pairs that already have ANY label (human or AI) in
data/{tag}_labels.jsonl.

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/auto_label.py --tag op
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parents[2]  # MINT_Backend/
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="op")
    args = ap.parse_args()
    prefix = f"{args.tag}_" if args.tag else ""

    candidates_path = DATA / f"{prefix}candidates.jsonl"
    corpus_path = DATA / f"{prefix}corpus.jsonl"
    labels_path = DATA / f"{prefix}labels.jsonl"

    candidates = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line]
    corpus_by_id = {
        row["id"]: row for row in (
            json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line
        )
    }

    done: set[tuple[str, str]] = set()
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            done.add((row["a_id"], row["b_id"]))

    remaining = [c for c in candidates if (c["a_id"], c["b_id"]) not in done]
    print(f"{len(done)} already labeled, {len(remaining)} to auto-label")

    from app.services.llm_client import get_llm_client

    client = get_llm_client()
    print(f"using {client.__class__.__name__}")

    with labels_path.open("a", encoding="utf-8") as out:
        for idx, pair in enumerate(remaining, 1):
            a = corpus_by_id.get(pair["a_id"], {})
            b = corpus_by_id.get(pair["b_id"], {})
            try:
                result = client.classify_pair_relation(
                    pair["a_title"], a.get("summary", ""), pair["b_title"], b.get("summary", "")
                )
                label = result.get("label") or "unrelated"
                if label not in ("near_dup", "event", "unrelated"):
                    label = "unrelated"
                reason = result.get("reason", "")
            except Exception as exc:  # noqa: BLE001 — one bad pair shouldn't stop the batch
                label, reason = "unrelated", f"(분류 실패, 기본값 unrelated: {exc})"

            record = {**pair, "label": label, "source": "ai", "reason": reason}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{idx}/{len(remaining)}  cosine={pair['cosine']}  -> {label}  ({reason[:60]})")
            time.sleep(0.1)

    print(f"\n저장 -> {labels_path}")
    print("사람 검토: label_cli.py --tag", args.tag, "--review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
