"""zelkor-mcp image dependencies (no cluster).

mcp-server-qdrant pins fastmcp==2.7.0 (CVE-2026-32871, FastMCP OpenAPI provider SSRF). The Qdrant
tool uses only its connector and embedding modules, which do not import fastmcp, so the image
installs mcp-server-qdrant without dependencies and pins the ones those modules need.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "images" / "mcp" / "Dockerfile").read_text()
REQUIREMENTS = (ROOT / "images" / "mcp" / "requirements.txt").read_text()


def _names(text: str) -> set[str]:
    names = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0].lower())
    return names


def test_mcp_image_does_not_install_fastmcp():
    assert "fastmcp" not in _names(REQUIREMENTS)
    assert not re.search(r"pip install[^\n]*fastmcp", DOCKERFILE, re.IGNORECASE)
    assert "! pip show fastmcp" in DOCKERFILE  # the build fails if a dependency brings it back


def test_mcp_server_qdrant_installed_without_dependencies():
    assert "mcp-server-qdrant" not in _names(REQUIREMENTS)
    assert re.search(r"pip install --no-deps mcp-server-qdrant==\d+\.\d+\.\d+", DOCKERFILE)


def test_qdrant_connector_dependencies_are_pinned():
    pins = {line.split("==")[0].lower() for line in REQUIREMENTS.splitlines() if "==" in line}
    assert {"fastembed", "qdrant-client", "pydantic"} <= pins
