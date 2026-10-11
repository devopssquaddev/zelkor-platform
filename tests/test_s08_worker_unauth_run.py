"""S-08 / P7: unauthenticated POST worker /run is 403 (live)."""
from __future__ import annotations

import pytest

from tests.helpers.ce8 import exec_python, sandbox_mcp_pod, worker_service


def test_s08_unauthenticated_worker_run_is_403():
    pod = sandbox_mcp_pod()
    host, port = worker_service()
    script = (
        "import json,sys,urllib.error,urllib.request\n"
        f"url='http://{host}:{port}/run'\n"
        "body=json.dumps({'code':'print(1)','timeout':2}).encode()\n"
        "req=urllib.request.Request(url,data=body,method='POST',"
        "headers={'Content-Type':'application/json'})\n"
        "try:\n"
        " urllib.request.urlopen(req,timeout=8)\n"
        " sys.stdout.write('status=200')\n"
        "except urllib.error.HTTPError as e:\n"
        " sys.stdout.write('status='+str(e.code))\n"
        "except Exception as e:\n"
        " sys.stdout.write('error='+type(e).__name__)\n"
    )
    out = exec_python(pod, script, timeout=25)
    line = out.splitlines()[-1] if out else ""
    if line.startswith("error="):
        pytest.skip(f"worker /run not reachable from {pod}: {line}")
    assert line == "status=403", f"expected 403 from {pod} POST {host}:{port}/run, got {out!r}"
