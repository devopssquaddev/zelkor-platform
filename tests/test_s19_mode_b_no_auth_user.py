"""S-19 / P4: Mode B without langgraph_auth_user sends no tenant headers; MCP fail-closed."""
from __future__ import annotations

from tests.helpers.ce8 import agent_pod, exec_python, running_pod_names


def _mode_b_pod() -> str:
    names = running_pod_names(label="app.kubernetes.io/component=aegra")
    if names:
        return names[0]
    return agent_pod()


def test_s19_no_auth_user_no_tenant_headers():
    pod = _mode_b_pod()
    script = (
        "from mcp_inject import identity_headers, tenant_from_run_config\n"
        "h=identity_headers({'configurable': {}})\n"
        "t=tenant_from_run_config({'configurable': {}})\n"
        "print('tenant='+repr(t))\n"
        "print('x_tenant='+repr(h.get('X-Tenant-ID')))\n"
    )
    out = exec_python(pod, script, timeout=20, site=True)
    assert "tenant=''" in out or 'tenant=""' in out, out
    assert "x_tenant=None" in out, out


def test_s19_tools_call_without_jwt_fail_closed():
    pod = _mode_b_pod()
    script = (
        "import json,os,sys,urllib.error,urllib.request\n"
        "base=(os.environ.get('MCP_URL') or 'http://zelkor-platform-mcp').rstrip('/')\n"
        "url=base if base.endswith('/mcp') else base+'/mcp'\n"
        "body=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call',"
        "'params':{'name':'postgres__query','arguments':{'sql':'SELECT 1'}}}).encode()\n"
        "req=urllib.request.Request(url,data=body,method='POST',"
        "headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'})\n"
        "try:\n"
        " urllib.request.urlopen(req,timeout=10)\n"
        " sys.stdout.write('status=200')\n"
        "except urllib.error.HTTPError as e:\n"
        " sys.stdout.write('status='+str(e.code))\n"
        "except Exception as e:\n"
        " sys.stdout.write('error='+type(e).__name__)\n"
    )
    out = exec_python(pod, script, timeout=25)
    line = out.splitlines()[-1] if out else ""
    assert line in {"status=401", "status=403"}, f"expected 401/403 without JWT, got {out!r}"
