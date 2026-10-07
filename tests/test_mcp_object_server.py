"""Object MCP tool contract without a bucket."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from wrappers.object_server import ObjectMCPServer, _read_bounds  # noqa: E402


class _Boom:
    def put_object(self, **_kwargs):
        raise AssertionError("S3 must not be called")

    def delete_object(self, **_kwargs):
        raise AssertionError("S3 must not be called")

    def get_object(self, **_kwargs):
        raise AssertionError("S3 must not be called")


def test_list_tools_short_names():
    names = [tool["name"] for tool in ObjectMCPServer().list_tools()]
    assert names == ["list", "stat", "read_text", "write_text", "copy", "delete"]
    for tool in ObjectMCPServer().list_tools():
        assert tool["inputSchema"]["additionalProperties"] is False


def test_delete_denied_by_default(monkeypatch):
    monkeypatch.delenv("OBJECT_ALLOW_DELETE", raising=False)
    server = ObjectMCPServer(_Boom())
    with pytest.raises(PermissionError, match="disabled"):
        server.call_tool("delete", {"key": "a.txt"}, "tenant-a")


def test_delete_allowed_calls_s3(monkeypatch):
    monkeypatch.setenv("OBJECT_ALLOW_DELETE", "true")
    monkeypatch.setenv("OBJECT_S3_BUCKET", "bucket")

    class _S3:
        def __init__(self):
            self.deleted = None

        def delete_object(self, **kwargs):
            self.deleted = kwargs

    client = _S3()
    server = ObjectMCPServer(client)
    result = server.call_tool("delete", {"key": "a.txt"}, "tenant-a")
    assert result == {"key": "a.txt", "deleted": True}
    assert client.deleted["Key"] == "tenant-a/a.txt"


def test_write_over_cap_is_rejected(monkeypatch):
    monkeypatch.setenv("OBJECT_MAX_WRITE_BYTES", "8")
    server = ObjectMCPServer(_Boom())
    with pytest.raises(ValueError, match="maxWriteBytes"):
        server.call_tool("write_text", {"key": "a.txt", "text": "0123456789"}, "tenant-a")


def test_read_bounds_truncate():
    offset, length, truncated = _read_bounds(0, 500, 100)
    assert (offset, length, truncated) == (0, 100, True)
    offset, length, truncated = _read_bounds(4, 3, 100)
    assert (offset, length, truncated) == (4, 3, False)


def test_read_text_window_and_flags(monkeypatch):
    monkeypatch.setenv("OBJECT_MAX_READ_BYTES", "4")
    monkeypatch.setenv("OBJECT_S3_BUCKET", "bucket")

    class _Body:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

    class _S3:
        def __init__(self):
            self.ranges = []

        def get_object(self, **kwargs):
            self.ranges.append(kwargs["Range"])
            spec = kwargs["Range"].split("=", 1)[1]
            start_s, end_s = spec.split("-")
            start, end = int(start_s), int(end_s)
            data = b"abcdefghij"
            chunk = data[start : end + 1]
            return {
                "Body": _Body(chunk),
                "ContentRange": f"bytes {start}-{start + len(chunk) - 1}/{len(data)}",
            }

    client = _S3()
    server = ObjectMCPServer(client)
    first = server.call_tool(
        "read_text",
        {"key": "notes.txt", "offset": 0, "length": 100},
        "tenant-a",
    )
    assert first["key"] == "notes.txt"
    assert first["offset"] == 0
    assert first["length"] == 4
    assert first["text"] == "abcd"
    assert first["truncated"] is True
    assert first["eof"] is False
    second = server.call_tool(
        "read_text",
        {"key": "notes.txt", "offset": 8, "length": 4},
        "tenant-a",
    )
    assert second["text"] == "ij"
    assert second["length"] == 2
    assert second["eof"] is True
    assert second["truncated"] is False
    assert client.ranges[0] == "bytes=0-3"


def test_read_text_rejects_traversal_without_s3():
    server = ObjectMCPServer(_Boom())
    with pytest.raises(PermissionError):
        server.call_tool("read_text", {"key": "../other/secret"}, "tenant-a")


def test_stray_tenant_id_rejected():
    server = ObjectMCPServer(_Boom())
    with pytest.raises(PermissionError, match="tenant_id"):
        server.call_tool("stat", {"key": "a.txt", "tenant_id": "other"}, "tenant-a")
