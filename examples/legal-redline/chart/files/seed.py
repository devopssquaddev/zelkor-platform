"""Seed Qdrant playbook points and the plain-text house contract."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("zelkor-legal-redline")

COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_redline_playbook")
CONTRACT_KEY = "contracts/msa.txt"
TENANTS = ("harborline-freight", "brightpath-clinics")
DISCLAIMER = (
    "Demo fixture. Not legal advice and not a Zelkor policy pack. "
    "Not the terms of Harborline Freight or Brightpath Clinics."
)

PLAYBOOK = {
    "harborline-freight": [
        {
            "id": 1,
            "rule_id": "hlf-liability-cap-stays",
            "clause_id": "liability-cap",
            "content": (
                f"{DISCLAIMER} Harborline Freight playbook: the liability cap stays. "
                "Unlimited liability is refused."
            ),
        },
        {
            "id": 2,
            "rule_id": "hlf-payment-net45",
            "clause_id": "payment-terms",
            "content": (
                f"{DISCLAIMER} Harborline Freight playbook: net 30 may move to net 45, "
                "not to net 90."
            ),
        },
        {
            "id": 3,
            "rule_id": "hlf-governing-law-house",
            "clause_id": "governing-law",
            "content": (
                f"{DISCLAIMER} Harborline Freight playbook: the house forum stays."
            ),
        },
    ],
    "brightpath-clinics": [
        {
            "id": 4,
            "rule_id": "bpc-liability-cap-network",
            "clause_id": "liability-cap",
            "content": (
                f"{DISCLAIMER} Brightpath Clinics playbook: a care-network cap may rise "
                "to USD 500,000; unlimited liability is still refused."
            ),
        },
        {
            "id": 5,
            "rule_id": "bpc-payment-net45",
            "clause_id": "payment-terms",
            "content": (
                f"{DISCLAIMER} Brightpath Clinics playbook: net 30 may move to net 45, "
                "not to net 90."
            ),
        },
        {
            "id": 6,
            "rule_id": "bpc-governing-law-house",
            "clause_id": "governing-law",
            "content": (
                f"{DISCLAIMER} Brightpath Clinics playbook: the house forum stays."
            ),
        },
    ],
}


def _configure_logging() -> None:
    level = getattr(logging, os.getenv("ZELKOR_LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")


def _contract_text() -> str:
    path = Path(os.getenv("CONTRACT_PATH") or "/app/contract.txt")
    return path.read_text(encoding="utf-8")


def _json_request(method: str, url: str, body: dict | None = None, timeout: int = 10) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        payload = {}
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"text": raw[:200]}
        return exc.code, payload


def _wait_tcp_http(url: str, attempts: int = 60) -> None:
    last = "unreached"
    for _ in range(attempts):
        try:
            code, _ = _json_request("GET", url, None, timeout=3)
            if code < 500:
                return
            last = f"http {code}"
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise RuntimeError(f"dependency not ready: {url} ({last})")


def _seed_qdrant(base: str) -> None:
    _wait_tcp_http(f"{base}/collections")
    code, body = _json_request(
        "PUT",
        f"{base}/collections/{COLLECTION}",
        {"vectors": {"size": 4, "distance": "Cosine"}},
    )
    if code not in (200, 201, 409):
        raise RuntimeError(f"qdrant create collection failed: {code} {body}")
    points = []
    for tenant, rows in PLAYBOOK.items():
        for row in rows:
            points.append(
                {
                    "id": row["id"],
                    "vector": [0.1, 0.2, 0.3, 0.4],
                    "payload": {
                        "tenant_id": tenant,
                        "clause_id": row["clause_id"],
                        "rule_id": row["rule_id"],
                        "document": row["content"],
                        "content": row["content"],
                    },
                }
            )
    code, body = _json_request(
        "PUT",
        f"{base}/collections/{COLLECTION}/points?wait=true",
        {"points": points},
    )
    if code not in (200, 201):
        raise RuntimeError(f"qdrant upsert failed: {code} {body}")
    logger.info("playbook seeded", extra={"event": "seed", "collection": COLLECTION})


def _s3_client():
    import boto3
    from botocore.config import Config

    endpoint = os.getenv("OBJECT_S3_ENDPOINT", "").strip()
    access = os.getenv("OBJECT_S3_ACCESS_KEY", "").strip()
    secret = os.getenv("OBJECT_S3_SECRET_KEY", "").strip()
    if not endpoint or not access or not secret:
        raise RuntimeError("object S3 endpoint and credentials are required")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _seed_objects() -> None:
    bucket = os.getenv("OBJECT_S3_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("OBJECT_S3_BUCKET is required")
    client = _s3_client()
    body = _contract_text().encode("utf-8")
    for tenant in TENANTS:
        key = f"{tenant}/{CONTRACT_KEY}"
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="text/plain; charset=utf-8",
        )
    logger.info("contracts seeded", extra={"event": "seed", "tenants": len(TENANTS)})


def main() -> int:
    _configure_logging()
    qdrant = os.getenv("QDRANT_URL", "").rstrip("/")
    if not qdrant:
        logger.error("QDRANT_URL is required")
        return 1
    _seed_qdrant(qdrant)
    _seed_objects()
    return 0


if __name__ == "__main__":
    sys.exit(main())
