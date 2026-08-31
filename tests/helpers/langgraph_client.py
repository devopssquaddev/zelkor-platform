"""Stock langgraph_sdk client pointed at the Zelkor Aegra front door.

Constructor-only env wiring (url, Bearer, optional Host / X-Graph-ID).
Not a Zelkor SDK — northbound calls stay langgraph_sdk.
"""
from __future__ import annotations

import os
from typing import Any

from langgraph_sdk import get_client

_DEFAULT_TENANT = "tenant-a"


def aegra_sdk_client(*, tenant_id: str = _DEFAULT_TENANT, graph_id: str | None = None) -> Any:
    token = os.environ.get("AEGRA_AUTH_TOKEN") if tenant_id == _DEFAULT_TENANT else None
    headers = {
        "Authorization": f"Bearer {token or f'dev:{tenant_id}'}",
        "Host": os.environ.get("AEGRA_HOST_HEADER", "aegra.localhost"),
    }
    if graph_id:
        headers["X-Graph-ID"] = graph_id
    return get_client(
        url=os.environ.get("GATEWAY_BASE_URL", "http://127.0.0.1:8088"),
        api_key=None,
        headers=headers,
    )
