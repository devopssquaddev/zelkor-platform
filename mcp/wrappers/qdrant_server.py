"""Zelkor qdrant MCP security wrapper (CE).

In-process wrap of official mcp-server-qdrant below the FastMCP tool schema.
Public tools: search_documents, upsert_document. Isolation is a tenant payload
filter/stamp, then a post-filter. Embeddings go through Envoy AI Gateway.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

logger = logging.getLogger("zelkor-qdrant-mcp")

QDRANT_URL = os.getenv("QDRANT_MCP_URL", "").rstrip("/")
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "").rstrip("/")
DEFAULT_EMBEDDING_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-3-small")
AI_GATEWAY_API_KEY = os.getenv("AI_GATEWAY_API_KEY", "")


def _json_request(url: str, body: dict, headers: Optional[Dict[str, str]] = None, timeout: int = 5) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_embedding(text: str) -> Optional[list]:
    try:
        data = _json_request(
            f"{AI_GATEWAY_URL}/embeddings",
            {"model": DEFAULT_EMBEDDING_MODEL, "input": text},
            headers={"Authorization": f"Bearer {AI_GATEWAY_API_KEY}"},
        )
        return data["data"][0]["embedding"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError) as exc:
        logger.info("Embedding unavailable (%s)", exc)
        return None


class GatewayEmbeddingProvider:
    """EmbeddingProvider that calls Envoy AI Gateway, not FastEmbed or a provider key."""

    def __init__(self, vector_size: int = 1536):
        self._vector_size = vector_size

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [self._embed_sync(doc) for doc in documents]

    async def embed_query(self, query: str) -> list[float]:
        return self._embed_sync(query)

    def _embed_sync(self, text: str) -> list[float]:
        vector = _get_embedding(text)
        if not vector:
            raise RuntimeError("AI Gateway embeddings unavailable")
        self._vector_size = len(vector)
        return vector

    def get_vector_name(self) -> str:
        # Unnamed/default vector — matches CE collections that are not FastEmbed-named.
        return ""

    def get_vector_size(self) -> int:
        return self._vector_size


def _tenant_filter(models, tenant_id: str):
    return models.Filter(
        must=[
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            )
        ]
    )


def _payloads_from_entries(entries, tenant_id: str) -> list:
    docs = []
    for entry in entries:
        metadata = entry.metadata if getattr(entry, "metadata", None) else {}
        payload = dict(metadata) if isinstance(metadata, dict) else {}
        if "document" not in payload and getattr(entry, "content", None) is not None:
            payload["document"] = entry.content
        if payload.get("tenant_id") == tenant_id:
            docs.append(payload)
        elif not payload.get("tenant_id") and tenant_id:
            # Official core nests metadata; stamp/check after merge.
            continue
    return docs


def _payloads_from_points(points: list, tenant_id: str) -> list:
    docs = []
    for point in points:
        payload = point.get("payload") or getattr(point, "payload", None) or {}
        if hasattr(payload, "items") and not isinstance(payload, dict):
            payload = dict(payload)
        nested = payload.get("metadata") if isinstance(payload, dict) else None
        tenant = None
        if isinstance(payload, dict):
            tenant = payload.get("tenant_id")
            if tenant is None and isinstance(nested, dict):
                tenant = nested.get("tenant_id")
                payload = {**nested, **{k: v for k, v in payload.items() if k != "metadata"}}
        if tenant == tenant_id:
            docs.append(payload)
    return docs


def _search_with_connector(query: str, collection: str, limit: int, tenant_id: str) -> Optional[list]:
    try:
        from mcp_server_qdrant.embeddings.base import EmbeddingProvider
        from mcp_server_qdrant.qdrant import QdrantConnector
        from qdrant_client import models
    except ImportError as exc:
        logger.info("mcp-server-qdrant not installed (%s); skipping connector search", exc)
        return None

    class _Provider(GatewayEmbeddingProvider, EmbeddingProvider):
        pass

    async def _run():
        connector = QdrantConnector(
            qdrant_url=QDRANT_URL or None,
            qdrant_api_key=None,
            collection_name=collection,
            embedding_provider=_Provider(),
        )
        filt = _tenant_filter(models, tenant_id)
        try:
            entries = await connector.search(
                query,
                collection_name=collection,
                limit=limit,
                query_filter=filt,
            )
            docs = _payloads_from_entries(entries, tenant_id)
            if docs:
                return docs
        except Exception as exc:
            logger.info("Connector named-vector search failed (%s); trying default vector", exc)

        try:
            query_vector = await connector._embedding_provider.embed_query(query)
            result = await connector._client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                query_filter=filt,
            )
            points = getattr(result, "points", None) or []
            raw = []
            for point in points:
                payload = getattr(point, "payload", None) or {}
                raw.append({"payload": dict(payload) if payload else {}})
            return _payloads_from_points(raw, tenant_id)
        except Exception as exc:
            logger.info("Connector default-vector search failed (%s)", exc)
            return None

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.info("Connector search unavailable (%s)", exc)
        return None


def _scroll_tenant(collection: str, limit: int, tenant_id: str) -> list:
    try:
        from qdrant_client import QdrantClient, models
    except ImportError:
        return []
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=5)
        filt = _tenant_filter(models, tenant_id)
        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=filt,
            limit=limit,
            with_payload=True,
        )
        raw = [{"payload": dict(getattr(p, "payload", None) or {})} for p in points]
        return _payloads_from_points(raw, tenant_id)[:limit]
    except Exception as exc:
        logger.warning("Qdrant scroll failed: %s", exc)
        return []


def _require_tenant(arguments: dict, tenant_id: str) -> None:
    arg_tenant = arguments.get("tenant_id")
    if not arg_tenant or arg_tenant != tenant_id:
        raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")


def stamp_upsert_payload(metadata: Optional[dict], content: str, tenant_id: str) -> dict:
    payload = dict(metadata) if isinstance(metadata, dict) else {}
    payload.pop("tenant_id", None)
    payload["document"] = content
    payload["tenant_id"] = tenant_id
    return payload


def _ensure_collection(client, models, collection: str, vector_size: int) -> None:
    try:
        client.get_collection(collection)
        return
    except Exception:
        pass
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def _store_document(content: str, collection: str, tenant_id: str, metadata: Optional[dict] = None) -> dict:
    """Upsert one point. Always stamps payload.tenant_id = caller."""
    import uuid

    from qdrant_client import QdrantClient, models

    vector = _get_embedding(content)
    if not vector:
        raise RuntimeError("AI Gateway embeddings unavailable")
    payload = stamp_upsert_payload(metadata, content, tenant_id)
    point_id = str(uuid.uuid4())
    client = QdrantClient(url=QDRANT_URL, timeout=10)
    _ensure_collection(client, models, collection, len(vector))
    client.upsert(
        collection_name=collection,
        points=[models.PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return {"id": point_id, "collection": collection, "tenant_id": payload["tenant_id"]}


class QdrantMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "search_documents",
                "description": (
                    "Tenant-scoped vector search over a Qdrant collection. "
                    "Always filters payload tenant_id to the authenticated caller. "
                    "collection defaults to QDRANT_COLLECTION."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "collection": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query", "tenant_id"],
                },
            },
            {
                "name": "upsert_document",
                "description": (
                    "Upsert one document into a Qdrant collection. "
                    "payload.tenant_id is forced to the authenticated caller."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "document": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "collection": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["tenant_id"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        _require_tenant(arguments, tenant_id)
        collection = arguments.get("collection") or DEFAULT_COLLECTION
        if name == "search_documents":
            query = arguments.get("query") or ""
            limit = int(arguments.get("limit") or 3)
            docs = _search_with_connector(query, collection, limit, tenant_id)
            if docs is None:
                docs = _scroll_tenant(collection, limit, tenant_id)
            docs = [d for d in (docs or []) if (d.get("tenant_id") == tenant_id)]
            return {"documents": docs, "count": len(docs), "collection": collection}
        if name == "upsert_document":
            content = arguments.get("content") or arguments.get("document") or ""
            if not str(content).strip():
                raise ValueError("content or document is required")
            return _store_document(str(content), collection, tenant_id, arguments.get("metadata"))
        raise ValueError(f"Unknown tool: {name}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(QdrantMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
