"""Mode B per-run factory (B14 / 07_clients §2)."""
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("langchain_core")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "aegra"))

from mcp_inject import (  # noqa: E402
    _make_mode_b_graph_factory,
    _store_specs,
    _wrap_agent_factory,
    patch_langgraph,
)


def _runtime(access_context: str) -> SimpleNamespace:
    return SimpleNamespace(access_context=access_context)


def _fake_orig(*_args, tools=None, **_kwargs):
    return SimpleNamespace(tools=tools or [], kind="compiled")


@pytest.fixture
def stub_langchain_mcp_adapters():
    """Kind/dev venv has no langchain-mcp-adapters; inner import still needs a module."""
    pkg = ModuleType("langchain_mcp_adapters")
    tools = ModuleType("langchain_mcp_adapters.tools")

    def _unused(_session, _spec):
        raise AssertionError("stub convert must be patched")

    tools.convert_mcp_tool_to_langchain_tool = _unused
    pkg.tools = tools
    sys.modules.setdefault("langchain_mcp_adapters", pkg)
    sys.modules.setdefault("langchain_mcp_adapters.tools", tools)
    yield


@pytest.fixture
def reset_spec_cache():
    import mcp_inject

    mcp_inject._TOOL_SPEC_CACHE.clear()
    yield
    mcp_inject._TOOL_SPEC_CACHE.clear()


def test_module_level_create_agent_returns_factory_without_calling_orig():
    def orig(*_args, **_kwargs):
        raise AssertionError("orig must not run at import")

    wrapped = _wrap_agent_factory(orig)
    with patch("mcp_inject._is_module_level_create_agent_call", return_value=True):
        factory = wrapped("model", tools=[])
    assert factory.__name__ == "zelkor_mode_b_graph"


def test_module_level_stack_walk_skips_inject_helper():
    """Import-time create_agent must be a factory (not tools=[] compile)."""
    src = (
        "from mcp_inject import _wrap_agent_factory\n"
        "def orig(*_a, **_k):\n"
        "    raise AssertionError('orig must not run at import')\n"
        "graph = _wrap_agent_factory(orig)('model', tools=[])\n"
    )
    ns: dict = {}
    exec(compile(src, "research_agent.py", "exec"), ns)
    assert ns["graph"].__name__ == "zelkor_mode_b_graph"


def test_patch_langgraph_no_import_time_mcp():
    import mcp_inject

    with patch.object(mcp_inject, "_mcp_client_session") as mock_sess:
        mock_sess.side_effect = AssertionError("import-time MCP")
        with patch.object(mcp_inject, "_patch_factory", return_value=True):
            patch_langgraph()
        mock_sess.assert_not_called()


def test_non_run_access_context_no_session(reset_spec_cache):
    factory = _make_mode_b_graph_factory(_fake_orig, ("m",), {}, ("postgres",), ())
    cfg = {"configurable": {"langgraph_auth_user": {"authorization": "Bearer t"}}}

    with patch("mcp_inject._mcp_client_session") as mock_sess:
        mock_sess.side_effect = AssertionError("session opened on read")
        graph = factory(cfg, _runtime("threads.read"))
        assert graph.kind == "compiled"
        mock_sess.assert_not_called()


def test_create_run_opens_one_session_lifecycle(
    reset_spec_cache, stub_langchain_mcp_adapters, monkeypatch
):
    import mcp_inject

    monkeypatch.setenv("MCP_URL", "http://mcp.test")
    factory = _make_mode_b_graph_factory(_fake_orig, ("m",), {}, (), ())
    cfg = {
        "configurable": {
            "langgraph_auth_user": {"authorization": "Bearer run-jwt"},
        }
    }

    spec = SimpleNamespace(name="postgres__query", description="q", inputSchema={})
    session = SimpleNamespace()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[spec]))
    tool_obj = SimpleNamespace(name="postgres__query", coroutine=None, func=None)
    open_count = 0

    @asynccontextmanager
    async def fake_session(_bearer):
        nonlocal open_count
        open_count += 1
        yield session

    with (
        patch.object(mcp_inject, "_mcp_client_session", fake_session),
        patch(
            "langchain_mcp_adapters.tools.convert_mcp_tool_to_langchain_tool",
            return_value=tool_obj,
        ),
    ):
        ctx = factory(cfg, _runtime("threads.create_run"))

        async def run():
            async with ctx as graph:
                assert graph.kind == "compiled"
                assert graph.tools == [tool_obj]
            return open_count

        assert asyncio.run(run()) == 1


def test_create_run_forwards_bearer(reset_spec_cache, stub_langchain_mcp_adapters, monkeypatch):
    import mcp_inject

    monkeypatch.setenv("MCP_URL", "http://mcp.test")
    captured = {}

    @asynccontextmanager
    async def capture_session(bearer):
        captured["bearer"] = bearer
        session = SimpleNamespace()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[]))
        yield session

    factory = _make_mode_b_graph_factory(_fake_orig, (), {}, (), ())
    cfg = {"configurable": {"langgraph_auth_user": {"authorization": "Bearer abc"}}}

    with (
        patch.object(mcp_inject, "_mcp_client_session", capture_session),
        patch(
            "langchain_mcp_adapters.tools.convert_mcp_tool_to_langchain_tool",
            return_value=SimpleNamespace(name="t"),
        ),
    ):
        ctx = factory(cfg, _runtime("threads.create_run"))
        asyncio.run(_consume(ctx))
    assert captured["bearer"] == "Bearer abc"


async def _consume(ctx):
    async with ctx:
        pass


def test_mcp_inject_tools_filters_names(
    reset_spec_cache, stub_langchain_mcp_adapters, monkeypatch
):
    import mcp_inject

    monkeypatch.setenv("MCP_URL", "http://mcp.test")
    specs = [
        SimpleNamespace(name="sandbox__execute_python", description="", inputSchema={}),
        SimpleNamespace(name="postgres__query", description="", inputSchema={}),
    ]
    _store_specs({"configurable": {"langgraph_auth_user": {"identity": "t-a"}}}, specs)

    factory = _make_mode_b_graph_factory(
        _fake_orig, (), {}, (), ("sandbox__execute_python",)
    )
    cfg = {"configurable": {"langgraph_auth_user": {"identity": "t-a"}}}

    with patch.object(mcp_inject, "_mcp_client_session") as mock_sess:
        session = SimpleNamespace()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=specs))

        @asynccontextmanager
        async def _sess(_b):
            yield session

        mock_sess.side_effect = _sess
        with patch(
            "langchain_mcp_adapters.tools.convert_mcp_tool_to_langchain_tool",
            side_effect=lambda _s, spec: SimpleNamespace(name=spec.name),
        ):
            graph = factory(cfg, _runtime("threads.read"))
    assert [t.name for t in graph.tools] == ["sandbox__execute_python"]


def test_nested_create_agent_calls_orig_directly():
    seen = {"nested": False}

    def orig(*_args, **_kwargs):
        seen["nested"] = True
        return "COMPILED"

    wrapped = _wrap_agent_factory(orig)

    def author_factory():
        return wrapped("model")

    assert author_factory() == "COMPILED"
    assert seen["nested"] is True


def test_mode_b_factory_two_param_signature():
    import inspect

    factory = _make_mode_b_graph_factory(_fake_orig, (), {}, (), ())
    params = list(inspect.signature(factory).parameters)
    assert params == ["config", "runtime"]
    assert factory.__name__ == "zelkor_mode_b_graph"
    assert factory.__annotations__["config"] is not None
    assert factory.__annotations__["runtime"] is not None
