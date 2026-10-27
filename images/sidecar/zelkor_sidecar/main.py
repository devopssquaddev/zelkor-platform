"""zelkor-sidecar entrypoint: :8000 (pod network) + 127.0.0.1:8001 (loopback only)."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logger = logging.getLogger("zelkor-sidecar")


def build_bridge(runtime: str):
    runtime = (runtime or "").strip().lower()
    url = os.getenv("ZELKOR_RUNTIME_URL", "http://127.0.0.1:8080").rstrip("/")
    if runtime == "a2a":
        from .bridges.a2a import A2ABridge

        return A2ABridge(url)
    if runtime == "opencode":
        from .bridges.opencode import OpenCodeBridge

        return OpenCodeBridge(url)
    raise SystemExit(f"ZELKOR_RUNTIME must be a2a or opencode (got {runtime!r})")


async def serve() -> None:
    import uvicorn

    from .egress import Egress, EgressConfig
    from .inbound import Inbound, graph_id_from_env
    from .runs import RunExecutor, RunSlot
    from .store import PgStore
    from .tracing import Tracing

    from jwt_verifier import validate_startup_config  # flat copy from mcp/common

    validate_startup_config()
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    runtime = os.getenv("ZELKOR_RUNTIME", "")
    store = PgStore(dsn, max_size=int(os.getenv("ZELKOR_SIDECAR_DB_POOL", "5")))
    await store.open()
    bridge = build_bridge(runtime)
    tracing = Tracing.from_env()
    slot = RunSlot()
    executor = RunExecutor(store, bridge, slot, tracing, runtime=runtime)
    inbound = Inbound(store, executor, graph_id=graph_id_from_env(), ready=bridge.ready)
    apps = [inbound.app()]
    if os.getenv("ZELKOR_A2A_ENABLED", "false").strip().lower() in ("1", "true", "yes"):
        from .a2a_server import mount_a2a

        mount_a2a(apps[0], inbound)
    egress = Egress(slot, tracing, EgressConfig.from_env())
    log_config = None  # zelkor_logging owns the root logger
    servers = [
        uvicorn.Server(uvicorn.Config(apps[0], host="0.0.0.0", port=int(os.getenv("ZELKOR_SIDECAR_PORT", "8000")),
                                      log_config=log_config, access_log=False)),
        uvicorn.Server(uvicorn.Config(egress.app(), host="127.0.0.1",
                                      port=int(os.getenv("ZELKOR_EGRESS_PORT", "8001")),
                                      log_config=log_config, access_log=False)),
    ]
    logger.info("listening", extra={"event": "startup", "kind": runtime})
    try:
        await asyncio.gather(*(s.serve() for s in servers))
    finally:
        await bridge.close()
        await store.close()


def main() -> int:
    try:
        from zelkor_logging import configure_logging, install_probe_access_filter

        configure_logging("zelkor-sidecar")
        install_probe_access_filter()
    except ImportError:
        logging.basicConfig(level=os.getenv("ZELKOR_LOG_LEVEL", "INFO"))
    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
