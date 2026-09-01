"""Deep Agents backend: execute → MCP sandbox__execute_python (gVisor workers).

Keep the tool name execute. Do not POST worker :8081 from the agent.
File ops are in-memory (not host FilesystemBackend).
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zelkor-gvisor-backend")

SKILLS_VIRTUAL_PATH = "/skills"

try:
    from deepagents.backends.protocol import SandboxBackendProtocol as _ProtocolBase
except Exception:  # pragma: no cover - unit tests without deepagents
    _ProtocolBase = object  # type: ignore[misc,assignment]


async def _to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(fn, *args, **kwargs)


def wrap_shell_as_python(command: str) -> str:
    return (
        "import subprocess, sys\n"
        f"r = subprocess.run({command!r}, shell=True, capture_output=True, text=True)\n"
        "sys.stdout.write(r.stdout or '')\n"
        "sys.stderr.write(r.stderr or '')\n"
        "raise SystemExit(r.returncode)\n"
    )


def _execute_response(output: str, exit_code: int, truncated: bool = False) -> Any:
    try:
        from deepagents.backends.protocol import ExecuteResponse

        return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)
    except Exception:
        return SimpleNamespace(output=output, exit_code=exit_code, truncated=truncated)


def _tenant_id() -> str:
    try:
        from mcp_inject import tenant_from_run_config

        return tenant_from_run_config()
    except Exception:
        return ""


def _identity_headers() -> Dict[str, str]:
    try:
        from mcp_inject import identity_headers

        return identity_headers()
    except Exception:
        return {"Content-Type": "application/json"}


def _norm(path: str) -> str:
    text = (path or "/").replace("\\", "/")
    if not text.startswith("/"):
        text = "/" + text
    parts: List[str] = []
    for seg in text.split("/"):
        if not seg or seg == ".":
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts) if parts else "/"


def _ls_result(error: Optional[str], entries: Optional[list]) -> Any:
    try:
        from deepagents.backends.protocol import LsResult

        return LsResult(error=error, entries=entries)
    except Exception:
        if error:
            return []
        return entries or []


def _write_result(path: Optional[str] = None, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import WriteResult

        return WriteResult(path=path, error=error)
    except Exception:
        return SimpleNamespace(path=path, error=error)


def _edit_result(path: Optional[str] = None, error: Optional[str] = None, occurrences: Optional[int] = None) -> Any:
    try:
        from deepagents.backends.protocol import EditResult

        return EditResult(path=path, error=error, occurrences=occurrences)
    except Exception:
        return SimpleNamespace(path=path, error=error, occurrences=occurrences)


def _delete_result(path: Optional[str] = None, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import DeleteResult

        return DeleteResult(path=path, error=error)
    except Exception:
        return SimpleNamespace(path=path, error=error)


def _read_result(path: str, content: Optional[str] = None, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import ReadResult

        if error:
            return ReadResult(error=error, file_data=None)
        return ReadResult(error=None, file_data={"content": content or "", "encoding": "utf-8"})
    except Exception:
        return SimpleNamespace(error=error, file_data={"content": content or ""} if content is not None else None)


def _download_response(path: str, content: Optional[bytes] = None, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import FileDownloadResponse

        return FileDownloadResponse(path=path, content=content, error=error)
    except Exception:
        return SimpleNamespace(path=path, content=content, error=error)


def _upload_response(path: str, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import FileUploadResponse

        return FileUploadResponse(path=path, error=error)
    except Exception:
        return SimpleNamespace(path=path, error=error)


def _grep_result(matches: list, error: Optional[str] = None, truncated: bool = False) -> Any:
    try:
        from deepagents.backends.protocol import GrepResult

        return GrepResult(error=error, matches=matches, truncated=truncated)
    except Exception:
        return SimpleNamespace(error=error, matches=matches, truncated=truncated)


def _glob_result(matches: list, error: Optional[str] = None) -> Any:
    try:
        from deepagents.backends.protocol import GlobResult

        return GlobResult(error=error, matches=matches, truncated=False)
    except Exception:
        return SimpleNamespace(error=error, matches=matches, truncated=False)


class _MemoryFiles:
    """In-process path → text. Never writes the agent pod disk."""

    def __init__(self) -> None:
        self._files: Dict[str, str] = {}

    def _children(self, virt: str) -> list:
        prefix = virt.rstrip("/") + "/" if virt != "/" else "/"
        names: Dict[str, bool] = {}
        for key in self._files:
            if virt != "/" and key != virt and not key.startswith(prefix):
                continue
            if key == virt:
                continue
            rest = key[len(prefix) :] if virt != "/" else key.lstrip("/")
            if not rest:
                continue
            name = rest.split("/", 1)[0]
            child = (prefix + name) if virt != "/" else "/" + name
            names[child] = "/" in rest
        return [{"path": path, "is_dir": is_dir} for path, is_dir in sorted(names.items())]

    def _dir_exists(self, virt: str) -> bool:
        if virt == "/":
            return True
        prefix = virt.rstrip("/") + "/"
        return any(k.startswith(prefix) or k == virt for k in self._files)

    def ls(self, path: str) -> Any:
        virt = _norm(path)
        if virt in self._files:
            return _ls_result(f"Path '{path}': not_a_directory", None)
        if not self._dir_exists(virt):
            return _ls_result(f"Path '{path}': path_not_found", None)
        return _ls_result(None, self._children(virt))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        virt = _norm(file_path)
        if virt not in self._files:
            return _read_result(virt, error=f"File '{file_path}' not found")
        lines = self._files[virt].splitlines(keepends=True)
        start = max(0, offset)
        window = lines[start : start + max(limit, 0)]
        return _read_result(virt, content="".join(window))

    def write(self, file_path: str, content: str) -> Any:
        virt = _norm(file_path)
        self._files[virt] = content
        return _write_result(path=virt)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        virt = _norm(file_path)
        if virt not in self._files:
            return _edit_result(error=f"File '{file_path}' not found")
        text = self._files[virt]
        count = text.count(old_string)
        if count == 0:
            return _edit_result(error="old_string not found")
        if not replace_all and count != 1:
            return _edit_result(error="old_string is not unique")
        self._files[virt] = text.replace(old_string, new_string)
        return _edit_result(path=virt, occurrences=count if replace_all else 1)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
        **_kwargs: Any,
    ) -> Any:
        root = _norm(path or "/")
        prefix = root.rstrip("/") + "/" if root != "/" else "/"
        matches = []
        for key, text in self._files.items():
            if root != "/" and key != root and not key.startswith(prefix):
                continue
            if glob and not fnmatch.fnmatch(key, glob) and not fnmatch.fnmatch(key.rsplit("/", 1)[-1], glob):
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append({"path": key, "line": i, "text": line})
                    if max_count is not None and len(matches) >= max_count:
                        return _grep_result(matches, truncated=True)
        return _grep_result(matches)

    def glob(self, pattern: str, path: str | None = None) -> Any:
        root = _norm(path or "/")
        prefix = root.rstrip("/") + "/" if root != "/" else "/"
        matches = []
        for key in sorted(self._files):
            if root != "/" and key != root and not key.startswith(prefix):
                continue
            rel = key[len(prefix) :] if root != "/" else key.lstrip("/")
            if fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch("/" + rel, pattern):
                matches.append({"path": key, "is_dir": False})
        return _glob_result(matches)

    def delete(self, file_path: str) -> Any:
        virt = _norm(file_path)
        prefix = virt.rstrip("/") + "/"
        keys = [k for k in self._files if k == virt or k.startswith(prefix)]
        if not keys:
            return _delete_result(error=f"Path '{file_path}' not found")
        for key in keys:
            del self._files[key]
        return _delete_result(path=virt)

    def upload_files(self, files: list) -> list:
        out = []
        for path, content in files:
            virt = _norm(path)
            if isinstance(content, bytes):
                text = content.decode("utf-8")
            else:
                text = str(content)
            self._files[virt] = text
            out.append(_upload_response(virt))
        return out

    def download_files(self, paths: list) -> list:
        out = []
        for path in paths:
            virt = _norm(path)
            if virt not in self._files:
                out.append(_download_response(virt, error="file_not_found"))
                continue
            out.append(_download_response(virt, content=self._files[virt].encode("utf-8")))
        return out


class ZelkorGvisorBackend(_ProtocolBase):
    """SandboxBackendProtocol: files in memory; execute via MCP.

    Deep Agents looks up ``type(backend).<method>`` (including async ``a*``).
    Inherit the protocol when present and keep every method on this class.
    """

    def __init__(self, mcp_url: Optional[str] = None):
        self._mcp = (mcp_url if mcp_url is not None else os.getenv("MCP_URL", "")).rstrip("/")
        self._files = _MemoryFiles()

    @property
    def id(self) -> str:
        return "zelkor-gvisor"

    def seed_host_dir(self, host_dir: str, virtual_path: str = SKILLS_VIRTUAL_PATH) -> str:
        src = Path(host_dir)
        if not src.is_dir():
            return ""
        virt = virtual_path if virtual_path.startswith("/") else f"/{virtual_path}"
        base = _norm(virt)
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(src).as_posix()
            dest = _norm(f"{base}/{rel}")
            self._files.write(dest, path.read_text(encoding="utf-8"))
        return virt

    def execute(self, command: str, *, timeout: int | None = None) -> Any:
        if not self._mcp:
            return _execute_response("MCP_URL is not set", 1)
        seconds = 5 if timeout is None else int(timeout)
        tenant = _tenant_id()
        headers = dict(_identity_headers())
        headers["Content-Type"] = "application/json"
        args: Dict[str, Any] = {
            "code": wrap_shell_as_python(command),
            "environment": "python-base",
            "timeout": seconds,
        }
        if tenant:
            args["tenant_id"] = tenant
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "sandbox__execute_python", "arguments": args},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._mcp}/mcp",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=seconds + 5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("MCP sandbox execute failed: %s", exc)
            return _execute_response(str(exc), 1)
        if body.get("error"):
            msg = (body["error"] or {}).get("message") or str(body["error"])
            return _execute_response(msg, 1)
        text = ((body.get("result") or {}).get("content") or [{}])[0].get("text") or "{}"
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return _execute_response(text, 0)
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        err = result.get("error") or ""
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}".strip() if output else stderr
        if err and err not in output:
            output = f"{output}\n{err}".strip() if output else err
        exit_code = int(result.get("exit_code") or 0)
        if result.get("status") == "error" and exit_code == 0:
            exit_code = 1
        return _execute_response(output, exit_code)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> Any:
        return await _to_thread(self.execute, command, timeout=timeout)

    def ls(self, path: str) -> Any:
        return self._files.ls(path)

    async def als(self, path: str) -> Any:
        return await _to_thread(self.ls, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return self._files.read(file_path, offset=offset, limit=limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return await _to_thread(self.read, file_path, offset, limit)

    def write(self, file_path: str, content: str) -> Any:
        return self._files.write(file_path, content)

    async def awrite(self, file_path: str, content: str) -> Any:
        return await _to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        return self._files.edit(file_path, old_string, new_string, replace_all=replace_all)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Any:
        return await _to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._files.grep(pattern, path=path, glob=glob, max_count=max_count, **kwargs)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
        **kwargs: Any,
    ) -> Any:
        return await _to_thread(self.grep, pattern, path, glob, max_count=max_count, **kwargs)

    def glob(self, pattern: str, path: str | None = None) -> Any:
        return self._files.glob(pattern, path=path)

    async def aglob(self, pattern: str, path: str | None = None) -> Any:
        return await _to_thread(self.glob, pattern, path)

    def delete(self, file_path: str) -> Any:
        return self._files.delete(file_path)

    async def adelete(self, file_path: str) -> Any:
        return await _to_thread(self.delete, file_path)

    def upload_files(self, files: list) -> Any:
        return self._files.upload_files(files)

    async def aupload_files(self, files: list) -> Any:
        return await _to_thread(self.upload_files, files)

    def download_files(self, paths: list) -> Any:
        return self._files.download_files(paths)

    async def adownload_files(self, paths: list) -> Any:
        return await _to_thread(self.download_files, paths)
