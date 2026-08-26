"""
Zelkor qdrant MCP security wrapper (CE).
Injects mandatory tenant_id payload filter on vector search.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant

QDRANT_URL = os.getenv("QDRANT_MCP_URL", "http://zelkor-platform-qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "finserve_policies")
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://envoy-default-zelkor-platform-gateway.default.svc:80/v1")
DEFAULT_EMBEDDING_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-3-small")

SEED_POLICIES = [
    {"id": 1, "tenant_id": "Bank_Alpha", "title": "High-Growth Tech Allocation Policy", "category": "asset_allocation",
     "content": "Bank_Alpha Policy: Maximum 40% allocation to high-growth tech equities (e.g. NVDA, AAPL, MSFT). Mandatory 15% cash hedge."},
    {"id": 2, "tenant_id": "Bank_Alpha", "title": "Risk Disclosure & Volatility Limits", "category": "risk_disclosure",
     "content": "Bank_Alpha Risk Disclosure: Portfolio maximum drawdown limit is 12%. Rebalancing triggered when variance exceeds 5%."},
    {"id": 3, "tenant_id": "Bank_Beta", "title": "Conservative Asset Allocation Policy", "category": "asset_allocation",
     "content": "Bank_Beta Policy: Maximum 15% allocation to tech sector. Strict conservative allocation requiring 60% fixed income (BND) and 10% commodities (GLD)."},
    {"id": 4, "tenant_id": "Bank_Beta", "title": "Risk Disclosure & ESG Mandate", "category": "risk_disclosure",
     "content": "Bank_Beta Risk Disclosure: Conservative ESG mandate. Zero exposure to non-ESG compliant derivatives."},
]


def _get_embedding(text: str) -> list:
    try:
        payload = json.dumps({"model": DEFAULT_EMBEDDING_MODEL, "input": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{AI_GATEWAY_URL}/embeddings",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer dev-key"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"][0]["embedding"]
    except Exception:
        return [0.1, 0.2, 0.3, 0.4]


class QdrantMCPServer(MCPToolHandler):
    def list_tools(self):
        return [
            {
                "name": "search_documents",
                "description": "Tenant-scoped semantic search over policy documents",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "tenant_id": {"type": "string"},
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
        vector = _get_embedding(query)

        search_body = {
            "vector": vector[:4] if len(vector) >= 4 else vector,
            "limit": limit,
            "filter": {"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]},
            "with_payload": True,
        }
        try:
            req = urllib.request.Request(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                data=json.dumps(search_body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                hits = json.loads(resp.read().decode("utf-8")).get("result") or []
                docs = []
                for hit in hits:
                    payload = hit.get("payload") or {}
                    if payload.get("tenant_id") == tenant_id:
                        docs.append(payload)
                if docs:
                    return {"documents": docs, "count": len(docs)}
        except Exception:
            pass

        query_lower = query.lower()
        fallback = []
        for p in SEED_POLICIES:
            if p["tenant_id"] != tenant_id:
                continue
            if any(w in query_lower for w in ["policy", "allocation", "risk", "tech", "guideline"]) or not query_lower.strip():
                fallback.append(p)
        return {"documents": fallback[:limit], "count": len(fallback), "source": "seed_fallback"}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    run_mcp_server(QdrantMCPServer(), extract_tenant, port=int(os.getenv("PORT", "8080")))
