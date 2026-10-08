"""C5: MCPRoute helm render (native refs, guards, no legacy gateway)."""
from __future__ import annotations

from pathlib import Path

from tests.test_helm_values_schema import PROFILES, _docs, _helm

INLINE_JWKS = Path(__file__).resolve().parent / "fixtures" / "lab-inline-jwks.yaml"


def _helm_local_jwks(*extra: str):
    return _helm(
        *extra,
        "--set",
        "platform.tenants.jwt.remoteJwksUri=",
        values_files=[INLINE_JWKS],
    )


def _mcproute(docs: list[dict]) -> dict:
    routes = [d for d in docs if d.get("kind") == "MCPRoute"]
    assert len(routes) == 1, f"expected one MCPRoute, got {[d['metadata']['name'] for d in routes]}"
    return routes[0]


def _native_backend_refs(route: dict) -> list[dict]:
    return [ref for ref in route["spec"].get("backendRefs") or [] if ref.get("forwardHeaders")]


def test_mcproute_absent_when_tools_disabled():
    r = _helm("--set", "workspace.tools.enabled=false")
    assert r.returncode == 0, r.stderr
    assert not [d for d in _docs(r.stdout) if d.get("kind") == "MCPRoute"]


def test_mcproute_requires_gateway_or_parent_ref():
    r = _helm("--set", "gateway.enabled=false", "--set", "gateway.parentRef.name=")
    assert r.returncode != 0
    assert "MCPRoute" in r.stderr or "gateway" in r.stderr


def test_native_backends_forward_authorization_only():
    r = _helm()
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    natives = _native_backend_refs(route)
    assert len(natives) >= 4
    for ref in natives:
        headers = [h.get("name") if isinstance(h, dict) else h for h in ref.get("forwardHeaders") or []]
        assert headers == ["Authorization"]
        assert ref.get("group") == "gateway.envoyproxy.io"
        assert ref.get("kind") == "Backend"


def test_native_ref_kind_service_uses_clusterip_names():
    r = _helm("--set", "gateway.mcproute.nativeRefKind=Service")
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    for ref in _native_backend_refs(route):
        assert ref.get("kind") == "Service"
        assert ref["name"].startswith("zelkor-platform-mcp-")
        assert ref.get("group") in (None, "")


def test_extra_backend_ref_has_no_authorization_forward():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=acme",
        "--set",
        "workspace.tools.extraBackends[0].service.name=acme-mcp",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    acme = next(ref for ref in route["spec"]["backendRefs"] if ref.get("name") == "acme")
    assert "forwardHeaders" not in acme or not acme.get("forwardHeaders")


def test_mcproute_local_jwks_when_no_remote_uri():
    r = _helm_local_jwks()
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    jwks = route["spec"]["securityPolicy"]["oauth"]["jwks"]
    assert "localJWKS" in jwks
    assert jwks["localJWKS"]["valueRef"]["name"] == "zelkor-platform-tenant-jwks"


def test_empty_mcp_hostname_uses_internal_dataplane_hostnames():
    r = _helm("--set", "gateway.hosts.mcp=")
    assert r.returncode == 0, r.stderr
    route = _mcproute(_docs(r.stdout))
    hostnames = route["spec"].get("hostnames") or []
    assert any("zelkor-platform-mcp" in h for h in hostnames)


def test_mcp_externalname_in_release_namespace():
    """Short MCP_URL DNS (http://<release>-mcp) resolves from seed/agent pods."""
    r = _helm()
    assert r.returncode == 0, r.stderr
    svcs = [
        d
        for d in _docs(r.stdout)
        if d.get("kind") == "Service"
        and d.get("metadata", {}).get("name") == "zelkor-platform-mcp"
    ]
    assert len(svcs) == 1
    svc = svcs[0]
    assert svc["metadata"].get("namespace") == "zelkor"
    assert svc["spec"]["type"] == "ExternalName"
    assert svc["spec"]["externalName"]
    assert "localhost" not in svc["spec"]["externalName"]


def test_shared_gateway_requires_ack():
    r = _helm(
        "--set",
        "gateway.enabled=false",
        "--set",
        "gateway.parentRef.name=shared-gw",
        "--set",
        "gateway.parentRef.namespace=envoy-system",
        "--set",
        "gateway.envoyProxy.enabled=false",
        "--set",
        "workspace.models.inClusterService.enabled=true",
        "--set",
        "workspace.models.inClusterService.targetHost=envoy.example.svc",
        "--set",
        "security.mcp.acceptUnprotectedBackends=true",
    )
    assert r.returncode != 0
    assert "sharedGatewayAck" in r.stderr


def test_reserved_extra_backend_name_fails():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=postgres",
        "--set",
        "workspace.tools.extraBackends[0].service.name=x",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode != 0
    assert "reserved" in r.stderr


def test_no_legacy_mcp_gateway_objects_in_profiles():
    for profile in PROFILES.glob("values*.yaml"):
        r = _helm(values_files=[profile])
        assert r.returncode == 0, f"{profile.name}: {r.stderr}"
        lowered = r.stdout.lower()
        assert "mcp-gateway" not in lowered
        assert "mcp_gateway" not in lowered


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
]


def test_reserved_object_backend_name_fails():
    r = _helm(
        "--set",
        "workspace.tools.extraBackends[0].name=object",
        "--set",
        "workspace.tools.extraBackends[0].service.name=x",
        "--set",
        "workspace.tools.extraBackends[0].service.port=8080",
    )
    assert r.returncode != 0
    assert "reserved" in r.stderr


def test_object_mcp_requires_endpoint_and_bucket():
    r = _helm("--set", "workspace.tools.objectMCP.enabled=true")
    assert r.returncode != 0
    assert "endpoint" in r.stderr


def test_object_mcp_backend_ref_and_no_s3_env_on_agent_or_worker():
    r = _helm(*_OBJECT_SETS)
    assert r.returncode == 0, r.stderr
    docs = _docs(r.stdout)
    route = _mcproute(docs)
    names = [ref.get("name") for ref in route["spec"]["backendRefs"]]
    assert "object" in names
    backends = [
        d
        for d in docs
        if d.get("kind") == "Backend" and d.get("metadata", {}).get("name") == "object"
    ]
    assert len(backends) == 1
    forbidden = []
    for doc in docs:
        if doc.get("kind") != "Deployment":
            continue
        name = doc["metadata"]["name"]
        if not (name.endswith("-aegra") or "sandbox-worker" in name):
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            for env in container.get("env") or []:
                if env.get("name", "").startswith("OBJECT_S3") or env.get("name", "").startswith("AWS_"):
                    forbidden.append((name, env["name"]))
    assert forbidden == []
    worker = next(
        d
        for d in docs
        if d.get("kind") == "NetworkPolicy" and d["metadata"]["name"].endswith("sandbox-worker-egress")
    )
    assert worker["spec"]["egress"] == []


def test_object_mcp_renders_seaweedfs_without_langfuse():
    r = _helm(
        *_OBJECT_SETS,
        "--set",
        "platform.telemetry.langfuse.enabled=false",
    )
    assert r.returncode == 0, r.stderr
    docs = _docs(r.stdout)
    deploy = next(
        d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-seaweedfs")
    )
    command = "\n".join(deploy["spec"]["template"]["spec"]["containers"][0]["command"])
    assert "-volume.max=16" in command
    assert "-master.volumeSizeLimitMB=1024" in command
    assert "Collection:zelkor-objects" in command
    assert "/vol/grow?collection=zelkor-objects&count=1" in command
    assert "hostname -i" in command
    assert "nodeSelector" not in deploy["spec"]["template"]["spec"]
    assert any(d.get("kind") == "PersistentVolumeClaim" and "seaweedfs" in d["metadata"]["name"] for d in docs)
    secret = next(d for d in docs if d.get("kind") == "Secret" and d["metadata"]["name"].endswith("-seaweedfs"))
    config = secret["stringData"]["s3-config.json"]
    assert "Read:zelkor-objects" in config
    assert "Admin" in config


def test_external_object_store_does_not_render_seaweedfs_without_langfuse():
    r = _helm(
        "--set",
        "platform.telemetry.langfuse.enabled=false",
        "--set",
        "workspace.tools.objectMCP.enabled=true",
        "--set",
        "workspace.tools.objectMCP.s3.endpoint=https://s3.amazonaws.com",
        "--set",
        "workspace.tools.objectMCP.s3.bucket=customer-objects",
        "--set",
        "workspace.tools.objectMCP.s3.auth.accessKey=obj-ak",
        "--set",
        "workspace.tools.objectMCP.s3.auth.secretKey=obj-sk",
        "--set",
        "workspace.tools.objectMCP.s3.egressCIDRs[0]=203.0.113.0/24",
        "--set",
        "security.networkPolicies.enabled=true",
    )
    assert r.returncode == 0, r.stderr
    docs = _docs(r.stdout)
    assert not any(
        d.get("kind") == "Deployment" and str(d.get("metadata", {}).get("name", "")).endswith("-seaweedfs")
        for d in docs
    )


def test_seaweedfs_empty_dir_when_persistence_disabled():
    r = _helm("--set", "seaweedfs.persistence.enabled=false")
    assert r.returncode == 0, r.stderr
    docs = _docs(r.stdout)
    assert not any(d.get("kind") == "PersistentVolumeClaim" for d in docs)
    deploy = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-seaweedfs"))
    data = next(v for v in deploy["spec"]["template"]["spec"]["volumes"] if v["name"] == "data")
    assert "emptyDir" in data

