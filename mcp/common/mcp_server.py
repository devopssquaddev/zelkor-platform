"""MCP Streamable HTTP server (mcp SDK) for native Zelkor backends."""
import json
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import anyio

logger = logging.getLogger("zelkor-mcp")

MAX_BODY_BYTES = int(os.getenv("MCP_MAX_BODY_BYTES", "1048576"))
MAX_CONCURRENT_REQUESTS = int(os.getenv("MCP_MAX_CONCURRENT_REQUESTS", "32"))
TOOL_DEADLINE_S = min(float(os.getenv("MCP_TOOL_DEADLINE_SECONDS", "100")), 110.0)
METRICS_PORT = int(os.getenv("MCP_METRICS_PORT", "9090"))

try:
    from prometheus_client import start_http_server
except ImportError:
    start_http_server = None  # type: ignore


class MCPToolHandler:
    def list_tools(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def call_tool(self, name: str, arguments: Dict[str, Any], tenant_id: Optional[str]) -> Any:
        raise NotImplementedError


def _reject_stray_tenant_id(arguments: dict) -> None:
    if "tenant_id" in arguments:
        raise PermissionError("tenant_id argument is not allowed")


def build_starlette_app(
    tool_handler: MCPToolHandler,
    tenant_extractor: Callable[[Dict[str, str]], Optional[str]],
    server_name: str = "zelkor-mcp",
):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    except ImportError as exc:
        raise RuntimeError("mcp package is required") from exc

    mcp_server = Server(server_name)
    limiter = anyio.CapacityLimiter(MAX_CONCURRENT_REQUESTS)
    manager = StreamableHTTPSessionManager(
        mcp_server,
        stateless=True,
        json_response=True,
        max_request_body_size=MAX_BODY_BYTES,
    )

    def _headers() -> Dict[str, str]:
        ctx = mcp_server.request_context
        return {k.decode(): v.decode() for k, v in ctx.request.headers.raw}

    @mcp_server.list_tools()
    async def _list_tools() -> list:
        tools = tool_handler.list_tools()
        tenant_id = tenant_extractor(_headers())
        logger.info(
            "tools/list count=%s",
            len(tools),
            extra={"event": "tools_list", "tenant_id": tenant_id or ""},
        )
        return [
            types.Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema") or {"type": "object", "properties": {}},
            )
            for t in tools
        ]

    @mcp_server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list:
        tenant_id = tenant_extractor(_headers())
        if not tenant_id:
            exc = PermissionError("Missing tenant identity in Authorization")
            logger.warning(
                "MCP permission denied: %s",
                exc,
                extra={"event": "tools_call", "tenant_id": ""},
            )
            raise exc
        args = dict(arguments or {})
        try:
            _reject_stray_tenant_id(args)
            with anyio.fail_after(TOOL_DEADLINE_S):
                result = await anyio.to_thread.run_sync(
                    tool_handler.call_tool,
                    name,
                    args,
                    tenant_id,
                    limiter=limiter,
                )
        except PermissionError as exc:
            logger.warning(
                "MCP permission denied: %s",
                exc,
                extra={"event": "tools_call", "tenant_id": tenant_id or ""},
            )
            raise
        logger.info(
            "tools/call %s",
            name,
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
        text = json.dumps(result) if not isinstance(result, str) else result
        return [types.TextContent(type="text", text=text)]

    # Starlette Route treats bare functions as request→response; a callable
    # instance is required so exact /mcp is ASGI (no Mount 307 to /mcp/).
    class _MCPASGI:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def ready(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ready"})

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/healthz", health, methods=["GET"]),
            Route("/ready", ready, methods=["GET"]),
            Route("/mcp", endpoint=_MCPASGI(), methods=["POST", "GET", "DELETE"]),
        ],
        lifespan=lifespan,
    )


def _configure_logging() -> None:
    try:
        from zelkor_logging import configure_logging
    except ImportError:
        extra = Path(__file__).resolve().parents[2] / "images" / "common"
        if extra.is_dir() and str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
        from zelkor_logging import configure_logging
    configure_logging(os.getenv("ZELKOR_LOG_COMPONENT", "zelkor-mcp"))


def run_mcp_server(
    tool_handler: MCPToolHandler,
    tenant_extractor: Callable[[Dict[str, str]], Optional[str]],
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    import uvicorn

    _configure_logging()
    if start_http_server is not None:
        start_http_server(METRICS_PORT)

    app = build_starlette_app(tool_handler, tenant_extractor)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _shutdown(signum, _frame):
        logger.info("MCP server shutdown signal=%s", signum, extra={"event": "shutdown"})
        server.should_exit = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    logger.info(
        "MCP server listening on %s:%s metrics=%s",
        host,
        port,
        METRICS_PORT,
        extra={"event": "startup"},
    )
    server.run()
