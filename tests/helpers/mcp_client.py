"""MCP client for platform tests (Streamable HTTP + RS256 bearer)."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
import pytest

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088")
MCP_HOST_HEADER = os.environ.get("MCP_HOST_HEADER", "mcp.localhost")

try:
    from mcp import ClientSession  # noqa: E402
    from mcp.client.streamable_http import streamable_http_client  # noqa: E402
except ImportError:
    # Repo top-level mcp/ is a namespace that can shadow the SDK on sys.path.
    pytest.skip("mcp Python SDK not importable", allow_module_level=True)

from tests.helpers.tokens import bearer_for  # noqa: E402


def _authorization_for(tenant_id: str) -> str:
    for key in (tenant_id, tenant_id.replace("_", "-"), tenant_id.replace("-", "_")):
        try:
            return bearer_for(key)
        except KeyError:
            continue
    pytest.skip(
        f"No bearer for tenant {tenant_id!r} in ZELKOR_TEST_TOKENS "
        "(mint with zelkor token mint on the test cluster)"
    )


class MCPGatewayClient:
    def __init__(
        self,
        tenant_id: str,
        *,
        base_url: str = GATEWAY_BASE_URL,
        host_header: str = MCP_HOST_HEADER,
    ) -> None:
        self.tenant_id = tenant_id
        self.mcp_url = f"{base_url.rstrip('/')}/mcp"
        self._host_header = host_header
        self._auth = _authorization_for(tenant_id)

    def _http_headers(self) -> dict[str, str]:
        return {
            "Host": self._host_header,
            "Authorization": self._auth,
            "Accept": "application/json, text/event-stream",
        }

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        timeout = httpx.Timeout(120.0, connect=30.0)
        async with httpx.AsyncClient(
            headers=self._http_headers(),
            timeout=timeout,
        ) as http_client:
            try:
                async with streamable_http_client(self.mcp_url, http_client=http_client) as streams:
                    read_stream, write_stream, _ = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
            except httpx.ConnectError as exc:
                raise ConnectionError(f"MCP not reachable at {self.mcp_url}") from exc
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    raise ConnectionError(f"MCP not published at {self.mcp_url}") from exc
                raise

    def list_tools(self) -> List[Dict[str, Any]]:
        async def _run() -> List[Dict[str, Any]]:
            async with self._session() as session:
                result = await session.list_tools()
                return [t.model_dump(mode="json") for t in result.tools]

        return asyncio.run(_run())

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        args = dict(arguments or {})

        async def _run() -> Any:
            async with self._session() as session:
                result = await session.call_tool(name, args)
                if result.isError:
                    text = ""
                    if result.content and getattr(result.content[0], "text", None):
                        text = result.content[0].text
                    raise RuntimeError(text or "tool call failed")
                content = result.content or []
                if content and getattr(content[0], "text", None):
                    return json.loads(content[0].text)
                return result

        try:
            return asyncio.run(_run())
        except BaseExceptionGroup as exc:
            # anyio TaskGroup wraps tool RuntimeError; admission tests assert RuntimeError.
            cur: BaseException = exc
            while isinstance(cur, BaseExceptionGroup) and len(cur.exceptions) == 1:
                cur = cur.exceptions[0]
            raise cur from exc
