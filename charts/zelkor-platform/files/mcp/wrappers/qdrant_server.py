"""Zelkor qdrant MCP security wrapper (CE).

Vector search against a configured collection. Always injects a payload
filter on tenant_id from the authenticated caller. Collection and
embedding settings come from env / tool args, not a demo schema.
"""
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, Optional

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
        logger.info("Embedding unavailable (%s); falling back to tenant-filtered scroll", exc)
        return None


def _tenant_filter(tenant_id: str) -> dict:
    return {"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]}


def _payloads(points: list, tenant_id: str) -> list:
    docs = []
    for point in points:
        payload = point.get("payload") or {}
        if payload.get("tenant_id") == tenant_id:
            docs.append(payload)
    return docs


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
            }
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if name != "search_documents":
            raise ValueError(f"Unknown tool: {name}")

        query = arguments.get("query") or ""
        arg_tenant = arguments.get("tenant_id")
        if not arg_tenant or arg_tenant != tenant_id:
            raise PermissionError(f"tenant_id mismatch: header={tenant_id}, arg={arg_tenant}")

        limit = int(arguments.get("limit") or 3)
        collection = arguments.get("collection") or DEFAULT_COLLECTION
        filt = _tenant_filter(tenant_id)

        vector = _get_embedding(query)
        if vector:
            try:
                data = _json_request(
                    f"{QDRANT_URL}/collections/{collection}/points/search",
                    {
                        "vector": vector,
                        "limit": limit,
                        "filter": filt,
                        "with_payload": True,
                    },
                )
                docs = _payloads(data.get("result") or [], tenant_id)
                if docs:
                    return {"documents": docs, "count": len(docs), "collection": collection}
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                logger.info("Vector search failed (%s); falling back to scroll", exc)

        try:
            data = _json_request(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                {"filter": filt, "limit": limit, "with_payload": True},
            )
            points = (data.get("result") or {}).get("points") or []
            docs = _payloads(points, tenant_id)[:limit]
            return {"documents": docs, "count": len(docs), "collection": collection}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Qdrant scroll failed: %s", exc)
            return {"documents": [], "count": 0, "collection": collection, "error": str(exc)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(QdrantMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
