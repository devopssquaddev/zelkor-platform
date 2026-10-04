"""Factory helpers: model rewrite, graph name, sandbox selection (no cluster)."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra-deep"))

from zelkor_deep_factory import (  # noqa: E402
    factory_kwargs,
    graph,
    graph_id_from_agent,
    model_spec,
    validate_mcp_servers,
    wants_sandbox,
)
from zelkor_gvisor_backend import (  # noqa: E402
    SKILLS_VIRTUAL_PATH,
    ZelkorGvisorBackend,
    _parse_execute_payload,
    wrap_shell_as_python,
)


def test_graph_name_defaults_to_agent():
    assert graph_id_from_agent({}) == "agent"
    assert graph_id_from_agent({"name": "fraud"}) == "fraud"


def test_model_rewrite_strips_provider_and_does_not_set_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    spec = model_spec({"model": "anthropic:claude-sonnet-4-6"})
    assert spec["model"] == "claude-sonnet-4-6"
    assert spec["base_url_env"] == "OPENAI_BASE_URL"
    assert spec["api_key_env"] == "OPENAI_API_KEY"
    assert spec["sets_anthropic_key"] is False
    assert spec["anthropic_env_present"] is False


def test_model_rewrite_runtime_model_id(monkeypatch):
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")
    spec = model_spec({"runtime": {"model": {"model_id": "anthropic:claude-3"}}})
    assert spec["model"] == "gpt-oss:20b"


def test_sandbox_only_when_asked():
    assert wants_sandbox({}) is False
    assert wants_sandbox({"backend": "sandbox"}) is True
    assert wants_sandbox({"backend": {"type": "sandbox"}}) is True
    assert wants_sandbox({"backend": {"type": "state"}}) is False


def test_factory_kwargs_from_tree(tmp_path):
    (tmp_path / "agent.json").write_text(
        json.dumps({"name": "desk", "backend": {"type": "sandbox"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Be brief.\n", encoding="utf-8")
    (tmp_path / "tools.json").write_text(
        json.dumps([{"name": "acme", "url": "http://acme-mcp.svc:8080"}]),
        encoding="utf-8",
    )
    kwargs = factory_kwargs(tmp_path)
    assert kwargs["name"] == "desk"
    assert kwargs["sandbox"] is True
    assert kwargs["mcp_servers"] == [{"name": "acme", "url": "http://acme-mcp.svc:8080"}]
    assert "ANTHROPIC_API_KEY" not in (tmp_path / "agent.json").read_text()


def test_factory_source_never_sets_anthropic_key():
    text = (Path(__file__).resolve().parents[1] / "images/aegra-deep/zelkor_deep_factory.py").read_text()
    assert "ANTHROPIC_API_KEY" not in text or "never" in text.lower()
    assert 'os.environ["ANTHROPIC_API_KEY"]' not in text
    assert "os.environ['ANTHROPIC_API_KEY']" not in text


def test_parent_aegra_image_does_not_pin_deepagents():
    reqs = (Path(__file__).resolve().parents[1] / "images/aegra/requirements.txt").read_text()
    assert "deepagents" not in reqs


_PROTOCOL_METHODS = (
    "ls",
    "als",
    "read",
    "aread",
    "write",
    "awrite",
    "edit",
    "aedit",
    "grep",
    "agrep",
    "glob",
    "aglob",
    "delete",
    "adelete",
    "execute",
    "aexecute",
    "upload_files",
    "aupload_files",
    "download_files",
    "adownload_files",
)


def test_gvisor_backend_protocol_methods_are_on_the_class():
    backend = ZelkorGvisorBackend()
    for name in _PROTOCOL_METHODS:
        assert name in ZelkorGvisorBackend.__dict__, name
        assert callable(getattr(type(backend), name)), name
    backend.write("/x.txt", "n")
    result = backend.delete("/x.txt")
    assert getattr(result, "error", None) in (None, "")
    ls = backend.ls("/")
    entries = ls.entries if hasattr(ls, "entries") else ls
    assert not any((e.get("path") if isinstance(e, dict) else str(e)) == "/x.txt" for e in (entries or []))


def test_gvisor_backend_write_stays_in_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend = ZelkorGvisorBackend()
    backend.write("/secret.txt", "nope")
    assert not (tmp_path / "secret.txt").exists()
    assert not list(tmp_path.rglob("secret.txt"))


def test_gvisor_backend_seeds_skills_in_memory(tmp_path):
    host = tmp_path / "host-skills" / "planning"
    host.mkdir(parents=True)
    (host / "SKILL.md").write_text("# planning\n", encoding="utf-8")
    backend = ZelkorGvisorBackend()
    virt = backend.seed_host_dir(str(tmp_path / "host-skills"), SKILLS_VIRTUAL_PATH)
    assert virt == "/skills"
    assert not (tmp_path / "skills").exists()
    ls = backend.ls("/skills")
    entries = ls.entries if hasattr(ls, "entries") else ls
    paths = [e["path"] if isinstance(e, dict) else str(e) for e in (entries or [])]
    assert any("planning" in p for p in paths)
    downloads = backend.download_files(["/skills/planning/SKILL.md"])
    assert downloads[0].error in (None, "")
    assert b"planning" in (downloads[0].content or b"")


def test_gvisor_backend_execute_uses_mcp_sdk_not_jsonrpc(monkeypatch):
    calls: dict = {}

    async def fake_call(code: str, environment: str, timeout_sec: int):
        calls["name"] = "sandbox__execute_python"
        calls["arguments"] = {
            "code": code,
            "environment": environment,
            "timeout": timeout_sec,
        }
        inner = json.dumps({"stdout": "ok", "stderr": "", "exit_code": 0})
        return SimpleNamespace(isError=False, content=[SimpleNamespace(text=inner)])

    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp")
    monkeypatch.delenv("SANDBOX_WORKER_URLS", raising=False)
    monkeypatch.setattr("zelkor_gvisor_backend._call_sandbox_execute", fake_call)
    monkeypatch.setattr("zelkor_gvisor_backend._run_async", lambda coro: asyncio.run(coro))
    backend = ZelkorGvisorBackend()
    result = backend.execute("echo hi")
    assert calls["name"] == "sandbox__execute_python"
    assert "tenant_id" not in calls["arguments"]
    assert calls["arguments"]["timeout"] <= 90
    assert result.exit_code == 0
    text = (Path(__file__).resolve().parents[1] / "images/aegra-deep/zelkor_gvisor_backend.py").read_text()
    assert "urllib.request" not in text
    assert "_identity_headers" not in text
    assert "SANDBOX_WORKER_URLS" not in text
    assert "from deepagents.backends import FilesystemBackend" not in text
    assert "streamable_http_client" not in text
    assert "from mcp_inject import call_tool" in text


def test_gvisor_parse_error_prefix_is_exit_1():
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(text="Error: RuntimeError: Session terminated")],
    )
    output, exit_code = _parse_execute_payload(result)
    assert exit_code == 1
    assert output.startswith("Error:")


def test_deep_graph_factory_signature():
    assert "config" in graph.__annotations__
    assert "runtime" in graph.__annotations__


def test_validate_mcp_servers_rejects_foreign_url(monkeypatch):
    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp")
    with pytest.raises(RuntimeError, match="must use"):
        validate_mcp_servers([{"name": "acme", "url": "http://acme-mcp.svc:8080/mcp"}])


def test_validate_mcp_servers_accepts_platform_url(monkeypatch):
    monkeypatch.setenv("MCP_URL", "http://zelkor-platform-mcp")
    validate_mcp_servers([{"name": "platform", "url": "http://zelkor-platform-mcp/mcp"}])


def test_deep_factory_source_uses_mcp_url_only():
    text = (Path(__file__).resolve().parents[1] / "images/aegra-deep/zelkor_deep_factory.py").read_text()
    assert "_load_mcp_tools" not in text
    assert "def graph(config" in text
    assert "MultiServerMCPClient" not in text


def test_wrap_shell_as_python_runs_command_string():
    wrapped = wrap_shell_as_python("echo hi")
    assert "echo hi" in wrapped
    assert "subprocess.run" in wrapped


def test_deep_image_contract():
    root = Path(__file__).resolve().parents[1]
    df = (root / "images/aegra-deep/Dockerfile").read_text()
    assert "zelkor-aegra" in df
    assert "rm -f /app/aegra.json" in df
    assert "deepagents" in (root / "images/aegra-deep/requirements.txt").read_text()
    lg = json.loads((root / "images/aegra-deep/langgraph.json").read_text())
    assert "zelkor_deep_factory.py:graph" in lg["graphs"]["agent"]
    build = (root / "scripts/build-images.sh").read_text()
    assert "zelkor-aegra-deep" in build
