"""B3 CI regression: the near-dup/event cosine thresholds must keep meeting
the precision/recall bar measured on the human-labeled golden set.

Skips (not fails) until B3's golden_set.jsonl / thresholds.json are
committed — see scripts/experiments/issue_clustering/calibrate_thresholds.py.
"""
import json
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN = _ROOT / "scripts/experiments/issue_clustering/golden_set.jsonl"
_THRESHOLDS = _ROOT / "scripts/experiments/issue_clustering/thresholds.json"


def _prf(labels: list[dict], threshold: float, positive_labels: set[str]) -> tuple[float, float]:
    tp = fp = fn = 0
    for row in labels:
        predicted_positive = row["cosine"] >= threshold
        actual_positive = row["label"] in positive_labels
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and actual_positive:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


@unittest.skipUnless(
    _GOLDEN.is_file() and _THRESHOLDS.is_file(),
    "B3 golden set not committed yet (data-science task, not code) — "
    "see scripts/experiments/issue_clustering/README.md",
)
class GoldenClusteringThresholdsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = [
            json.loads(line) for line in _GOLDEN.read_text(encoding="utf-8").splitlines() if line
        ]
        self.thresholds = json.loads(_THRESHOLDS.read_text(encoding="utf-8"))

    def test_near_dup_threshold_meets_recorded_bar(self) -> None:
        precision, recall = _prf(self.labels, self.thresholds["near_dup_cosine"], {"near_dup"})
        self.assertGreaterEqual(precision, self.thresholds["near_dup_precision"] - 0.02)
        self.assertGreaterEqual(recall, self.thresholds["near_dup_recall"] - 0.02)

    def test_event_threshold_meets_recorded_bar(self) -> None:
        precision, recall = _prf(
            self.labels, self.thresholds["event_cosine"], {"near_dup", "event"}
        )
        self.assertGreaterEqual(precision, self.thresholds["event_precision"] - 0.02)
        self.assertGreaterEqual(recall, self.thresholds["event_recall"] - 0.02)


if __name__ == "__main__":
    unittest.main()
