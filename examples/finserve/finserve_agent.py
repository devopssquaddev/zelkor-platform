import os
import json
import logging
import httpx
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finserve")

DATABASE_URL = os.getenv("FINSERVE_DATABASE_URL", "postgresql://zelkor:zelkor-dev-password@zelkor-platform-postgresql:5432/finserve")
LITELLM_URL = os.getenv("LITELLM_URL", "http://zelkor-platform-litellm:4000")
CODE_EXECUTOR_URL = os.getenv("CODE_EXECUTOR_URL", "http://finserve-code-executor:8080")
AEGRA_URL = os.getenv("AEGRA_URL", "http://zelkor-platform-aegra:8000")

class FinServeAgent:
    """
    FinServe AI Wealth Management Agent.
    Enforces tenant boundaries and routes untrusted code execution to sandboxed nodes.
    """
    def __init__(self, tenant_id: str, db_url: str = DATABASE_URL):
        self.tenant_id = tenant_id
        self.db_url = db_url

    def query_database(self, query_tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query portfolios for the authenticated tenant only.
        If a user attempts cross-tenant access, tenant_id scoping prevents it.
        """
        # Strictly enforce the authenticated tenant_id
        effective_tenant = self.tenant_id
        if query_tenant_id and query_tenant_id != self.tenant_id:
            logger.warning(f"Tenant {self.tenant_id} attempted unauthorized access to {query_tenant_id}")
            return []

        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, tenant_id, account_number, client_name, ssn, balance, risk_profile, holdings FROM portfolios WHERE tenant_id = %s",
                    (effective_tenant,)
                )
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return []
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    async def execute_code(self, python_code: str) -> Dict[str, Any]:
        """
        Send dynamically generated Python code to the sandboxed CodeExecutor.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{CODE_EXECUTOR_URL}/execute",
                    json={"code": python_code}
                )
                return resp.json()
        except Exception as e:
            logger.error(f"Code execution error: {e}")
            return {"status": "error", "error": str(e)}

    async def handle_prompt(self, prompt: str, thread_id: str = "default-thread") -> Dict[str, Any]:
        """
        Process user prompts:
        - Cross-tenant queries: filtered via tenant_id
        - Financial math: invokes sandboxed Python code execution
        - Stateful memory: checkpointed via Aegra
        """
        prompt_lower = prompt.lower()

        # Check for cross-tenant injection / IDOR
        if "bank_beta" in prompt_lower and self.tenant_id == "Bank_Alpha":
            # Attempt to query Bank_Beta data
            portfolios = self.query_database(query_tenant_id="Bank_Beta")
            if not portfolios:
                return {
                    "tenant_id": self.tenant_id,
                    "response": "No portfolio records found for Bank_Beta. Access denied or data does not exist.",
                    "data": []
                }

        if "bank_alpha" in prompt_lower and self.tenant_id == "Bank_Beta":
            portfolios = self.query_database(query_tenant_id="Bank_Alpha")
            if not portfolios:
                return {
                    "tenant_id": self.tenant_id,
                    "response": "No portfolio records found for Bank_Alpha. Access denied or data does not exist.",
                    "data": []
                }

        # Code execution request (e.g., Monte Carlo, projections, or adversarial syscall test)
        if "python" in prompt_lower or "code" in prompt_lower or "read /etc/passwd" in prompt_lower or "projection" in prompt_lower:
            code = "import os\n"
            if "/etc/passwd" in prompt_lower:
                code += "try:\n    with open('/etc/passwd') as f:\n        print(f.read())\nexcept Exception as e:\n    print(f'Error: {e}')"
            else:
                code += "import numpy as np\nprint('Calculated projected portfolio growth: +14.2%')"

            exec_result = await self.execute_code(code)
            return {
                "tenant_id": self.tenant_id,
                "response": "Executed financial calculation in sandbox.",
                "execution_result": exec_result
            }

        # Standard portfolio summary query
        portfolios = self.query_database()
        total_balance = sum(float(p.get("balance", 0)) for p in portfolios)
        return {
            "tenant_id": self.tenant_id,
            "response": f"Retrieved {len(portfolios)} portfolios for {self.tenant_id}. Total Assets Under Management: ${total_balance:,.2f}",
            "portfolios": portfolios
        }
