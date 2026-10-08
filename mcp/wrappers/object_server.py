"""Zelkor object MCP (CE-11a).

Tools carry keys and text windows. The verified JWT supplies the tenant
prefix. S3 credentials stay on this process. SeaweedFS bucket-scoped
identities cannot CreateBucket (Admin only); the chart pre-creates the
bucket, and startup still head/creates for customer S3.
"""
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.mcp_server import MCPToolHandler, run_mcp_server
from common.tenant import extract_tenant, strip_tenant, tenant_key

logger = logging.getLogger("zelkor-mcp-object")

_DEFAULT_MAX_READ = 262144
_DEFAULT_MAX_WRITE = 262144
_DEFAULT_MAX_LIST = 1000


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    return int(raw)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _s3_region(raw: str) -> str:
    value = (raw or "").strip()
    if value in ("", "auto"):
        return "us-east-1"
    return value


def build_s3_client():
    import boto3
    from botocore.config import Config

    endpoint = os.getenv("OBJECT_S3_ENDPOINT", "").strip()
    region = _s3_region(os.getenv("OBJECT_S3_REGION", "auto"))
    access_key = os.getenv("OBJECT_S3_ACCESS_KEY", "").strip()
    secret_key = os.getenv("OBJECT_S3_SECRET_KEY", "").strip()
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("object S3 endpoint and credentials are required")
    path_style = _env_flag("OBJECT_S3_FORCE_PATH_STYLE", True)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if path_style else "virtual"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _error_code(exc) -> tuple:
    response = getattr(exc, "response", None) or {}
    code = str((response.get("Error") or {}).get("Code", ""))
    status = int((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
    return code, status


def _missing_bucket(code: str, status: int) -> bool:
    return status in (404, 400) or code in {"404", "NoSuchBucket", "NotFound"}


def ensure_bucket(client, bucket: str, region: str) -> None:
    """Head the bucket, then CreateBucket on 404. Retry while SeaweedFS starts."""
    from botocore.exceptions import BotoCoreError, ClientError

    if not bucket:
        raise RuntimeError("OBJECT_S3_BUCKET is required")
    deadline = time.monotonic() + 60
    last = "unavailable"
    while time.monotonic() < deadline:
        try:
            client.head_bucket(Bucket=bucket)
            logger.info("object bucket ready", extra={"event": "startup"})
            return
        except ClientError as exc:
            code, status = _error_code(exc)
            last = code or str(status)
            if _missing_bucket(code, status):
                try:
                    kwargs = {"Bucket": bucket}
                    if region != "us-east-1":
                        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
                    client.create_bucket(**kwargs)
                    logger.info("object bucket created", extra={"event": "startup"})
                    return
                except (ClientError, BotoCoreError) as create_exc:
                    last = type(create_exc).__name__
                    if isinstance(create_exc, ClientError):
                        last = _error_code(create_exc)[0] or last
                    logger.warning(
                        "object bucket create failed: %s",
                        last,
                        extra={"event": "startup"},
                    )
            else:
                logger.warning(
                    "object bucket head failed: %s",
                    last,
                    extra={"event": "startup"},
                )
        except BotoCoreError as exc:
            last = type(exc).__name__
            logger.warning(
                "object bucket head failed: %s",
                last,
                extra={"event": "startup"},
            )
        time.sleep(2)
    logger.error("object bucket unavailable: %s", last, extra={"event": "startup"})
    raise SystemExit(1)


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return ""


def _content_range_total(header: str) -> int:
    # bytes start-end/total  or  bytes */total
    if not header or "/" not in header:
        raise ValueError("S3 response missing Content-Range")
    total = header.rsplit("/", 1)[-1].strip()
    if total == "*":
        raise ValueError("S3 response missing object size")
    return int(total)


def _read_bounds(offset, length, max_read: int) -> tuple:
    if offset is None:
        offset = 0
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be an integer >= 0")
    if length is None:
        length = max_read
    if not isinstance(length, int) or isinstance(length, bool) or length < 1:
        raise ValueError("length must be an integer >= 1")
    truncated = length > max_read
    if truncated:
        length = max_read
    return offset, length, truncated


class ObjectMCPServer(MCPToolHandler):
    def __init__(self, s3_client=None):
        self._s3 = s3_client
        self.bucket = os.getenv("OBJECT_S3_BUCKET", "").strip()
        self.region = _s3_region(os.getenv("OBJECT_S3_REGION", "auto"))
        self.max_read = _env_int("OBJECT_MAX_READ_BYTES", _DEFAULT_MAX_READ)
        self.max_write = _env_int("OBJECT_MAX_WRITE_BYTES", _DEFAULT_MAX_WRITE)
        self.max_list = _env_int("OBJECT_MAX_LIST_KEYS", _DEFAULT_MAX_LIST)
        self.allow_delete = _env_flag("OBJECT_ALLOW_DELETE", False)

    def _client(self):
        if self._s3 is None:
            self._s3 = build_s3_client()
        return self._s3

    def list_tools(self):
        key = {"type": "string"}
        return [
            {
                "name": "list",
                "description": "List object keys under the caller tenant. Keys omit the tenant prefix.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prefix": {"type": "string"},
                        "limit": {"type": "integer"},
                        "cursor": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "stat",
                "description": "Object size and metadata. The key omits the tenant prefix.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"key": key},
                    "required": ["key"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_text",
                "description": "Read a UTF-8 window. Bytes above the per-call cap are not returned.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": key,
                        "offset": {"type": "integer"},
                        "length": {"type": "integer"},
                    },
                    "required": ["key"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "write_text",
                "description": "Write a UTF-8 object. Text above the per-call cap is rejected.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": key,
                        "text": {"type": "string"},
                        "content_type": {"type": "string"},
                    },
                    "required": ["key", "text"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "copy",
                "description": "Copy an object inside the bucket. Both keys stay under the caller tenant.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"source": key, "key": key},
                    "required": ["source", "key"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "delete",
                "description": "Delete an object. Disabled unless allowDelete is true.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"key": key},
                    "required": ["key"],
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict, tenant_id: str):
        if "tenant_id" in arguments:
            raise PermissionError("tenant_id argument is not allowed")
        if name == "list":
            return self._list(arguments, tenant_id)
        if name == "stat":
            return self._stat(arguments, tenant_id)
        if name == "read_text":
            return self._read_text(arguments, tenant_id)
        if name == "write_text":
            return self._write_text(arguments, tenant_id)
        if name == "copy":
            return self._copy(arguments, tenant_id)
        if name == "delete":
            return self._delete(arguments, tenant_id)
        raise ValueError(f"Unknown tool: {name}")

    def _prefixed(self, tenant_id: str, raw: str) -> str:
        return tenant_key(tenant_id, raw)

    def _public_key(self, tenant_id: str, s3_key: str) -> str:
        return strip_tenant(tenant_id, s3_key)

    def _list(self, arguments: dict, tenant_id: str):
        raw_prefix = arguments.get("prefix") or ""
        if raw_prefix:
            prefix = self._prefixed(tenant_id, raw_prefix)
        else:
            tenant_key(tenant_id, "placeholder")
            prefix = f"{tenant_id}/"
        limit = arguments.get("limit")
        if limit is None:
            limit = self.max_list
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be an integer >= 1")
        max_keys = min(limit, self.max_list)
        kwargs = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": max_keys}
        cursor = arguments.get("cursor") or ""
        if cursor:
            if not isinstance(cursor, str):
                raise ValueError("cursor must be a string")
            kwargs["ContinuationToken"] = cursor
        page = self._client().list_objects_v2(**kwargs)
        keys = []
        for item in page.get("Contents") or []:
            s3_key = item.get("Key") or ""
            if s3_key.endswith("/") and item.get("Size", 0) == 0:
                continue
            keys.append(
                {
                    "key": self._public_key(tenant_id, s3_key),
                    "size": int(item.get("Size") or 0),
                    "modified": _iso(item.get("LastModified")),
                }
            )
        logger.info(
            "object list count=%s",
            len(keys),
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
        return {
            "keys": keys,
            "truncated": bool(page.get("IsTruncated")),
            "cursor": page.get("NextContinuationToken") or "",
        }

    def _stat(self, arguments: dict, tenant_id: str):
        s3_key = self._prefixed(tenant_id, arguments.get("key") or "")
        head = self._client().head_object(Bucket=self.bucket, Key=s3_key)
        etag = str(head.get("ETag") or "").strip('"')
        logger.info("object stat", extra={"event": "tools_call", "tenant_id": tenant_id})
        return {
            "key": self._public_key(tenant_id, s3_key),
            "size": int(head.get("ContentLength") or 0),
            "modified": _iso(head.get("LastModified")),
            "content_type": head.get("ContentType") or "",
            "etag": etag,
        }

    def _read_text(self, arguments: dict, tenant_id: str):
        s3_key = self._prefixed(tenant_id, arguments.get("key") or "")
        offset, length, truncated = _read_bounds(
            arguments.get("offset"),
            arguments.get("length"),
            self.max_read,
        )
        end = offset + length - 1
        try:
            response = self._client().get_object(
                Bucket=self.bucket,
                Key=s3_key,
                Range=f"bytes={offset}-{end}",
            )
        except Exception as exc:
            code, status = _error_code(exc)
            if code in {"InvalidRange", "416"} or status == 416:
                public = self._public_key(tenant_id, s3_key)
                return {
                    "key": public,
                    "offset": offset,
                    "length": 0,
                    "eof": True,
                    "truncated": truncated,
                    "text": "",
                }
            raise
        body = response["Body"].read()
        total = _content_range_total(str(response.get("ContentRange") or ""))
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("object window is not UTF-8 text") from exc
        logger.info(
            "object read bytes=%s",
            len(body),
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
        return {
            "key": self._public_key(tenant_id, s3_key),
            "offset": offset,
            "length": len(body),
            "eof": offset + len(body) >= total,
            "truncated": truncated,
            "text": text,
        }

    def _write_text(self, arguments: dict, tenant_id: str):
        text = arguments.get("text")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        raw = text.encode("utf-8")
        if len(raw) > self.max_write:
            raise ValueError(f"text exceeds maxWriteBytes ({self.max_write})")
        s3_key = self._prefixed(tenant_id, arguments.get("key") or "")
        content_type = arguments.get("content_type") or "text/plain; charset=utf-8"
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError("content_type must be a string")
        self._client().put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=raw,
            ContentType=content_type,
        )
        logger.info(
            "object write bytes=%s",
            len(raw),
            extra={"event": "tools_call", "tenant_id": tenant_id},
        )
        return {"key": self._public_key(tenant_id, s3_key), "size": len(raw)}

    def _copy(self, arguments: dict, tenant_id: str):
        source = self._prefixed(tenant_id, arguments.get("source") or "")
        dest = self._prefixed(tenant_id, arguments.get("key") or "")
        self._client().copy_object(
            Bucket=self.bucket,
            Key=dest,
            CopySource={"Bucket": self.bucket, "Key": source},
        )
        logger.info("object copy", extra={"event": "tools_call", "tenant_id": tenant_id})
        return {"key": self._public_key(tenant_id, dest)}

    def _delete(self, arguments: dict, tenant_id: str):
        if not self.allow_delete:
            raise PermissionError("object delete is disabled")
        s3_key = self._prefixed(tenant_id, arguments.get("key") or "")
        self._client().delete_object(Bucket=self.bucket, Key=s3_key)
        logger.info("object delete", extra={"event": "tools_call", "tenant_id": tenant_id})
        return {"key": self._public_key(tenant_id, s3_key), "deleted": True}


if __name__ == "__main__":
    region = _s3_region(os.getenv("OBJECT_S3_REGION", "auto"))
    bucket = os.getenv("OBJECT_S3_BUCKET", "").strip()
    client = build_s3_client()
    ensure_bucket(client, bucket, region)
    run_mcp_server(
        ObjectMCPServer(client),
        extract_tenant,
        port=int(os.getenv("PORT", "8080")),
    )
