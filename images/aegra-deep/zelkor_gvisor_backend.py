"""Deep Agents backend: execute → MCP sandbox__execute_python (gVisor workers).

Keep the tool name execute. Do not POST worker :8081 from the agent.
File ops are in-memory (not host FilesystemBackend).
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zelkor-gvisor-backend")

SKILLS_VIRTUAL_PATH = "/skills"
_SANDBOX_TIMEOUT_MAX = 90

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


def _clamp_timeout(seconds: int) -> int:
    return max(1, min(int(seconds), _SANDBOX_TIMEOUT_MAX))


def _parse_execute_payload(result: Any) -> tuple[str, int]:
    if getattr(result, "isError", False):
        text = ""
        content = getattr(result, "content", None) or []
        if content and getattr(content[0], "text", None):
            text = content[0].text
        return text or "sandbox tool call failed", 1
    content = getattr(result, "content", None) or []
    text = ""
    if content and getattr(content[0], "text", None):
        text = content[0].text
    if not text:
        return "", 0
    if text.startswith("Error:"):
        return text, 1
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, 0
    stdout = parsed.get("stdout") or ""
    stderr = parsed.get("stderr") or ""
    err = parsed.get("error") or ""
    output = stdout
    if stderr:
        output = f"{output}\n{stderr}".strip() if output else stderr
    if err and err not in output:
        output = f"{output}\n{err}".strip() if output else err
    exit_code = int(parsed.get("exit_code") or 0)
    if parsed.get("status") == "error" and exit_code == 0:
        exit_code = 1
    try:
        from sandbox_trace import stamp_sandbox_execution_span

        stamp_sandbox_execution_span(parsed)
    except Exception:
        logger.debug("sandbox trace stamp skipped on execute backend", exc_info=True)
    return output, exit_code


async def _call_sandbox_execute(code: str, environment: str, timeout_sec: int) -> Any:
    from mcp_inject import call_tool

    text = await call_tool(
        "sandbox__execute_python",
        {
            "code": code,
            "environment": environment,
            "timeout": timeout_sec,
        },
    )
    is_err = text.startswith("Error:")
    return SimpleNamespace(isError=is_err, content=[SimpleNamespace(text=text)])


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


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
        if not self._dir_exists(virt):
            return _ls_result("directory_not_found", None)
        return _ls_result(None, self._children(virt))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        virt = _norm(file_path)
        if virt not in self._files:
            return _read_result(virt, error="file_not_found")
        lines = self._files[virt].splitlines()
        chunk = "\n".join(lines[offset : offset + limit])
        return _read_result(virt, content=chunk)

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
            return _edit_result(error="file_not_found")
        text = self._files[virt]
        if old_string not in text:
            return _edit_result(error="string_not_found")
        if replace_all:
            count = text.count(old_string)
            self._files[virt] = text.replace(old_string, new_string)
        else:
            count = 1
            self._files[virt] = text.replace(old_string, new_string, 1)
        return _edit_result(path=virt, occurrences=count)

    def delete(self, file_path: str) -> Any:
        virt = _norm(file_path)
        if virt not in self._files:
            return _delete_result(error="file_not_found")
        del self._files[virt]
        return _delete_result(path=virt)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        output_mode: str = "files_with_matches",
    ) -> Any:
        base = _norm(path or "/")
        matches: list = []
        for key, text in self._files.items():
            if base != "/" and not (key == base or key.startswith(base.rstrip("/") + "/")):
                continue
            if glob and not fnmatch.fnmatch(key, glob):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if fnmatch.fnmatch(line, pattern) or pattern in line:
                    matches.append({"path": key, "line": idx, "text": line})
        if output_mode == "content":
            return _grep_result(matches)
        paths = sorted({m["path"] for m in matches})
        return _grep_result([{"path": p} for p in paths])

    def glob(self, pattern: str, path: str = "/") -> Any:
        base = _norm(path)
        found = []
        for key in self._files:
            if base != "/" and not (key == base or key.startswith(base.rstrip("/") + "/")):
                continue
            if fnmatch.fnmatch(key, pattern):
                found.append(key)
        return _glob_result(sorted(found))

    def upload_files(self, files: list) -> list:
        out = []
        for item in files:
            path = _norm(getattr(item, "path", "") or item.get("path", ""))
            content = getattr(item, "content", None)
            if content is None and isinstance(item, dict):
                content = item.get("content")
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            if not isinstance(content, str):
                out.append(_upload_response(path, error="invalid_content"))
                continue
            self._files[path] = content
            out.append(_upload_response(path))
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
            logger.error("MCP_URL is not set")
            return _execute_response("MCP_URL is not set", 1)
        seconds = _clamp_timeout(5 if timeout is None else int(timeout))
        logger.info(
            "gvisor execute timeout=%s",
            seconds,
            extra={"event": "sandbox_execute"},
        )
        code = wrap_shell_as_python(command)
        try:
            result = _run_async(
                _call_sandbox_execute(code, "python-base", seconds),
            )
        except Exception as exc:
            logger.warning("MCP sandbox execute failed: %s", exc)
            return _execute_response(str(exc), 1)
        output, exit_code = _parse_execute_payload(result)
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
        output_mode: str = "files_with_matches",
    ) -> Any:
        return self._files.grep(pattern, path, glob, output_mode=output_mode)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        output_mode: str = "files_with_matches",
    ) -> Any:
        return await _to_thread(self.grep, pattern, path, glob, output_mode=output_mode)

    def glob(self, pattern: str, path: str = "/") -> Any:
        return self._files.glob(pattern, path)

    async def aglob(self, pattern: str, path: str = "/") -> Any:
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
