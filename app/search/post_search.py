from __future__ import annotations

import logging
import re
from datetime import datetime
from uuid import UUID

from app.core.config import get_settings
from app.search.es_client import get_es_client
from app.search.post_search_query import PostSearchFilters, search_posts

logger = logging.getLogger(__name__)


def get_post_embedding(post_id: UUID) -> list[float] | None:
    """Fetch a post's B0-computed embedding straight from its ES document."""
    settings = get_settings()
    if not settings.search_uses_elasticsearch:
        return None
    client = get_es_client()
    if client is None:
        return None
    try:
        response = client.get(
            index=settings.elasticsearch_index_posts,
            id=str(post_id),
            source=["embedding"],
        )
        if not response.get("found"):
            return None
        return (response.get("_source") or {}).get("embedding")
    except Exception as exc:
        logger.debug("get_post_embedding failed for %s: %s", post_id, exc)
        return None


def knn_similar_post_ids(
    organization_id: UUID,
    post_id: UUID,
    embedding: list[float],
    *,
    since: datetime,
    until: datetime,
    k: int = 20,
) -> list[tuple[UUID, float]]:
    """Nearest posts by embedding, same org, published within [since, until], excluding self.

    Used by issue assignment (B4) — not a general search entry point.
    """
    settings = get_settings()
    if not settings.search_uses_elasticsearch:
        return []
    client = get_es_client()
    if client is None:
        return []
    try:
        response = client.search(
            index=settings.elasticsearch_index_posts,
            knn={
                "field": "embedding",
                "query_vector": embedding,
                "k": k,
                "num_candidates": max(k * 5, 50),
                "filter": [
                    {"term": {"organization_id": str(organization_id)}},
                    {"range": {"published_at": {"gte": since.isoformat(), "lte": until.isoformat()}}},
                    {"bool": {"must_not": [{"term": {"status": "deleted"}}, {"term": {"status": "hidden"}}]}},
                ],
            },
            size=k + 1,
            source=["post_id"],
        )
        out: list[tuple[UUID, float]] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            raw_id = source.get("post_id") or hit.get("_id")
            if not raw_id or str(raw_id) == str(post_id):
                continue
            out.append((UUID(str(raw_id)), float(hit.get("_score", 0.0))))
        return out
    except Exception as exc:
        logger.warning("knn_similar_post_ids failed: %s", exc)
        return []


def search_post_ids(
    organization_id: UUID,
    query: str,
    *,
    limit: int = 50,
    min_token_len: int = 1,
) -> list[UUID]:
    text = query.strip()
    if len(text) < min_token_len:
        return []
    result = search_posts(
        PostSearchFilters(
            organization_id=organization_id,
            query=text,
            exclude_statuses=["deleted"],
        ),
        page=1,
        size=limit,
    )
    if not result:
        return []
    return [hit.post_id for hit in result.hits]


def search_post_ids_for_chat(
    organization_id: UUID,
    query: str,
    *,
    limit: int = 8,
    min_token_len: int = 2,
) -> list[UUID]:
    """BM25 + importance/recency boost for chatbot retrieval."""
    settings = get_settings()
    if not settings.search_uses_elasticsearch:
        return []

    client = get_es_client()
    if client is None:
        return []

    question = query.strip()
    if len(question) < min_token_len:
        return []

    try:
        response = client.search(
            index=settings.elasticsearch_index_posts,
            size=limit,
            query={
                "function_score": {
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"organization_id": str(organization_id)}},
                                {
                                    "bool": {
                                        "must_not": [
                                            {"term": {"status": "deleted"}},
                                            {"term": {"status": "hidden"}},
                                        ]
                                    }
                                },
                            ],
                            "must": [
                                {
                                    "multi_match": {
                                        "query": question,
                                        "fields": [
                                            "title^3",
                                            "summary^2",
                                            "body",
                                            "impact",
                                            "keyword_names",
                                        ],
                                        "type": "best_fields",
                                        "operator": "or",
                                    }
                                }
                            ],
                        }
                    },
                    "functions": [
                        {"filter": {"term": {"importance": "high"}}, "weight": 2.0},
                        {"filter": {"term": {"importance": "medium"}}, "weight": 1.3},
                        {
                            "gauss": {
                                "collected_at": {
                                    "origin": "now",
                                    "scale": "30d",
                                    "offset": "2d",
                                    "decay": 0.5,
                                }
                            },
                            "weight": 1.5,
                        },
                    ],
                    "score_mode": "sum",
                    "boost_mode": "multiply",
                }
            },
            _source=["post_id"],
        )
        ids: list[UUID] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            raw_id = source.get("post_id") or hit.get("_id")
            if raw_id:
                ids.append(UUID(str(raw_id)))
        return ids
    except Exception as exc:
        logger.warning("ES chat search failed: %s", exc)
        return search_post_ids(
            organization_id,
            query,
            limit=limit,
            min_token_len=min_token_len,
        )
