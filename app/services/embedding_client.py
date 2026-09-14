"""Bedrock Cohere embedding client — posts semantic index (issue radar B0)."""
from __future__ import annotations

import json
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def embed_text(text: str, *, input_type: str = "search_document") -> list[float] | None:
    """Embed one text with Bedrock `cohere.embed-multilingual-v3`.

    Raises on transient failure so callers relying on the search-index outbox
    (app.search.index_outbox) get the same retry/give-up behavior as any
    other Elasticsearch write failure. Returns None only when there is no
    text to embed.
    """
    clean = (text or "").strip()
    if not clean:
        return None

    settings = get_settings()
    model_id = (settings.bedrock_embedding_model or "").strip()
    if not model_id:
        return None

    from app.services.bedrock_runtime import create_bedrock_runtime_client

    region = (settings.bedrock_embedding_region or settings.aws_region or "").strip()
    client = create_bedrock_runtime_client(settings, region=region)
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({"texts": [clean], "input_type": input_type, "truncate": "END"}),
        contentType="application/json",
        accept="application/json",
    )
    body = response.get("body")
    raw = body.read() if hasattr(body, "read") else body
    data = json.loads(raw)
    embeddings = data.get("embeddings") or []
    if not embeddings:
        logger.warning("Bedrock embedding returned no vectors (model=%s region=%s)", model_id, region)
        return None
    return embeddings[0]


def post_embedding_text(title: str, summary: str) -> str:
    title = (title or "").strip()
    summary = (summary or "").strip()
    if summary:
        return f"{title}\n{summary}"
    return title
