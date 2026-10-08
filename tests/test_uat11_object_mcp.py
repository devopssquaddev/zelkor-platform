"""UAT-11 object MCP render contract. Live calls are tests/test_mcp_object.py."""
from __future__ import annotations

from tests.test_helm_values_schema import _docs, _helm

_OBJECT_SETS = [
    "--set",
    "workspace.tools.objectMCP.enabled=true",
    "--set",
    "workspace.tools.objectMCP.s3.endpoint=http://zelkor-platform-seaweedfs:8333",
    "--set",
    "workspace.tools.objectMCP.s3.bucket=zelkor-objects",
    "--set",
    "workspace.tools.objectMCP.s3.auth.accessKey=obj-ak",
    "--set",
    "workspace.tools.objectMCP.s3.auth.secretKey=obj-sk",
    "--set",
    "seaweedfs.objectIdentity.accessKey=obj-ak",
    "--set",
    "seaweedfs.objectIdentity.secretKey=obj-sk",
    "--set",
    "security.networkPolicies.enabled=true",
]


def test_uat11_object_mcp_off_by_default():
    rendered = _helm()
    assert rendered.returncode == 0, rendered.stderr
    names = [
        doc.get("metadata", {}).get("name", "")
        for doc in _docs(rendered.stdout)
        if doc and doc.get("kind") == "Deployment"
    ]
    assert not any(name.endswith("-mcp-object") for name in names)


def test_uat11_object_backend_delete_off_and_no_s3_on_agent_or_worker():
    rendered = _helm(*_OBJECT_SETS)
    assert rendered.returncode == 0, rendered.stderr
    docs = _docs(rendered.stdout)
    route = next(doc for doc in docs if doc and doc.get("kind") == "MCPRoute")
    assert any(ref.get("name") == "object" for ref in route["spec"]["backendRefs"])
    deploy = next(
        doc
        for doc in docs
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"].endswith("-mcp-object")
    )
    env = {
        item["name"]: item.get("value")
        for item in deploy["spec"]["template"]["spec"]["containers"][0]["env"]
        if "value" in item
    }
    assert env["OBJECT_ALLOW_DELETE"] == "false"
    leaked = []
    for doc in docs:
        if not doc or doc.get("kind") != "Deployment":
            continue
        name = doc["metadata"]["name"]
        if not (name.endswith("-aegra") or "sandbox-worker" in name):
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            for item in container.get("env") or []:
                if item.get("name", "").startswith(("OBJECT_S3", "AWS_")):
                    leaked.append((name, item["name"]))
    assert leaked == []
    worker = next(
        doc
        for doc in docs
        if doc
        and doc.get("kind") == "NetworkPolicy"
        and doc["metadata"]["name"].endswith("sandbox-worker-egress")
    )
    assert worker["spec"]["egress"] == []
    object_egress = next(
        doc
        for doc in docs
        if doc
        and doc.get("kind") == "NetworkPolicy"
        and doc["metadata"]["name"].endswith("mcp-object-egress")
    )
    s3_ports = []
    for rule in object_egress["spec"]["egress"]:
        for peer in rule.get("to") or []:
            labels = (peer.get("podSelector") or {}).get("matchLabels") or {}
            if labels.get("app.kubernetes.io/component") == "seaweedfs":
                s3_ports.extend(port.get("port") for port in rule.get("ports") or [])
    assert s3_ports == [8333]


def test_uat11_reserved_object_name_fails():
    rendered = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=object",
        "--set",
        "workspace.tools.extraBackends[0].service.name=x",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert rendered.returncode != 0
    assert "reserved" in rendered.stderr
