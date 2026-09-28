"""Extract tenant identity from verified JWT on MCP tool calls."""
from typing import Dict, Optional

from common.jwt_verifier import resolve_tenant_from_headers


def extract_tenant(headers: Dict[str, str]) -> Optional[str]:
    try:
        return resolve_tenant_from_headers(headers)
    except PermissionError:
        return None
