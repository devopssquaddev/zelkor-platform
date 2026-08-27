import os
import sys
import json
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, "/app")
from finserve_agent import FinServeAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finserve-agent")

app = FastAPI(
    title="FinServe Wealth Management Agent",
    description="Multi-tenant Wealth Management Reference Agent with gVisor sandboxing and Envoy AI Gateway routing.",
    version="0.1.0"
)

class PromptPayload(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    thread_id: Optional[str] = "default-thread"

class RunPayload(BaseModel):
    assistant_id: Optional[str] = "finserve_agent"
    input: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = "default-thread"

def extract_tenant(authorization: Optional[str], x_tenant_id: Optional[str]) -> str:
    if authorization and "Bearer dev:" in authorization:
        return authorization.split("Bearer dev:", 1)[1].strip()
    if x_tenant_id:
        return x_tenant_id
    return "Bank_Alpha"

@app.get("/health")
async def health():
    return {"status": "ok", "service": "finserve-agent"}

@app.post("/chat")
async def chat(payload: PromptPayload, request: Request, authorization: str = Header(None), x_tenant_id: str = Header(None)):
    tenant_id = extract_tenant(authorization, x_tenant_id)
    prompt_text = payload.prompt or ""
    if not prompt_text and payload.messages:
        prompt_text = payload.messages[-1].get("content", "")

    agent = FinServeAgent(tenant_id=tenant_id)
    result = await agent.handle_prompt(prompt_text, thread_id=payload.thread_id or "default-thread")
    return result

@app.post("/runs/stream")
@app.post("/runs")
async def runs_stream(payload: RunPayload, request: Request, authorization: str = Header(None), x_tenant_id: str = Header(None)):
    tenant_id = extract_tenant(authorization, x_tenant_id)
    prompt_text = ""
    input_data = payload.input or {}
    if isinstance(input_data, dict):
        if "messages" in input_data and isinstance(input_data["messages"], list) and len(input_data["messages"]) > 0:
            prompt_text = input_data["messages"][-1].get("content", "")
        elif "prompt" in input_data:
            prompt_text = input_data["prompt"]

    agent = FinServeAgent(tenant_id=tenant_id)
    result = await agent.handle_prompt(prompt_text, thread_id=payload.thread_id or "default-thread")
    return {
        "event": "messages/complete",
        "assistant_id": payload.assistant_id or "finserve_agent",
        "tenant_id": tenant_id,
        "data": result
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
