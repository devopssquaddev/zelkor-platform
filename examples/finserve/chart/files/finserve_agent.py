"""
FinServe AI — LangGraph ReAct orchestrator over Zelkor Native MCP.

Guardrails: platform NeMo only (no agent-side topic regex).
Tools: discovered from MCP gateway; LLM selects via OpenAI-style tool calling.
LLM: Envoy AI Gateway /v1/chat/completions (CE interim).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict

import httpx

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
    StateGraph = None  # type: ignore[misc, assignment]
    END = None  # type: ignore[misc, assignment]

logger = logging.getLogger("finserve")

MCP_URL = os.getenv("MCP_URL", "http://zelkor-platform-mcp-gateway:8080")
AI_GATEWAY_URL = os.getenv(
    "AI_GATEWAY_URL",
    "http://envoy-default-zelkor-platform-gateway.envoy-gateway-system.svc.cluster.local:80/v1",
)
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-oss:20b")
NEMO_URL = os.getenv("NEMO_URL", "http://zelkor-platform-nemo:8000/v1/guardrails/input")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://zelkor-platform-langfuse:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-zelkor-dev-00000000000000000000")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-zelkor-dev-00000000000000000000")
LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "true").lower() in ("1", "true", "yes")
AI_GATEWAY_HOST_HEADER = os.getenv("AI_GATEWAY_HOST_HEADER", "ai-gateway.localhost")
AI_GATEWAY_API_KEY = os.getenv(
    "AI_GATEWAY_API_KEY",
    os.getenv("OLLAMA_API_KEY", os.getenv("ZELKOR_CONSUMER_KEY", "dev-key")),
)
LANGFUSE_HOST_HEADER = os.getenv("LANGFUSE_HOST_HEADER", "langfuse.localhost")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "finserve_policies")
MAX_REACT_TURNS = int(os.getenv("FINSERVE_MAX_REACT_TURNS", "5"))


class MCPClient:
    def __init__(self, tenant_id: str, base_url: str = MCP_URL) -> None:
        self.tenant_id = tenant_id
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer dev:{tenant_id}",
            "X-Tenant-ID": tenant_id,
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/mcp", headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return (data.get("result") or {}).get("tools") or []

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        args = dict(arguments or {})
        args.setdefault("tenant_id", self.tenant_id)
        if name.startswith("qdrant__"):
            # LLM often hallucinates collection names (e.g. "policies"); always use demo seed collection.
            args["collection"] = QDRANT_COLLECTION
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{self.base_url}/mcp", headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        content = (data.get("result") or {}).get("content") or []
        if content and content[0].get("text"):
            return json.loads(content[0]["text"])
        return data.get("result")


def mcp_tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    openai_tools = []
    for tool in tools:
        schema = dict(tool.get("inputSchema") or {"type": "object", "properties": {}})
        properties = dict(schema.get("properties") or {})
        if tool["name"].startswith("qdrant__"):
            properties["collection"] = {
                "type": "string",
                "default": QDRANT_COLLECTION,
                "description": f"Qdrant collection. Must be '{QDRANT_COLLECTION}'.",
            }
            schema["properties"] = properties
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": schema,
            },
        })
    return openai_tools


class GatewayChatModel:
    def __init__(self, tenant_id: str, model: str, base_url: str) -> None:
        self.tenant_id = tenant_id
        self.model = model
        self.base_urls = [base_url.rstrip("/")]

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_GATEWAY_API_KEY}",
            "X-Tenant-ID": self.tenant_id,
            "x-ai-eg-model": self.model,
            "Host": AI_GATEWAY_HOST_HEADER,
        }
        last_error: Optional[Exception] = None
        for base in self.base_urls:
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(f"{base}/chat/completions", headers=headers, json=body)
                    if resp.status_code != 200:
                        last_error = RuntimeError(f"LLM {resp.status_code}: {resp.text[:200]}")
                        continue
                    return resp.json()
            except Exception as exc:
                last_error = exc
                logger.debug("LLM via %s failed: %s", base, exc)
        raise RuntimeError(f"AI Gateway unreachable: {last_error}")


def _span(name: str, started: float, input_data: Any, output_data: Any, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    return {
        "id": f"span-{uuid.uuid4().hex[:12]}",
        "name": name,
        "startTime": datetime.datetime.fromtimestamp(started, tz=datetime.timezone.utc).isoformat(),
        "endTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input": input_data,
        "output": output_data,
        "metadata": metadata or {},
    }


class LangfuseTracer:
    @staticmethod
    async def emit(
        *,
        tenant_id: str,
        trace_id: str,
        name: str,
        prompt: str,
        output: Any,
        thread_id: str,
        spans: List[Dict[str, Any]],
        started_at: float,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not LANGFUSE_ENABLED or not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
            return
        try:
            end_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            start_iso = datetime.datetime.fromtimestamp(started_at, tz=datetime.timezone.utc).isoformat()
            batch: List[Dict[str, Any]] = [{
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": end_iso,
                "body": {
                    "id": trace_id,
                    "name": name,
                    "userId": tenant_id,
                    "sessionId": thread_id,
                    "input": prompt,
                    "output": output,
                    "tags": tags or ["finserve", tenant_id, "wealth-management"],
                    "metadata": metadata or {},
                },
            }]
            for span in spans:
                batch.append({
                    "id": str(uuid.uuid4()),
                    "type": "span-create",
                    "timestamp": span.get("endTime", end_iso),
                    "body": {
                        "id": span.get("id", str(uuid.uuid4())),
                        "traceId": trace_id,
                        "name": span.get("name", "span"),
                        "startTime": span.get("startTime", start_iso),
                        "endTime": span.get("endTime", end_iso),
                        "input": span.get("input"),
                        "output": span.get("output"),
                        "metadata": span.get("metadata", {}),
                    },
                })
            auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
            headers = {"Host": LANGFUSE_HOST_HEADER}
            async with httpx.AsyncClient(timeout=3.0) as client:
                for url in (f"{LANGFUSE_HOST}/api/public/ingestion", "http://127.0.0.1:8088/api/public/ingestion"):
                    try:
                        resp = await client.post(url, headers=headers, auth=auth, json={"batch": batch})
                        if resp.status_code in (200, 201, 207):
                            break
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("Langfuse emission failed: %s", exc)


class AgentState(TypedDict, total=False):
    prompt: str
    thread_id: str
    tenant_id: str
    messages: List[Dict[str, Any]]
    openai_tools: List[Dict[str, Any]]
    guardrail: Dict[str, Any]
    tool_results: List[Dict[str, Any]]
    execution_result: Dict[str, Any]
    portfolios: List[Dict[str, Any]]
    policies: List[Dict[str, Any]]
    response: Dict[str, Any]
    spans: List[Dict[str, Any]]
    trace_tags: List[str]
    trace_metadata: Dict[str, Any]


class FinServeAgent:
    def __init__(
        self,
        tenant_id: str,
        *,
        mcp_url: str = MCP_URL,
        ai_gateway_url: str = AI_GATEWAY_URL,
        model: str = DEFAULT_LLM_MODEL,
    ) -> None:
        self.tenant_id = tenant_id
        self.mcp = MCPClient(tenant_id, mcp_url)
        self.llm = GatewayChatModel(tenant_id, model, ai_gateway_url)
        self.model = model

    async def _call_nemo_guardrails(self, prompt: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(NEMO_URL, json={"prompt": prompt, "tenant_id": self.tenant_id})
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("NeMo guardrails unavailable: %s", exc)
            return {
                "allowed": False,
                "reason": "guardrails_unavailable",
                "response": (
                    "FinServe cannot process this request because conversational guardrails "
                    "are temporarily unavailable. Please retry shortly."
                ),
            }

    async def _fetch_langfuse_system_prompt(self) -> str:
        fallback = (
            f"You are FinServe Wealth Management AI for tenant {self.tenant_id}. "
            "Use MCP tools: postgres__query for portfolio rows (portfolios table), "
            f"qdrant__search_documents for policy documents (collection '{QDRANT_COLLECTION}'), "
            "sandbox__execute_python for calculations. Do not invent table or collection names. "
            "Always respect tenant isolation. Summarize tool results clearly for the user."
        )
        auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
        headers = {"Host": LANGFUSE_HOST_HEADER}
        urls = [
            f"{LANGFUSE_HOST}/api/public/v2/prompts/finserve-system",
            "http://127.0.0.1:8088/api/public/v2/prompts/finserve-system",
        ]
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                for url in urls:
                    try:
                        resp = await client.get(url, headers=headers, auth=auth)
                        if resp.status_code == 200:
                            data = resp.json()
                            prompt = data.get("prompt") or data.get("content")
                            if isinstance(prompt, str) and prompt.strip():
                                return prompt.replace("{tenant_id}", self.tenant_id)
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("Langfuse prompt fetch failed: %s", exc)
        return fallback

    def _collect_structured_data(self, tool_results: List[Dict[str, Any]]) -> tuple[List[Dict], List[Dict], Optional[Dict]]:
        portfolios: List[Dict] = []
        policies: List[Dict] = []
        execution_result: Optional[Dict] = None
        for tr in tool_results:
            name = tr.get("tool", "")
            result = tr.get("result") or {}
            if name.startswith("postgres__"):
                rows = result.get("rows") or []
                portfolios.extend(r for r in rows if isinstance(r, dict) and r.get("tenant_id"))
            elif name.startswith("qdrant__"):
                policies.extend(result.get("documents") or [])
            elif name.startswith("sandbox__"):
                execution_result = result
        return portfolios, policies, execution_result

    def _fallback_response(self, prompt: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        portfolios, policies, execution_result = self._collect_structured_data(tool_results)
        if execution_result is not None:
            stdout = execution_result.get("stdout") or execution_result.get("output") or ""
            return {
                "tenant_id": self.tenant_id,
                "response": f"Sandbox execution completed.\n{stdout}".strip(),
                "execution_result": execution_result,
                "tool_results": tool_results,
                "source": "mcp:sandbox",
            }
        if policies:
            bullets = "\n".join(f"- {p.get('title')}: {p.get('content')}" for p in policies)
            return {
                "tenant_id": self.tenant_id,
                "response": f"Retrieved policies for {self.tenant_id}:\n{bullets}",
                "policies": policies,
                "portfolios": portfolios,
                "tool_results": tool_results,
                "source": "mcp:qdrant",
            }
        if portfolios:
            total = sum(float(p.get("balance", 0)) for p in portfolios)
            return {
                "tenant_id": self.tenant_id,
                "response": (
                    f"Retrieved {len(portfolios)} portfolios for {self.tenant_id}. "
                    f"Total AUM: ${total:,.2f}"
                ),
                "portfolios": portfolios,
                "policies": policies,
                "tool_results": tool_results,
                "source": "mcp:postgres",
            }
        return {
            "tenant_id": self.tenant_id,
            "response": "AI Gateway unavailable; no tool results to summarize.",
            "tool_results": tool_results,
            "source": "fallback",
        }

    async def _react_loop(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        openai_tools = state.get("openai_tools") or []
        spans = list(state.get("spans") or [])
        tool_results: List[Dict[str, Any]] = list(state.get("tool_results") or [])

        for turn in range(MAX_REACT_TURNS):
            started = time.time()
            try:
                completion = await self.llm.complete(messages, openai_tools)
            except Exception as exc:
                logger.warning("LLM failed on turn %s: %s", turn, exc)
                state["response"] = self._fallback_response(state["prompt"], tool_results)
                state["spans"] = spans
                state["tool_results"] = tool_results
                return state

            choice = (completion.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            spans.append(_span(
                "ai_gateway_llm_chat",
                started,
                {"turn": turn, "model": self.model},
                {"message": message, "usage": completion.get("usage", {})},
                {"gateway": "envoy-ai-gateway", "tenant_id": self.tenant_id},
            ))

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                messages.append(message)
                for call in tool_calls:
                    fn = call.get("function") or {}
                    tool_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    t0 = time.time()
                    try:
                        result = await self.mcp.call_tool(tool_name, args)
                        tool_results.append({"tool": tool_name, "arguments": args, "result": result})
                        spans.append(_span(
                            f"mcp_tool_{tool_name.replace('__', '_')}",
                            t0,
                            {"tool": tool_name, "arguments": args},
                            result,
                            {"mcp": True, "tenant_id": self.tenant_id},
                        ))
                        tool_content = json.dumps(result)
                    except Exception as exc:
                        tool_content = json.dumps({"error": str(exc)})
                        tool_results.append({"tool": tool_name, "arguments": args, "error": str(exc)})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id") or str(uuid.uuid4()),
                        "name": tool_name,
                        "content": tool_content,
                    })
                continue

            content = message.get("content") or ""
            portfolios, policies, execution_result = self._collect_structured_data(tool_results)
            state["response"] = {
                "tenant_id": self.tenant_id,
                "response": content,
                "portfolios": portfolios,
                "policies": policies,
                "tool_results": tool_results,
                "model": self.model,
                "source": "ai_gateway",
            }
            if execution_result is not None:
                state["response"]["execution_result"] = execution_result
                stdout = f"{execution_result.get('stdout', '')} {execution_result.get('stderr', '')}"
                if any(k in stdout for k in ("BLOCKED", "PermissionError", "Operation not permitted")):
                    state["trace_tags"] = ["finserve", self.tenant_id, "gvisor-sandbox", "outbreak-prevention-verified"]
                    state["trace_metadata"] = {"security_event": "code_outbreak_prevented", "sandbox": "gvisor"}
            state["spans"] = spans
            state["tool_results"] = tool_results
            return state

        state["response"] = self._fallback_response(state["prompt"], tool_results)
        state["spans"] = spans
        state["tool_results"] = tool_results
        state.setdefault("trace_tags", ["finserve", self.tenant_id, "wealth-management"])
        return state

    async def _node_guardrails(self, state: AgentState) -> AgentState:
        prompt = state["prompt"]
        spans = list(state.get("spans") or [])
        started = time.time()
        guardrail = await self._call_nemo_guardrails(prompt)
        spans.append(_span(
            "nemo_guardrails_input_check",
            started,
            {"prompt": prompt, "tenant_id": self.tenant_id},
            guardrail,
            {"engine": "nemo-guardrails-cpu"},
        ))
        state["guardrail"] = guardrail
        state["spans"] = spans
        return state

    async def _node_prepare(self, state: AgentState) -> AgentState:
        if not state.get("guardrail", {}).get("allowed", True):
            return state
        system = await self._fetch_langfuse_system_prompt()
        mcp_tools = await self.mcp.list_tools()
        state["openai_tools"] = mcp_tools_to_openai(mcp_tools)
        existing = list(state.get("messages") or [])
        if existing:
            if not any(m.get("role") == "system" for m in existing):
                state["messages"] = [{"role": "system", "content": system}, *existing]
            return state
        state["messages"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": state.get("prompt") or ""},
        ]
        return state

    async def _node_blocked(self, state: AgentState) -> AgentState:
        guardrail = state.get("guardrail") or {}
        state["response"] = {
            "tenant_id": self.tenant_id,
            "guardrail_triggered": True,
            "guardrail_blocked": True,
            "response": guardrail.get("response", ""),
            "data": [],
            "policies": [],
        }
        state["trace_tags"] = ["finserve", self.tenant_id, "guardrail-refusal", "nemo-guardrails"]
        return state

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("guardrails", self._node_guardrails)
        graph.add_node("prepare", self._node_prepare)
        graph.add_node("blocked", self._node_blocked)
        graph.add_node("react", self._react_loop)
        graph.set_entry_point("guardrails")

        def after_guardrails(state: AgentState) -> str:
            if not state.get("guardrail", {}).get("allowed", True):
                return "blocked"
            return "prepare"

        graph.add_conditional_edges("guardrails", after_guardrails, {"blocked": "blocked", "prepare": "prepare"})
        graph.add_edge("prepare", "react")
        graph.add_edge("blocked", END)
        graph.add_edge("react", END)
        return graph.compile()

    async def handle_prompt(self, prompt: str, thread_id: str = "default-thread") -> Dict[str, Any]:
        started_at = time.time()
        trace_id = f"trace-{uuid.uuid4().hex}"
        initial: AgentState = {
            "prompt": prompt,
            "thread_id": thread_id,
            "tenant_id": self.tenant_id,
            "spans": [],
            "tool_results": [],
        }

        if StateGraph is not None:
            final_state = await self._build_graph().ainvoke(initial)
        else:
            state = await self._node_guardrails(initial)
            if not state.get("guardrail", {}).get("allowed", True):
                final_state = await self._node_blocked(state)
            else:
                state = await self._node_prepare(state)
                final_state = await self._react_loop(state)

        result = final_state.get("response") or {}
        await LangfuseTracer.emit(
            tenant_id=self.tenant_id,
            trace_id=trace_id,
            name="finserve_agent_handle_prompt",
            prompt=prompt,
            output=result,
            thread_id=thread_id,
            spans=final_state.get("spans") or [],
            started_at=started_at,
            tags=final_state.get("trace_tags"),
            metadata=final_state.get("trace_metadata"),
        )
        return result


def _tenant_from_config(config: Optional[Dict[str, Any]]) -> str:
    configurable = (config or {}).get("configurable") or {}
    user = configurable.get("langgraph_auth_user") or {}
    if isinstance(user, dict):
        return str(user.get("identity") or user.get("tenant_id") or "")
    return str(getattr(user, "identity", "") or "")


def graph(config: Optional[Dict[str, Any]] = None):
    """Aegra graph factory — compiled when this graph is registered with platform Aegra."""
    tenant_id = _tenant_from_config(config) or "anonymous"
    return FinServeAgent(tenant_id=tenant_id)._build_graph()
