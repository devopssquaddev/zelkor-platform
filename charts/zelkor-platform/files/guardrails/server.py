import os
import re
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nemo-guardrails")

app = FastAPI(title="NeMo Guardrails CPU Service", version="0.1.0")

OFF_TOPIC_PATTERNS = json.loads(os.getenv("NEMO_OFF_TOPIC_PATTERNS", "[]"))

OFF_TOPIC_REFUSAL = os.getenv(
    "NEMO_OFF_TOPIC_REFUSAL",
    "This assistant cannot help with that request. Please stay on topic for your configured domain.",
)
COMPLIANCE_REFUSAL = os.getenv(
    "NEMO_COMPLIANCE_REFUSAL",
    "Request violated compliance, tenant privacy, and security policies.",
)

class GuardrailRequest(BaseModel):
    prompt: str
    tenant_id: str = "default"

@app.get("/health")
async def health():
    return {"status": "ok", "engine": "nemo-guardrails-cpu"}

@app.post("/v1/guardrails/input")
async def evaluate_input(req: GuardrailRequest):
    prompt_lower = req.prompt.lower()
    
    for pat in OFF_TOPIC_PATTERNS:
        if re.search(pat, prompt_lower):
            logger.info(f"Guardrail triggered (off-topic pattern '{pat}') for tenant {req.tenant_id}")
            return {
                "allowed": False,
                "reason": "off-topic",
                "response": OFF_TOPIC_REFUSAL
            }

    if "ssn" in prompt_lower or "password" in prompt_lower:
        logger.info(f"Guardrail triggered (compliance/privacy) for tenant {req.tenant_id}")
        return {
            "allowed": False,
            "reason": "compliance_refusal",
            "response": COMPLIANCE_REFUSAL
        }

    return {"allowed": True, "reason": "passed", "response": ""}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
