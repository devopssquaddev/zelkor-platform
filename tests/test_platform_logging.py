"""Platform logging contract (no cluster)."""
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "images" / "common"))

from zelkor_logging import JsonFormatter, configure_logging, parse_format, parse_level  # noqa: E402

CHART = ROOT / "charts" / "zelkor-platform"
AGENT_CHART = ROOT / "charts" / "zelkor-agent"
FIRST_PARTY_TEMPLATES = [
    CHART / "templates/aegra/deployment.yaml",
    CHART / "templates/aegra/job-migrate.yaml",
    CHART / "templates/mcp/deployment-gateway.yaml",
    CHART / "templates/mcp/deployment-postgres.yaml",
    CHART / "templates/mcp/deployment-qdrant.yaml",
    CHART / "templates/mcp/deployment-egress.yaml",
    CHART / "templates/mcp/deployment-sandbox.yaml",
    CHART / "templates/guardrails/deployment.yaml",
    CHART / "templates/langfuse/job-surfaces-seed.yaml",
    AGENT_CHART / "templates/deployment.yaml",
]


def test_parse_level_defaults_and_aliases():
    assert parse_level("INFO") == logging.INFO
    assert parse_level("warn") == logging.WARNING
    assert parse_level("nope") == logging.INFO
    assert parse_level("") == logging.INFO


def test_parse_format_rejects_unknown():
    assert parse_format("json") == "json"
    assert parse_format("text") == "text"
    assert parse_format("xml") == "json"


def test_json_formatter_required_keys_and_optional_event():
    record = logging.LogRecord(
        name="zelkor-mcp-gateway",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="listening",
        args=(),
        exc_info=None,
    )
    record.component = "zelkor-mcp-gateway"
    record.event = "startup"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "zelkor-mcp-gateway"
    assert payload["message"] == "listening"
    assert payload["component"] == "zelkor-mcp-gateway"
    assert payload["event"] == "startup"
    assert "timestamp" in payload
    assert "Authorization" not in json.dumps(payload)


def test_configure_honors_error_level(monkeypatch, capsys):
    monkeypatch.setenv("ZELKOR_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("ZELKOR_LOG_FORMAT", "json")
    configure_logging("zelkor-test", force=True)
    log = logging.getLogger("zelkor-test")
    log.info("should-not-appear")
    log.error("boom")
    out = capsys.readouterr().out
    assert "should-not-appear" not in out
    line = json.loads(out.strip().splitlines()[-1])
    assert line["level"] == "ERROR"
    assert line["message"] == "boom"
    assert line["component"] == "zelkor-test"


def test_chart_default_is_info_json_not_debug():
    values = (CHART / "values.yaml").read_text()
    block = values.split("\nlogging:", 1)[1].split("\n\n", 1)[0]
    assert "level: INFO" in block
    assert "format: json" in block
    assert "DEBUG" not in block


def test_local_overlay_sets_debug():
    text = (ROOT / "profiles" / "values-local.yaml").read_text()
    assert "level: DEBUG" in text.split("\nlogging:", 1)[1].split("\n\n", 1)[0]


def test_helper_defines_log_env():
    helpers = (CHART / "templates" / "_helpers.tpl").read_text()
    assert "zelkor-platform.logEnv" in helpers
    assert "ZELKOR_LOG_LEVEL" in helpers
    assert "ZELKOR_LOG_FORMAT" in helpers


def test_first_party_templates_include_log_env():
    for path in FIRST_PARTY_TEMPLATES:
        text = path.read_text()
        assert "logEnv" in text, path.name


def test_agent_chart_has_logging_knobs():
    values = (AGENT_CHART / "values.yaml").read_text()
    assert "logging:" in values
    assert "level: INFO" in values
    assert "DEBUG" not in values.split("\nlogging:", 1)[1].split("\n\n", 1)[0]


def test_first_party_python_does_not_hardcode_basicconfig_info():
    skip = {ROOT / "images" / "common" / "zelkor_logging.py"}
    offenders = []
    for path in (ROOT / "mcp").rglob("*.py"):
        if "basicConfig(level=logging.INFO)" in path.read_text():
            offenders.append(path)
    for path in (ROOT / "images").rglob("*.py"):
        if path in skip:
            continue
        if "basicConfig(level=logging.INFO)" in path.read_text():
            offenders.append(path)
    assert offenders == []


def test_vendor_templates_map_level():
    assert "LANGFUSE_LOG_LEVEL" in (CHART / "templates/_helpers.tpl").read_text()
    assert "QDRANT__LOG_LEVEL" in (CHART / "templates/qdrant/statefulset.yaml").read_text()
    assert "log_min_messages=" in (CHART / "templates/postgresql/statefulset.yaml").read_text()
    assert "--loglevel" in (CHART / "templates/valkey/deployment.yaml").read_text()
    assert "zelkor-log.xml" in (CHART / "templates/clickhouse/statefulset.yaml").read_text()
    seaweed = (CHART / "templates/seaweedfs/deployment.yaml").read_text()
    assert "weed -v=" in seaweed
    assert "server -dir=" in seaweed
    assert "-s3.config=/etc/seaweedfs/s3-config.json -v=" not in seaweed
    assert "logging:" in (CHART / "templates/gateway/envoyproxy.yaml").read_text()
    for rel in (
        "images/aegra/Dockerfile",
        "images/aegra-cli/Dockerfile",
        "images/mcp/Dockerfile",
        "images/guardrails/Dockerfile",
        "images/langfuse-seed/Dockerfile",
        "images/sandbox-worker/Dockerfile",
    ):
        text = (ROOT / rel).read_text()
        assert "images/common/zelkor_logging.py" in text, rel


def _helm(*args: str) -> str:
    try:
        res = subprocess.run(["helm", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        pytest.skip("helm not installed")
    if res.returncode != 0:
        pytest.fail(res.stderr or res.stdout)
    return res.stdout


def test_helm_local_overlay_emits_debug_json_on_aegra():
    rendered = _helm(
        "template",
        "zelkor",
        str(CHART),
        "-f",
        str(ROOT / "profiles" / "values-local.yaml"),
        "-s",
        "templates/aegra/deployment.yaml",
    )
    assert "name: ZELKOR_LOG_LEVEL" in rendered
    assert "value: \"DEBUG\"" in rendered.split("ZELKOR_LOG_LEVEL", 1)[1][:120]
    assert "name: ZELKOR_LOG_FORMAT" in rendered
    assert "value: \"json\"" in rendered.split("ZELKOR_LOG_FORMAT", 1)[1][:120]
    assert "name: ZELKOR_LOG_COMPONENT" in rendered
    assert "zelkor-aegra" in rendered.split("ZELKOR_LOG_COMPONENT", 1)[1][:120]


def test_helm_chart_default_is_info_not_debug():
    rendered = _helm(
        "template",
        "zelkor",
        str(CHART),
        "-f",
        str(ROOT / "profiles" / "values-local.yaml"),
        "--set",
        "logging.level=INFO",
        "-s",
        "templates/mcp/deployment-gateway.yaml",
    )
    block = rendered.split("ZELKOR_LOG_LEVEL", 1)[1][:120]
    assert "value: \"INFO\"" in block
    assert "DEBUG" not in block


def test_mcp_tools_list_and_call_log_info(caplog):
    sys.path.insert(0, str(ROOT / "mcp"))
    import threading
    import urllib.request
    from http.server import HTTPServer

    from common.mcp_server import MCPToolHandler, make_handler

    class Dummy(MCPToolHandler):
        def list_tools(self):
            return [{"name": "echo"}]

        def call_tool(self, name, arguments, tenant_id):
            return {"ok": True}

    server = HTTPServer(("127.0.0.1", 0), make_handler(Dummy(), lambda _h: "tenant-a"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def rpc(method, params=None):
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    try:
        with caplog.at_level(logging.INFO, logger="zelkor-mcp"):
            listed = rpc("tools/list")
            called = rpc(
                "tools/call",
                {"name": "echo", "arguments": {"secret": "should-not-log"}},
            )
        assert listed["result"]["tools"][0]["name"] == "echo"
        assert "ok" in called["result"]["content"][0]["text"]
        assert "tools/list count=1" in caplog.text
        assert "tools/call echo" in caplog.text
        assert "should-not-log" not in caplog.text
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_permission_denied_logs_warning(caplog):
    sys.path.insert(0, str(ROOT / "mcp"))
    import threading
    import urllib.request
    from http.server import HTTPServer

    from common.mcp_server import MCPToolHandler, make_handler

    class Dummy(MCPToolHandler):
        def list_tools(self):
            return []

        def call_tool(self, name, arguments, tenant_id):
            raise AssertionError("must not call")

    server = HTTPServer(("127.0.0.1", 0), make_handler(Dummy(), lambda _h: None))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {}},
            }
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with caplog.at_level(logging.WARNING, logger="zelkor-mcp"):
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode())
        assert body["error"]["code"] == -32001
        assert "MCP permission denied" in caplog.text
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_list_tools_logs_info(monkeypatch, caplog):
    sys.path.insert(0, str(ROOT / "mcp"))
    import gateway.gateway_server as gw

    monkeypatch.setattr(gw, "BACKENDS", {"postgres": "http://postgres.example"})

    def fake_rpc(_url, method, _params):
        assert method == "tools/list"
        return {"tools": [{"name": "query"}]}

    monkeypatch.setattr(gw, "_rpc_call", fake_rpc)
    with caplog.at_level(logging.INFO, logger="zelkor-mcp-gateway"):
        tools = gw.GatewayMCPServer().list_tools()
    assert [t["name"] for t in tools] == ["postgres__query"]
    assert "MCP gateway backends=postgres tools=1" in caplog.text


def test_postgres_query_log_omits_sql(monkeypatch, caplog):
    sys.path.insert(0, str(ROOT / "mcp"))
    from wrappers.postgres_server import PostgresMCPServer

    monkeypatch.setattr(
        "wrappers.postgres_server._with_tenant_txn",
        lambda _tenant_id, _fn: {"rows": [], "count": 0},
    )
    with caplog.at_level(logging.INFO, logger="zelkor-mcp-postgres"):
        PostgresMCPServer()._query(
            {"sql": "SELECT secret FROM accounts", "tenant_id": "tenant-a"},
            "tenant-a",
        )
    assert "postgres query rows=0" in caplog.text
    assert "SELECT secret" not in caplog.text
    assert "accounts" not in caplog.text
