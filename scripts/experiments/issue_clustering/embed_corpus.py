"""Step 2 — embed the corpus with Amazon Bedrock.

Default model: cohere.embed-multilingual-v3 (batched, strong on Korean).
Fallback:      amazon.titan-embed-text-v2:0  (--model, one text per call).

Output: data/embeddings.npy   float32 [N, D], L2-normalized, row order == data/embed_ids.json

Usage:
  .venv/bin/python scripts/experiments/issue_clustering/embed_corpus.py
  .venv/bin/python scripts/experiments/issue_clustering/embed_corpus.py --region us-east-1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parents[2]  # MINT_Backend/
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.bedrock_runtime import create_bedrock_runtime_client  # noqa: E402


def embed_text(row: dict) -> str:
    title = row.get("title", "").strip()
    summary = row.get("summary", "").strip()
    text = f"{title}\n{summary}" if summary else title
    return text[:1800]


def embed_cohere(client, model: str, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for start in range(0, len(texts), 90):
        batch = texts[start : start + 90]
        body = json.dumps({"texts": batch, "input_type": "clustering", "truncate": "END"})
        resp = client.invoke_model(modelId=model, body=body)
        payload = json.loads(resp["body"].read())
        emb = payload["embeddings"]
        if isinstance(emb, dict):  # embedding_types response shape
            emb = emb.get("float") or next(iter(emb.values()))
        out.extend(emb)
        print(f"  embedded {min(start + 90, len(texts))}/{len(texts)}")
        time.sleep(0.2)
    return out


def embed_titan(client, model: str, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i, text in enumerate(texts, 1):
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        resp = client.invoke_model(modelId=model, body=body)
        payload = json.loads(resp["body"].read())
        out.append(payload["embedding"])
        if i % 25 == 0 or i == len(texts):
            print(f"  embedded {i}/{len(texts)}")
        time.sleep(0.05)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="cohere.embed-multilingual-v3")
    ap.add_argument("--region", default=None, help="override AWS_REGION for this call")
    args = ap.parse_args()

    rows = [json.loads(line) for line in (DATA / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if line]
    texts = [embed_text(r) for r in rows]
    print(f"embedding {len(texts)} articles with {args.model}"
          + (f" in {args.region}" if args.region else ""))

    settings = get_settings()
    try:
        client = create_bedrock_runtime_client(settings, region=args.region)
        if args.model.startswith("cohere."):
            vectors = embed_cohere(client, args.model, texts)
        else:
            vectors = embed_titan(client, args.model, texts)
    except Exception as exc:  # noqa: BLE001
        print(f"\nBedrock call failed: {exc.__class__.__name__}: {exc}")
        print("Hints: try  --region us-east-1  or  --model amazon.titan-embed-text-v2:0")
        return 1

    mat = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms

    np.save(DATA / "embeddings.npy", mat)
    (DATA / "embed_ids.json").write_text(
        json.dumps([r["id"] for r in rows], ensure_ascii=False), encoding="utf-8"
    )
    (DATA / "embed_meta.json").write_text(
        json.dumps({"model": args.model, "region": args.region or settings.aws_region,
                    "count": len(rows), "dim": int(mat.shape[1])}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nsaved embeddings [{mat.shape[0]}, {mat.shape[1]}] -> {DATA / 'embeddings.npy'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
