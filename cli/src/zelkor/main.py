"""zelkor CLI — one packager for every agent."""
from __future__ import annotations

import argparse
import base64
import dataclasses
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

import yaml

from zelkor import __version__
from zelkor.detect import (
    DetectError,
    agent_deployment_name,
    customer_dockerfile,
    deploy_first_langgraph,
    detect,
    helm_release_name,
    mcp_servers_from_tools,
    should_attach_as_default,
)
from zelkor.envfile import Env, add_env, list_envs, load_store, remove_env, resolve_env
from zelkor.extra_backends import format_missing_extras_error, missing_extra_registrations
from zelkor.token_cmd import cmd_token_jwks, cmd_token_mint

PAID = frozenset({"login", "license", "whoami", "team", "budget", "audit"})
UPGRADE = "This command requires Zelkor Pro or Enterprise. Community Edition does not apply it."

logger = logging.getLogger("zelkor-cli")

RunFn = Callable[..., subprocess.CompletedProcess]


@dataclass
class PlatformInfo:
    release: str = ""
    chart_version: str = ""
    database_url: str = ""
    openai_base_url: str = ""
    mcp_url: str = ""
    redis_url: str = ""
    agents_host: str = ""
    gateway_name: str = ""
    gateway_namespace: str = ""
    jwt_issuer: str = ""
    jwt_audiences: list[str] = field(default_factory=list)
    jwt_jwks_configmap: str = ""
    jwt_tenant_claims: list[str] = field(default_factory=lambda: ["tenant_id", "org_id", "sub"])
    default_llm_model: str = ""
    langfuse_base_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    otel_targets: str = ""
    agent_route_names: list[str] = field(default_factory=list)
    image_pull_secrets: list[dict[str, str]] = field(default_factory=list)
    helm_values: dict[str, Any] = field(default_factory=dict)
    network_policies_enabled: bool = False
    gateway_host_cidrs: list[str] = field(default_factory=list)


def find_chart(start: Path, chart_name: str, explicit: str = "", env_key: str = "") -> Path:
    if explicit:
        path = Path(explicit)
        if (path / "Chart.yaml").is_file():
            return path
        raise FileNotFoundError(f"chart not found: {explicit}")
    env_val = os.getenv(env_key, "").strip() if env_key else ""
    if env_val:
        path = Path(env_val)
        if (path / "Chart.yaml").is_file():
            return path
        raise FileNotFoundError(f"{env_key} is not a chart: {env_val}")
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        cand = parent / "charts" / chart_name
        if (cand / "Chart.yaml").is_file():
            return cand
    raise FileNotFoundError(f"charts/{chart_name} not found from {start}")


KUBE_REQUEST_TIMEOUT = os.getenv("ZELKOR_KUBE_TIMEOUT", "30s").strip() or "30s"
KUBE_RUN_TIMEOUT_SEC = float(os.getenv("ZELKOR_KUBE_RUN_TIMEOUT_SEC", "45"))
HELM_UPGRADE_TIMEOUT_SEC = float(os.getenv("ZELKOR_HELM_UPGRADE_TIMEOUT_SEC", "180"))


def _argv_for_log(argv: list[str]) -> str:
    text = " ".join(argv)
    return text if len(text) <= 240 else text[:237] + "..."


def _flush_logs() -> None:
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except ValueError:
            pass
    for handler in logger.handlers:
        try:
            handler.flush()
        except ValueError:
            pass
    try:
        sys.stderr.flush()
    except Exception:
        pass


def _stream_child(argv: list[str]) -> bool:
    return bool(argv) and argv[0] in {"docker", "kind"}


def _run(
    argv: list[str],
    *,
    runner: Optional[RunFn] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    if _stream_child(argv):
        capture = False
    line = _argv_for_log(argv)
    if capture:
        logger.debug("run %s", line)
    else:
        logger.info("run %s", line)
        _flush_logs()
    fn = runner or subprocess.run
    kw: dict[str, Any] = {"text": True, "check": False}
    if timeout is not None:
        kw["timeout"] = timeout
    if capture:
        kw["capture_output"] = True
    else:
        kw["stdout"] = sys.stderr
        kw["stderr"] = sys.stderr
    started = time.monotonic()
    try:
        res = fn(argv, **kw)
    except TypeError:
        res = fn(argv, capture_output=capture, text=True, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(argv)} timed out after {timeout}s") from exc
    elapsed = time.monotonic() - started
    if not capture:
        logger.info("done %s elapsed=%.1fs rc=%s", argv[0] if argv else "cmd", elapsed, res.returncode)
        _flush_logs()
    if check and res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(f"{' '.join(argv)} failed: {err}")
    return res


def kube_argv(env: Env, *args: str) -> list[str]:
    cmd = ["kubectl", "--request-timeout", KUBE_REQUEST_TIMEOUT, "--context", env.kube_context, "-n", env.namespace]
    if env.kubeconfig:
        cmd[1:1] = ["--kubeconfig", env.kubeconfig]
    cmd.extend(args)
    return cmd


def helm_argv(env: Env, *args: str) -> list[str]:
    cmd = ["helm", "--kube-context", env.kube_context, "-n", env.namespace]
    if env.kubeconfig:
        cmd[1:1] = ["--kubeconfig", env.kubeconfig]
    cmd.extend(args)
    return cmd


def _container_env(deploy: dict[str, Any]) -> dict[str, str]:
    spec = (((deploy.get("spec") or {}).get("template") or {}).get("spec") or {})
    containers = spec.get("containers") or []
    if not containers:
        return {}
    out: dict[str, str] = {}
    for item in containers[0].get("env") or []:
        name = item.get("name")
        if name and "value" in item:
            out[str(name)] = str(item.get("value") or "")
    return out


def kind_node_cidrs(env: Env, *, runner: Optional[RunFn] = None) -> list[str]:
    """Kind only: /32 sources of a hostNetwork Envoy (agent ingress NetworkPolicy).

    Per node: its InternalIP, and the first host of its podCIDR (kindnet routes host to
    local-pod traffic with that source address).
    """
    out = _run(
        kube_argv(env, "get", "nodes", "-o",
                  "jsonpath={range .items[*]}{.status.addresses[?(@.type=='InternalIP')].address}"
                  " {.spec.podCIDR}{'\\n'}{end}"),
        runner=runner, check=False, timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    cidrs = set()
    for line in (getattr(out, "stdout", "") or "").splitlines():
        for token in line.split():
            try:
                if "/" in token:
                    net = ipaddress.ip_network(token, strict=False)
                    if net.version == 4 and net.num_addresses > 2:
                        cidrs.add(f"{net.network_address + 1}/32")
                else:
                    addr = ipaddress.ip_address(token)
                    if addr.version == 4:
                        cidrs.add(f"{addr}/32")
            except ValueError:
                continue
    return sorted(cidrs)


def _np_values(info: "PlatformInfo") -> dict[str, Any]:
    np: dict[str, Any] = {"enabled": info.network_policies_enabled}
    if info.gateway_host_cidrs:
        np["hostNetworkGatewayCIDRs"] = list(info.gateway_host_cidrs)
    return {"networkPolicies": np}


def discover_platform(env: Env, runner: Optional[RunFn] = None) -> PlatformInfo:
    logger.info(
        "discover platform env=%s context=%s namespace=%s",
        env.name,
        env.kube_context,
        env.namespace,
    )
    info = PlatformInfo()
    logger.info("helm list")
    listed = _run(
        helm_argv(env, "list", "-o", "json"),
        runner=runner,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    releases = json.loads(listed.stdout or "[]")
    for rel in releases:
        chart = str(rel.get("chart") or "")
        if chart.startswith("zelkor-platform"):
            info.release = str(rel.get("name") or "")
            info.chart_version = chart.split("-")[-1] if "-" in chart else chart
            break
    if not info.release:
        raise RuntimeError("zelkor-platform Helm release not found in this env")
    logger.info("found platform release=%s chart=%s", info.release, info.chart_version)
    logger.info("helm get values %s", info.release)
    values_raw = _run(
        helm_argv(env, "get", "values", info.release, "-o", "yaml"),
        runner=runner,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    values = yaml.safe_load(values_raw.stdout or "") or {}
    if isinstance(values, dict):
        info.helm_values = values
    hosts = ((values.get("gateway") or {}).get("hosts") or {})
    info.agents_host = str(hosts.get("agents") or hosts.get("aegra") or "")
    info.image_pull_secrets = list((values.get("global") or {}).get("imagePullSecrets") or [])
    info.network_policies_enabled = bool(
        ((values.get("security") or {}).get("networkPolicies") or {}).get("enabled")
    )
    info.gateway_namespace = env.namespace
    if info.network_policies_enabled and _is_kind(env):
        info.gateway_host_cidrs = kind_node_cidrs(env, runner=runner)
    logger.info("agents host=%s", info.agents_host or "(empty)")
    logger.info("get aegra deployment")
    deploys = _run(
        kube_argv(env, "get", "deploy", "-l", "app.kubernetes.io/component=aegra", "-o", "json"),
        runner=runner,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    items = (json.loads(deploys.stdout or "{}") or {}).get("items") or []
    for dep in items:
        labels = (dep.get("metadata") or {}).get("labels") or {}
        if labels.get("zelkor.io/workload-type") == "agent":
            continue
        env_map = _container_env(dep)
        info.database_url = env_map.get("DATABASE_URL", "")
        info.openai_base_url = env_map.get("OPENAI_BASE_URL", "")
        info.mcp_url = env_map.get("MCP_URL", "")
        info.redis_url = env_map.get("REDIS_URL", "")
        info.jwt_issuer = env_map.get("AUTH_JWT_ISSUER", "")
        aud_raw = env_map.get("AUTH_JWT_AUDIENCES", "")
        if aud_raw.startswith("["):
            try:
                info.jwt_audiences = list(json.loads(aud_raw))
            except json.JSONDecodeError:
                info.jwt_audiences = []
        elif aud_raw:
            info.jwt_audiences = [a.strip() for a in aud_raw.split(",") if a.strip()]
        claims_raw = env_map.get("AUTH_TENANT_CLAIMS", "tenant_id,org_id,sub")
        if claims_raw.startswith("["):
            try:
                parsed = json.loads(claims_raw)
                info.jwt_tenant_claims = [str(c) for c in parsed] if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                info.jwt_tenant_claims = []
        elif claims_raw:
            info.jwt_tenant_claims = [c.strip() for c in claims_raw.split(",") if c.strip()]
        info.jwt_jwks_configmap = f"{info.release}-tenant-jwks"
        info.default_llm_model = default_llm_model_from(env_map, values)
        info.langfuse_base_url = env_map.get("LANGFUSE_BASE_URL", "")
        info.langfuse_public_key = env_map.get("LANGFUSE_PUBLIC_KEY", "")
        info.langfuse_secret_key = env_map.get("LANGFUSE_SECRET_KEY", "")
        info.otel_targets = env_map.get("OTEL_TARGETS", "")
        name = (dep.get("metadata") or {}).get("name") or ""
        if name:
            info.gateway_name = f"{str(name).rsplit('-aegra', 1)[0]}-gateway"
        break
    logger.info("get httproutes")
    routes = _run(
        kube_argv(env, "get", "httproute", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if routes.returncode == 0:
        for route in (json.loads(routes.stdout or "{}") or {}).get("items") or []:
            labels = (route.get("metadata") or {}).get("labels") or {}
            rname = str((route.get("metadata") or {}).get("name") or "")
            if labels.get("zelkor.io/workload-type") == "agent" or rname.endswith("-zelkor-agent-route"):
                info.agent_route_names.append(rname)
            if not info.gateway_name:
                refs = (route.get("spec") or {}).get("parentRefs") or []
                if refs:
                    info.gateway_name = str(refs[0].get("name") or "")
                    info.gateway_namespace = str(refs[0].get("namespace") or env.namespace)
    cluster_gw = in_cluster_openai_base_url(env, runner=runner)
    if cluster_gw:
        info.openai_base_url = cluster_gw
    if not info.default_llm_model:
        info.default_llm_model = default_llm_model_from({}, values)
    logger.info(
        "discover done release=%s gateway=%s model=%s",
        info.release,
        info.gateway_name or "(none)",
        info.default_llm_model or "(none)",
    )
    return info


def in_cluster_openai_base_url(env: Env, runner: Optional[RunFn] = None) -> str:
    """Use *-ai-gateway Service DNS so Host matches AIGatewayRoute (not Envoy data-plane FQDN)."""
    svcs = _run(
        kube_argv(env, "get", "svc", "-l", "app.kubernetes.io/component=ai-gateway", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if svcs.returncode != 0:
        return ""
    for svc in (json.loads(svcs.stdout or "{}") or {}).get("items") or []:
        sname = str((svc.get("metadata") or {}).get("name") or "")
        if not sname.endswith("-ai-gateway"):
            continue
        ports = (svc.get("spec") or {}).get("ports") or []
        port = ports[0].get("port") if ports else 80
        return f"http://{sname}:{port}/v1"
    return ""


def default_llm_model_from(env_map: dict[str, str], values: dict[str, Any]) -> str:
    direct = (env_map.get("DEFAULT_LLM_MODEL") or "").strip()
    if direct:
        return direct
    nemo = str(((values.get("guardrails") or {}).get("nemo") or {}).get("model") or "").strip()
    if nemo:
        return nemo
    gateway_default = str((values.get("aiGateway") or {}).get("defaultModel") or "").strip()
    if gateway_default:
        return gateway_default
    workspace_default = str(
        (((values.get("workspace") or {}).get("models") or {}).get("defaultModel") or "")
    ).strip()
    if workspace_default:
        return workspace_default
    models = (((values.get("langfuse") or {}).get("surfaces") or {}).get("llmConnection") or {}).get("models") or []
    if isinstance(models, list) and models:
        return str(models[0] or "").strip()
    return ""


def _truthy(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def auth_values(info: PlatformInfo) -> dict[str, Any]:
    """Copy live platform JWT contract onto the worker. Do not invent secrets."""
    return {
        "issuer": info.jwt_issuer,
        "audiences": info.jwt_audiences,
        "jwksConfigMap": info.jwt_jwks_configmap,
        "tenantClaims": info.jwt_tenant_claims,
    }


RUNTIMES = ("aegra", "a2a", "opencode")
A2A_FRAMEWORKS = ("pydantic-ai", "crewai")


def runtime_base_image(runtime: str, a2a_framework: str, tag: str) -> str:
    """Base image a deploy-first project builds FROM (CE-14). Tag follows Chart appVersion."""
    if runtime == "aegra":
        return _deep_base_image(tag)
    if runtime == "a2a":
        if a2a_framework not in A2A_FRAMEWORKS:
            raise RuntimeError(f"--a2a-framework must be one of {', '.join(A2A_FRAMEWORKS)}")
        default = f"ghcr.io/devopssquaddev/zelkor-runtime-{a2a_framework}:{tag}"
    else:
        default = f"ghcr.io/devopssquaddev/zelkor-runtime-{runtime}:{tag}"
    return os.getenv("ZELKOR_RUNTIME_IMAGE", "").strip() or default


def _write_build_context(src: Path, dest: Path, shape_kind: str, graph_id: str, *,
                         base_image: str, runtime: str = "aegra") -> None:
    ignore = {".git", ".zelkor", "__pycache__", ".venv", ".pytest_cache"}
    for item in src.iterdir():
        if item.name in ignore:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*ignore, "*.pyc"))
        else:
            shutil.copy2(item, target)
    if runtime == "a2a" and (src / "Dockerfile").is_file():
        return  # BYO A2A image: the project's own Dockerfile serves A2A on 127.0.0.1:8080
    (dest / "Dockerfile").write_text(customer_dockerfile(base_image), encoding="utf-8")
    if shape_kind == "deploy-first" and runtime == "aegra":
        (dest / "langgraph.json").write_text(
            json.dumps(deploy_first_langgraph(graph_id), indent=2),
            encoding="utf-8",
        )


def _is_kind(env: Env) -> bool:
    return env.kube_context.startswith("kind-") or os.getenv("KIND_CLUSTER", "") != ""


def _skip_build() -> bool:
    return _truthy(os.getenv("ZELKOR_SKIP_BUILD", ""))


def _chart_repo_root(agent_chart: Path) -> Path:
    return agent_chart.resolve().parent.parent


def _chart_app_version(agent_chart: Path) -> str:
    chart = yaml.safe_load((agent_chart / "Chart.yaml").read_text(encoding="utf-8")) or {}
    return str(chart.get("appVersion") or "dev").strip().strip('"')


def _kind_cluster_name(env: Env) -> str:
    return os.getenv("KIND_CLUSTER") or env.kube_context.removeprefix("kind-")


def _deep_base_image(tag: str) -> str:
    return os.getenv("ZELKOR_DEEP_IMAGE", "").strip() or f"ghcr.io/devopssquaddev/zelkor-aegra-deep:{tag}"


def _build_catalog_image(
    *,
    env: Env,
    image_ref: str,
    dockerfile: Path,
    context: Path,
    tag: str,
    runner: Optional[RunFn],
    push: bool,
) -> None:
    deep = _deep_base_image(tag)
    logger.info("building %s dockerfile=%s context=%s base=%s", image_ref, dockerfile, context, deep)
    logger.info("docker build first pull can take several minutes; layer progress follows")
    _run(
        [
            "docker",
            "build",
            "--progress=plain",
            "-f",
            str(dockerfile),
            "-t",
            image_ref,
            "--build-arg",
            f"ZELKOR_AEGRA_DEEP_IMAGE={deep}",
            str(context),
        ],
        runner=runner,
    )
    logger.info("built %s", image_ref)
    if push:
        logger.info("push %s", image_ref)
        _run(["docker", "push", image_ref], runner=runner)
    elif _is_kind(env):
        cluster = _kind_cluster_name(env)
        logger.info("kind load %s cluster=%s", image_ref, cluster)
        _run(["kind", "load", "docker-image", image_ref, "--name", cluster], runner=runner)
        logger.info("kind-loaded %s; kubelet will not pull this tag", image_ref)


def _require_registered_extras(info: PlatformInfo, servers: tuple[dict[str, str], ...] | list[dict[str, str]]) -> None:
    if not servers:
        return
    missing = missing_extra_registrations(servers, info.helm_values)
    if missing:
        raise RuntimeError(format_missing_extras_error(missing))


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def fill_empty(dst: Any, src: Any) -> Any:
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return src if _is_empty(dst) else dst
    out = dict(dst)
    for key, val in src.items():
        cur = out.get(key)
        if key not in out or _is_empty(cur):
            out[key] = val
        elif isinstance(cur, dict) and isinstance(val, dict):
            out[key] = fill_empty(cur, val)
    return out


_FILE_WINS = frozenset({"graphId", "image", "runtimeClassName", "extraEnv"})


def env_for_namespace(env: Env, namespace: str) -> Env:
    ns = (namespace or "").strip() or env.namespace
    if ns == env.namespace:
        return env
    return Env(name=env.name, kube_context=env.kube_context, namespace=ns, kubeconfig=env.kubeconfig)


def rewrite_in_cluster_url(url: str, platform_ns: str) -> str:
    if not url or not platform_ns:
        return url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host or host.endswith(".svc.cluster.local"):
        return url
    if host.endswith(".svc"):
        new_host = f"{host}.cluster.local"
    elif "." not in host:
        new_host = f"{host}.{platform_ns}.svc.cluster.local"
    else:
        return url
    auth = ""
    if parsed.username is not None:
        auth = parsed.username
        if parsed.password is not None:
            auth += f":{parsed.password}"
        auth += "@"
    port = parsed.port
    netloc = f"{auth}{new_host}:{port}" if port else f"{auth}{new_host}"
    return urlunparse(parsed._replace(netloc=netloc))


def bind_worker_to_agent_namespace(info: PlatformInfo, agent_ns: str, platform_ns: str) -> PlatformInfo:
    if not agent_ns or agent_ns == platform_ns:
        return info
    rel = info.release
    info.openai_base_url = f"http://{rel}-ai-gateway.{platform_ns}.svc.cluster.local:80/v1"
    info.mcp_url = rewrite_in_cluster_url(info.mcp_url, platform_ns) or f"http://{rel}-mcp.{platform_ns}.svc.cluster.local"
    info.langfuse_base_url = f"http://{rel}-langfuse.{platform_ns}.svc.cluster.local:3000"
    info.database_url = rewrite_in_cluster_url(info.database_url, platform_ns)
    info.redis_url = rewrite_in_cluster_url(info.redis_url, platform_ns)
    return info


def fill_langfuse_from_secret(env: Env, info: PlatformInfo, runner: Optional[RunFn] = None) -> None:
    if info.langfuse_public_key and info.langfuse_secret_key:
        return
    name = f"{info.release}-langfuse-otel"
    got = _run(kube_argv(env, "get", "secret", name, "-o", "json"), runner=runner, check=False, timeout=KUBE_RUN_TIMEOUT_SEC)
    if got.returncode != 0:
        return
    data = (json.loads(got.stdout or "{}") or {}).get("data") or {}
    def _b64(key: str) -> str:
        raw = data.get(key) or ""
        if not raw:
            return ""
        try:
            return base64.b64decode(raw).decode("utf-8")
        except Exception:
            return ""
    info.langfuse_public_key = info.langfuse_public_key or _b64("LANGFUSE_PUBLIC_KEY")
    info.langfuse_secret_key = info.langfuse_secret_key or _b64("LANGFUSE_SECRET_KEY")
    info.langfuse_base_url = info.langfuse_base_url or _b64("LANGFUSE_BASE_URL")
    info.otel_targets = info.otel_targets or _b64("OTEL_TARGETS") or info.otel_targets


def copy_verify_configmaps(
    env: Env,
    dest_ns: str,
    names: list[str],
    *,
    runner: Optional[RunFn] = None,
) -> None:
    if dest_ns == env.namespace:
        return
    dest_env = env_for_namespace(env, dest_ns)
    for name in names:
        got = _run(
            kube_argv(env, "get", "cm", name, "-o", "json"),
            runner=runner,
            check=False,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )
        if got.returncode != 0:
            logger.info("skip copy configmap %s (not in platform ns)", name)
            continue
        obj = json.loads(got.stdout or "{}") or {}
        meta = obj.setdefault("metadata", {})
        meta["namespace"] = dest_ns
        for key in ("resourceVersion", "uid", "creationTimestamp", "managedFields", "selfLink"):
            meta.pop(key, None)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(obj, fh)
            path = fh.name
        try:
            _run(
                kube_argv(dest_env, "apply", "-f", path),
                runner=runner,
                timeout=KUBE_RUN_TIMEOUT_SEC,
            )
        finally:
            Path(path).unlink(missing_ok=True)


def copy_named_secrets(
    env: Env,
    dest_ns: str,
    names: list[str],
    *,
    runner: Optional[RunFn] = None,
) -> None:
    if dest_ns == env.namespace:
        return
    dest_env = env_for_namespace(env, dest_ns)
    for name in names:
        if not name:
            continue
        got = _run(
            kube_argv(env, "get", "secret", name, "-o", "json"),
            runner=runner,
            check=False,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )
        if got.returncode != 0:
            logger.info("skip copy secret %s (not in platform ns)", name)
            continue
        obj = json.loads(got.stdout or "{}") or {}
        meta = obj.setdefault("metadata", {})
        meta["namespace"] = dest_ns
        for key in ("resourceVersion", "uid", "creationTimestamp", "managedFields", "selfLink"):
            meta.pop(key, None)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(obj, fh)
            path = fh.name
        try:
            _run(
                kube_argv(dest_env, "apply", "-f", path),
                runner=runner,
                timeout=KUBE_RUN_TIMEOUT_SEC,
            )
        finally:
            Path(path).unlink(missing_ok=True)


def find_agent_release_namespace(
    env: Env, release: str, *, runner: Optional[RunFn] = None
) -> str:
    listed = _run(
        helm_argv(env, "list", "-A", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if listed.returncode != 0:
        return env.namespace
    for rel in json.loads(listed.stdout or "[]"):
        if str(rel.get("name") or "") == release:
            return str(rel.get("namespace") or env.namespace)
    return env.namespace


def discovered_worker_values(info: PlatformInfo, *, platform_namespace: str = "") -> dict[str, Any]:
    platform: dict[str, Any] = {
        "releaseName": info.release,
        "databaseUrl": info.database_url,
        "openaiBaseUrl": info.openai_base_url,
        "mcpUrl": info.mcp_url,
        # No consumerKey literal: the chart reads {releaseName}-ai-gateway-consumer by reference, so
        # the key stays out of Helm values and the Deployment, and a rotation restarts the agent.
        "valkeyUrl": info.redis_url,
        "mcpInject": True,
    }
    if platform_namespace:
        platform["namespace"] = platform_namespace
    if info.default_llm_model:
        platform["defaultLlmModel"] = info.default_llm_model
    if info.langfuse_base_url:
        platform["langfuseBaseUrl"] = info.langfuse_base_url
    if info.langfuse_public_key:
        platform["langfusePublicKey"] = info.langfuse_public_key
    if info.langfuse_secret_key:
        platform["langfuseSecretKey"] = info.langfuse_secret_key
    if info.otel_targets:
        platform["otelTargets"] = info.otel_targets
    overlay: dict[str, Any] = {
        "sharedRoute": {
            "host": info.agents_host,
            "gatewayName": info.gateway_name,
            "gatewayNamespace": info.gateway_namespace,
        },
        "platform": platform,
        "auth": auth_values(info),
        "security": _np_values(info),
    }
    if info.image_pull_secrets:
        overlay["global"] = {"imagePullSecrets": info.image_pull_secrets}
    return overlay


def merge_catalog_values(file_values: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    kept = {key: file_values[key] for key in _FILE_WINS if key in file_values}
    rest = {key: val for key, val in file_values.items() if key not in _FILE_WINS}
    sr = rest.get("sharedRoute")
    if isinstance(sr, dict) and "asDefault" not in sr:
        disc_sr = dict((discovered.get("sharedRoute") or {}))
        disc_sr.pop("asDefault", None)
        discovered = dict(discovered)
        discovered["sharedRoute"] = disc_sr
    merged = fill_empty(rest, discovered)
    merged.update(kept)
    return merged


ROLLOUT_WAIT_SEC = float(os.getenv("ZELKOR_ROLLOUT_TIMEOUT_SEC", "180"))


def _rs_revision(rs: dict[str, Any]) -> int:
    raw = ((rs.get("metadata") or {}).get("annotations") or {}).get("deployment.kubernetes.io/revision")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _pod_template_hash(obj: dict[str, Any]) -> str:
    return str(((obj.get("metadata") or {}).get("labels") or {}).get("pod-template-hash") or "")


def _current_template_hash(env: Env, release: str, runner: Optional[RunFn] = None) -> str:
    res = _run(
        kube_argv(env, "get", "rs", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if res.returncode != 0:
        return ""
    best_rev = -1
    best_hash = ""
    for rs in (json.loads(res.stdout or "{}") or {}).get("items") or []:
        rev = _rs_revision(rs)
        if rev >= best_rev:
            best_rev = rev
            best_hash = _pod_template_hash(rs)
    return best_hash


def _prune_stale_agent_pods(env: Env, release: str, runner: Optional[RunFn] = None) -> None:
    current = _current_template_hash(env, release, runner=runner)
    if not current:
        return
    res = _run(
        kube_argv(env, "get", "pods", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if res.returncode != 0:
        return
    for pod in (json.loads(res.stdout or "{}") or {}).get("items") or []:
        name = str((pod.get("metadata") or {}).get("name") or "")
        if not name or _pod_template_hash(pod) == current:
            continue
        logger.info("delete stale pod %s (not hash=%s)", name, current)
        _run(
            kube_argv(env, "delete", "pod", name, "--grace-period=0", "--force"),
            runner=runner,
            check=False,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )


def _deploy_ready(dep: dict[str, Any]) -> bool:
    spec = dep.get("spec") or {}
    status = dep.get("status") or {}
    if dep.get("kind") == "List" or "replicas" not in spec:
        return False
    desired = int(spec.get("replicas") or 0)
    if desired == 0:
        return True
    updated = int(status.get("updatedReplicas") or 0)
    available = int(status.get("availableReplicas") or 0)
    gen = int((dep.get("metadata") or {}).get("generation") or 0)
    observed = int(status.get("observedGeneration") or 0)
    return observed >= gen and updated >= desired and available >= desired


def _deploy_wait_summary(dep: dict[str, Any]) -> str:
    status = dep.get("status") or {}
    spec = dep.get("spec") or {}
    desired = spec.get("replicas")
    available = status.get("availableReplicas") or 0
    updated = status.get("updatedReplicas") or 0
    reasons = []
    for cond in status.get("conditions") or []:
        if cond.get("type") == "Progressing" and cond.get("reason"):
            reasons.append(str(cond.get("reason")))
    extra = f" {','.join(reasons)}" if reasons else ""
    return f"updated={updated}/{desired} available={available}/{desired}{extra}"


def _pod_wait_summary(
    env: Env,
    release: str,
    runner: Optional[RunFn] = None,
    *,
    template_hash: str = "",
) -> str:
    _names, summary = _current_wait_pods(env, release, runner=runner, template_hash=template_hash)
    return summary


def _current_wait_pods(
    env: Env,
    release: str,
    runner: Optional[RunFn] = None,
    *,
    template_hash: str = "",
) -> tuple[Optional[list[str]], str]:
    res = _run(
        kube_argv(env, "get", "pods", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if res.returncode != 0:
        return None, (res.stderr or res.stdout or "get pods failed").strip()
    names: list[str] = []
    parts: list[str] = []
    for pod in (json.loads(res.stdout or "{}") or {}).get("items") or []:
        if template_hash and _pod_template_hash(pod) != template_hash:
            continue
        name = str((pod.get("metadata") or {}).get("name") or "pod")
        names.append(name)
        phase = str((pod.get("status") or {}).get("phase") or "")
        waiting = ""
        for cs in (pod.get("status") or {}).get("containerStatuses") or []:
            st = cs.get("state") or {}
            wait = st.get("waiting") or {}
            if wait.get("reason"):
                waiting = str(wait.get("reason"))
                if wait.get("message"):
                    waiting = f"{waiting}: {wait.get('message')}"
                break
        parts.append(f"{name} {phase} {waiting}".strip())
    return names, "; ".join(parts) or "no pods"


def _clip_log_text(text: str, *, max_chars: int = 2000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return "…\n" + text[-max_chars:]


def _pod_log_snippet(env: Env, pod: str, runner: Optional[RunFn] = None) -> str:
    argv = kube_argv(env, "logs", pod, "--tail", "40")
    res = _run(argv, runner=runner, check=False, timeout=KUBE_RUN_TIMEOUT_SEC)
    text = (res.stdout or "").strip()
    if not text:
        prev = _run(
            kube_argv(env, "logs", pod, "--previous", "--tail", "40"),
            runner=runner,
            check=False,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )
        text = (prev.stdout or prev.stderr or res.stderr or "").strip()
    elif res.returncode != 0 and not text:
        text = (res.stderr or "").strip()
    return _clip_log_text(text) if text else "(no logs yet)"


def _log_rollout_heartbeat(
    env: Env,
    *,
    name: str,
    summary: str,
    release: str,
    template_hash: str,
    runner: Optional[RunFn] = None,
) -> None:
    names, pods = _current_wait_pods(env, release, runner=runner, template_hash=template_hash)
    logger.info("waiting rollout deployment/%s %s pods=%s", name, summary, pods)
    if names is None:
        return
    for pod in names:
        snippet = _pod_log_snippet(env, pod, runner=runner)
        logger.info("pod logs %s\n%s", pod, snippet)


def _wait_agent_rollout(
    env: Env,
    release: str,
    *,
    runner: Optional[RunFn] = None,
    timeout_sec: Optional[float] = None,
) -> None:
    """Poll Available replicas. Do not use `kubectl rollout status` — it exits
    immediately on a leftover ProgressDeadlineExceeded from a prior RS."""
    wait_for = ROLLOUT_WAIT_SEC if timeout_sec is None else timeout_sec
    name = agent_deployment_name(release)
    logger.info("wait rollout deployment/%s timeout=%ss", name, int(wait_for))
    _prune_stale_agent_pods(env, release, runner=runner)
    deadline = time.monotonic() + wait_for
    last_log = 0.0
    while True:
        dep_res = _run(
            kube_argv(env, "get", "deploy", name, "-o", "json"),
            runner=runner,
            check=False,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )
        summary = "get deploy failed"
        current_hash = _current_template_hash(env, release, runner=runner)
        if dep_res.returncode == 0:
            dep = json.loads(dep_res.stdout or "{}") or {}
            if _deploy_ready(dep):
                logger.info("rollout ready deployment/%s", name)
                return
            summary = _deploy_wait_summary(dep)
        else:
            summary = (dep_res.stderr or dep_res.stdout or summary).strip()
        now = time.monotonic()
        if now >= deadline:
            names, pods = _current_wait_pods(env, release, runner=runner, template_hash=current_hash)
            snippets = []
            for pod in names or []:
                snippets.append(f"{pod}: {_pod_log_snippet(env, pod, runner=runner)}")
            extra = ("\n" + "\n".join(snippets)) if snippets else ""
            raise RuntimeError(
                f"deployment/{name} not ready within {wait_for:.0f}s ({summary}); pods: {pods}{extra}"
            )
        if last_log == 0.0 or now - last_log >= 10:
            _log_rollout_heartbeat(
                env,
                name=name,
                summary=summary,
                release=release,
                template_hash=current_hash,
                runner=runner,
            )
            last_log = now
        remaining = deadline - now
        time.sleep(0 if runner is not None else min(2.0, remaining))


def _helm_upgrade_agent(
    *,
    env: Env,
    release: str,
    overlay: dict[str, Any],
    agent_chart: Path,
    platform_chart: Path,
    platform_release: str,
    as_default: bool,
    runner: Optional[RunFn] = None,
    agent_namespace: str = "",
) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(overlay, fh)
        values_file = fh.name
    try:
        agent_env = env_for_namespace(env, agent_namespace)
        logger.info("helm upgrade --install %s namespace=%s", release, agent_env.namespace)
        _run(
            helm_argv(
                agent_env,
                "upgrade",
                "--install",
                release,
                str(agent_chart),
                "-f",
                values_file,
            ),
            runner=runner,
            capture=False,
            timeout=HELM_UPGRADE_TIMEOUT_SEC,
        )
        if as_default:
            logger.info("helm upgrade platform %s attachDefaultRoute=false", platform_release)
            plat_args = helm_argv(env, "upgrade", platform_release, str(platform_chart), "--reuse-values")
            plat_args.extend(["--set", "workload.agents.attachDefaultRoute=false"])
            _run(plat_args, runner=runner, capture=False, timeout=HELM_UPGRADE_TIMEOUT_SEC)
        _wait_agent_rollout(agent_env, release, runner=runner)
    finally:
        Path(values_file).unlink(missing_ok=True)


_TOOL_PREFIX_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_SKIP_SCAN_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


def _graph_declares_tools(root: Path) -> bool:
    """True when a graph module sets MCP_INJECT_TOOLS / MCP_INJECT_PREFIXES itself."""
    for path in root.rglob("*.py"):
        if _SKIP_SCAN_DIRS.intersection(path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "MCP_INJECT_TOOLS" in text or "MCP_INJECT_PREFIXES" in text:
            return True
    return False


def mcp_tool_scope(shape: Any, *, tools: str, all_tools: bool,
                   graph_may_declare: bool = True) -> dict[str, Any]:
    """CE-9: Mode B agents bind tools only by explicit scope. Returns agent `platform` values."""
    prefixes = [p.strip() for p in (tools or "").split(",") if p.strip()]
    if prefixes and all_tools:
        raise RuntimeError("pass --tools or --all-tools, not both")
    if not getattr(shape, "mcp_inject", False):
        return {}
    for prefix in prefixes:
        if not _TOOL_PREFIX_RE.match(prefix):
            raise RuntimeError(
                f"--tools takes MCP backend prefixes such as postgres,sandbox (got {prefix!r})"
            )
    if prefixes:
        return {"mcpInjectToolPrefixes": ",".join(prefixes)}
    if all_tools:
        return {"mcpInjectAllowAll": True}
    if graph_may_declare and _graph_declares_tools(shape.root):
        return {}
    raise RuntimeError(
        "this agent binds platform MCP tools (Mode B) but declares none. "
        "Pass --tools <prefix,...> (for example --tools postgres,sandbox) or --all-tools, "
        "or set MCP_INJECT_TOOLS in the graph module"
    )


def deploy_agent(
    *,
    root: Path,
    env: Env,
    push: bool,
    graph_id_flag: str = "",
    agent_chart: Path,
    platform_chart: Path,
    runner: Optional[RunFn] = None,
    skip_build: bool = False,
    run_timeout: str = "",
    max_tokens: int = 0,
    approval_threshold: str = "",
    image_registry: str = "",
    agent_namespace: str = "",
    tool_prefixes: str = "",
    all_tools: bool = False,
    runtime: str = "aegra",
    a2a_framework: str = "pydantic-ai",
) -> dict[str, Any]:
    if approval_threshold:
        raise RuntimeError(UPGRADE)
    runtime = (runtime or "aegra").strip().lower()
    if runtime not in RUNTIMES:
        raise RuntimeError(f"--runtime must be one of {', '.join(RUNTIMES)}")
    registry = (image_registry or os.getenv("ZELKOR_IMAGE_REGISTRY", "")).strip().rstrip("/")
    if not _is_kind(env) and not registry:
        raise RuntimeError(
            "Set ZELKOR_IMAGE_REGISTRY or pass --registry when deploying to a non-kind cluster"
        )
    if not registry:
        registry = "ghcr.io/devopssquaddev"
    shape = detect(root, graph_id_flag)
    if runtime != "aegra":
        byo = runtime == "a2a" and (root / "Dockerfile").is_file()
        if shape.kind != "deploy-first" and not byo:
            raise RuntimeError(
                f"--runtime {runtime} needs a deploy-first project (agent.json + AGENTS.md)"
                + (" or your own Dockerfile serving A2A" if runtime == "a2a" else "")
            )
        # The sidecar enforces the tool scope for every non-Aegra runtime.
        shape = dataclasses.replace(shape, mcp_inject=True)
    tool_scope = mcp_tool_scope(shape, tools=tool_prefixes, all_tools=all_tools,
                                graph_may_declare=runtime == "aegra")
    release = helm_release_name(shape.graph_id)
    logger.info("detect kind=%s graph_id=%s skip_build=%s", shape.kind, shape.graph_id, skip_build)
    info = discover_platform(env, runner=runner)
    agent_ns = (agent_namespace or "").strip() or env.namespace
    fill_langfuse_from_secret(env, info, runner=runner)
    bind_worker_to_agent_namespace(info, agent_ns, env.namespace)
    if agent_ns != env.namespace:
        copy_verify_configmaps(
            env,
            agent_ns,
            [f"{info.release}-tenant-jwks", f"{info.release}-tenant-jwt"],
            runner=runner,
        )
        copy_named_secrets(
            env,
            agent_ns,
            # AI Gateway caller key: the agent chart reads it from this Secret (gateway refuses /v1 without it).
            [str(item.get("name") or "") for item in info.image_pull_secrets]
            + [f"{info.release}-ai-gateway-consumer"],
            runner=runner,
        )
    _require_registered_extras(info, shape.mcp_servers)
    as_default = should_attach_as_default(info.agent_route_names, release)
    tag = os.getenv("ZELKOR_IMAGE_TAG") or ("dev" if not push else time.strftime("%Y%m%d%H%M%S"))
    image_repo = f"{registry}/zelkor-agent-{release}"
    image_ref = f"{image_repo}:{tag}"
    if not skip_build:
        with tempfile.TemporaryDirectory(prefix="zelkor-build-") as tmp:
            ctx = Path(tmp)
            _write_build_context(root, ctx, shape.kind, shape.graph_id,
                                 base_image=runtime_base_image(runtime, a2a_framework,
                                                               _chart_app_version(agent_chart)),
                                 runtime=runtime)
            logger.info("building %s", image_ref)
            logger.info("docker build first pull can take several minutes; layer progress follows")
            _run(["docker", "build", "--progress=plain", "-t", image_ref, str(ctx)], runner=runner)
            logger.info("built %s", image_ref)
        if push:
            logger.info("push %s", image_ref)
            _run(["docker", "push", image_ref], runner=runner)
        elif _is_kind(env):
            cluster = _kind_cluster_name(env)
            logger.info("kind load %s cluster=%s", image_ref, cluster)
            _run(["kind", "load", "docker-image", image_ref, "--name", cluster], runner=runner)
    overlay: dict[str, Any] = {
        "graphId": shape.graph_id,
        "runtime": runtime,
        # Lab override (internal labs run :dev images); released installs use the chart tag.
        **({"sidecar": {"image": {"tag": os.environ["ZELKOR_SIDECAR_TAG"]}}}
           if runtime != "aegra" and os.getenv("ZELKOR_SIDECAR_TAG") else {}),
        "image": {"repository": image_repo, "tag": tag},
        "aegraConfig": "",
        "sharedRoute": {
            "host": info.agents_host,
            "gatewayName": info.gateway_name,
            "gatewayNamespace": info.gateway_namespace,
            "asDefault": as_default,
        },
        "platform": {
            "namespace": env.namespace,
            "releaseName": info.release,  # consumer key by reference (Secret copied into agent_ns)
            "databaseUrl": info.database_url,
            "openaiBaseUrl": info.openai_base_url,
            "mcpUrl": info.mcp_url,
            "valkeyUrl": info.redis_url,
            "mcpInject": shape.mcp_inject,
            **tool_scope,
            **({"defaultLlmModel": info.default_llm_model} if info.default_llm_model else {}),
            **({"langfuseBaseUrl": info.langfuse_base_url} if info.langfuse_base_url else {}),
            **({"langfusePublicKey": info.langfuse_public_key} if info.langfuse_public_key else {}),
            **({"langfuseSecretKey": info.langfuse_secret_key} if info.langfuse_secret_key else {}),
            **({"otelTargets": info.otel_targets} if info.otel_targets else {}),
        },
        "auth": auth_values(info),
        "security": _np_values(info),
    }
    if run_timeout or max_tokens or approval_threshold:
        overlay["workload"] = {
            "intent": {
                "timeout": run_timeout,
                "maxTokens": max_tokens,
                "approval": {
                    "enabled": bool(approval_threshold),
                    "threshold": approval_threshold,
                },
            }
        }
    if info.image_pull_secrets:
        overlay["global"] = {"imagePullSecrets": info.image_pull_secrets}
    _helm_upgrade_agent(
        env=env,
        release=release,
        overlay=overlay,
        agent_chart=agent_chart,
        platform_chart=platform_chart,
        platform_release=info.release,
        as_default=as_default,
        runner=runner,
        agent_namespace=agent_ns,
    )
    return {"release": release, "graph_id": shape.graph_id, "as_default": as_default, "image": image_ref}


def _merge_values_files(paths: list[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise RuntimeError(f"{path} must be a YAML mapping")
        merged = fill_empty(data, merged)
    return merged


def deploy_from_values(
    *,
    values_path: Path,
    env: Env,
    agent_chart: Path,
    platform_chart: Path,
    runner: Optional[RunFn] = None,
    approval_threshold: str = "",
    extra_values: Optional[list[Path]] = None,
    image_registry: str = "",
    skip_build: Optional[bool] = None,
    agent_namespace: str = "",
) -> dict[str, Any]:
    if approval_threshold:
        raise RuntimeError(UPGRADE)
    paths = [values_path, *(extra_values or [])]
    file_values = _merge_values_files(paths)
    if not isinstance(file_values, dict):
        raise RuntimeError(f"{values_path} must be a YAML mapping")
    graph_id = str(file_values.get("graphId") or "").strip()
    if not graph_id:
        raise RuntimeError("values file must set graphId")
    image = dict(file_values.get("image") or {})
    repo = str(image.get("repository") or "").strip()
    if not repo:
        raise RuntimeError("values file must set image.repository")
    digest = str(image.get("digest") or "").strip()
    tag = str(image.get("tag") or "").strip() or _chart_app_version(agent_chart)
    image["tag"] = tag
    file_values = dict(file_values)
    file_values["image"] = image
    logger.info("deploy -f %s graph_id=%s image=%s:%s", values_path, graph_id, repo, tag)
    dockerfile = values_path.parent / "Dockerfile"
    skip = _skip_build() if skip_build is None else skip_build
    if dockerfile.is_file() and not skip and not digest:
        if not _is_kind(env):
            registry = (image_registry or os.getenv("ZELKOR_IMAGE_REGISTRY", "")).strip().rstrip("/")
            if not registry:
                raise RuntimeError(
                    "Set ZELKOR_IMAGE_REGISTRY or pass --registry when deploying to a non-kind cluster"
                )
        image_ref = f"{repo}:{tag}"
        _build_catalog_image(
            env=env,
            image_ref=image_ref,
            dockerfile=dockerfile,
            context=_chart_repo_root(agent_chart),
            tag=tag,
            runner=runner,
            push=not _is_kind(env),
        )
        if _is_kind(env):
            image["pullPolicy"] = "Never"
            file_values = dict(file_values)
            file_values["image"] = image
            logger.info("image.pullPolicy=Never after kind load")
    info = discover_platform(env, runner=runner)
    agent_ns = (agent_namespace or "").strip() or env.namespace
    fill_langfuse_from_secret(env, info, runner=runner)
    bind_worker_to_agent_namespace(info, agent_ns, env.namespace)
    if agent_ns != env.namespace:
        copy_verify_configmaps(
            env,
            agent_ns,
            [f"{info.release}-tenant-jwks", f"{info.release}-tenant-jwt"],
            runner=runner,
        )
        copy_named_secrets(
            env,
            agent_ns,
            # AI Gateway caller key: the agent chart reads it from this Secret (gateway refuses /v1 without it).
            [str(item.get("name") or "") for item in info.image_pull_secrets]
            + [f"{info.release}-ai-gateway-consumer"],
            runner=runner,
        )
    _require_registered_extras(info, mcp_servers_from_tools(values_path.parent))
    overlay = merge_catalog_values(
        file_values, discovered_worker_values(info, platform_namespace=env.namespace)
    )
    as_default = bool(((overlay.get("sharedRoute") or {}).get("asDefault")))
    release = helm_release_name(graph_id)
    _helm_upgrade_agent(
        env=env,
        release=release,
        overlay=overlay,
        agent_chart=agent_chart,
        platform_chart=platform_chart,
        platform_release=info.release,
        as_default=as_default,
        runner=runner,
        agent_namespace=agent_ns,
    )
    if digest:
        ref = f"{repo}@{digest}"
    else:
        ref = f"{repo}:{tag}"
    return {"release": release, "graph_id": graph_id, "as_default": as_default, "image": ref}


def cmd_undeploy(
    root: Path,
    env: Env,
    *,
    graph_id_flag: str = "",
    platform_chart: Path,
    runner: Optional[RunFn] = None,
    agent_namespace: str = "",
) -> int:
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    agent_ns = (agent_namespace or "").strip() or find_agent_release_namespace(env, release, runner=runner)
    agent_env = env_for_namespace(env, agent_ns)
    logger.info("undeploy release=%s namespace=%s", release, agent_env.namespace)
    info = discover_platform(env, runner=runner)
    got = _run(
        helm_argv(agent_env, "get", "values", release, "-o", "yaml"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if got.returncode != 0:
        print(f"agent release {release} not found", file=sys.stderr)
        return 1
    values = yaml.safe_load(got.stdout or "") or {}
    as_default = bool(((values.get("sharedRoute") or {}).get("asDefault")))
    logger.info("helm uninstall %s", release)
    _run(helm_argv(agent_env, "uninstall", release), runner=runner, capture=False, timeout=KUBE_RUN_TIMEOUT_SEC)
    if as_default:
        _run(
            helm_argv(
                env,
                "upgrade",
                info.release,
                str(platform_chart),
                "--reuse-values",
                "--set",
                "aegra.attachDefaultRoute=true",
            ),
            runner=runner,
            capture=False,
            timeout=HELM_UPGRADE_TIMEOUT_SEC,
        )
    print(json.dumps({"release": release, "uninstalled": True, "restored_default": as_default}))
    return 0


def cmd_logs(
    root: Path,
    env: Env,
    *,
    graph_id_flag: str = "",
    follow: bool = True,
    tail: str = "",
    runner: Optional[RunFn] = None,
    agent_namespace: str = "",
) -> int:
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    agent_ns = (agent_namespace or "").strip() or find_agent_release_namespace(env, release, runner=runner)
    agent_env = env_for_namespace(env, agent_ns)
    deploy = f"deployment/{agent_deployment_name(release)}"
    argv = kube_argv(agent_env, "logs", deploy)
    if follow:
        argv.append("-f")
    if tail:
        argv.extend(["--tail", str(tail)])
    logger.info("logs deploy=%s", deploy)
    res = _run(argv, runner=runner, capture=not follow, check=True)
    if not follow and res.stdout:
        sys.stdout.write(res.stdout if res.stdout.endswith("\n") else res.stdout + "\n")
    return 0


def cmd_init(root: Path) -> int:
    logger.info("init directory=%s", root)
    agent = root / "agent.json"
    md = root / "AGENTS.md"
    if agent.exists() or md.exists():
        print("agent.json or AGENTS.md already exists", file=sys.stderr)
        return 1
    agent.write_text(json.dumps({"name": "agent", "description": ""}, indent=2) + "\n", encoding="utf-8")
    md.write_text("# Agent\n\nYou are a helpful assistant running on Zelkor.\n", encoding="utf-8")
    print(f"wrote {agent} and {md}")
    return 0


def cmd_env(args: argparse.Namespace, store_path: Path | None) -> int:
    logger.info("env %s", args.env_cmd)
    if args.env_cmd == "add":
        add_env(
            Env(name=args.name, kube_context=args.kube_context, namespace=args.namespace, kubeconfig=args.kubeconfig or ""),
            store_path=store_path,
        )
        print(f"env {args.name} added")
        return 0
    if args.env_cmd == "list":
        data = load_store(store_path)
        current = data.get("current") or ""
        for env in list_envs(store_path):
            mark = "*" if env.name == current else " "
            print(f"{mark} {env.name}  {env.kube_context}  {env.namespace}")
        return 0
    if args.env_cmd == "use":
        data = load_store(store_path)
        envs = (data.get("envs") or {})
        if args.name not in envs:
            print(f"unknown env {args.name}", file=sys.stderr)
            return 1
        data["current"] = args.name
        from zelkor.envfile import save_store

        save_store(data, store_path)
        print(f"using {args.name}")
        return 0
    if args.env_cmd == "remove":
        remove_env(args.name, store_path=store_path)
        print(f"removed {args.name}")
        return 0
    return 1


def cmd_status(env: Env, runner: Optional[RunFn] = None, agent_namespace: str = "") -> int:
    logger.info("status env=%s namespace=%s", env.name, env.namespace)
    listed = _run(helm_argv(env, "list", "-A", "-o", "json"), runner=runner, timeout=KUBE_RUN_TIMEOUT_SEC)
    print("Helm releases:")
    for rel in json.loads(listed.stdout or "[]"):
        chart = str(rel.get("chart") or "")
        ns = str(rel.get("namespace") or "")
        if agent_namespace and ns not in (env.namespace, agent_namespace):
            continue
        if "zelkor-agent" in chart or str(rel.get("name") or "").endswith("zelkor-agent"):
            print(f"  {rel.get('name')}  {ns}  {chart}  {rel.get('status')}")
        if chart.startswith("zelkor-platform"):
            print(f"  {rel.get('name')}  {ns}  {chart}  {rel.get('status')}")
    routes = _run(
        ["kubectl", "--request-timeout", KUBE_REQUEST_TIMEOUT, "--context", env.kube_context, "get", "httproute", "-A", "-o", "json"]
        + (["--kubeconfig", env.kubeconfig] if env.kubeconfig else []),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    print("HTTPRoutes:")
    if routes.returncode == 0:
        for route in (json.loads(routes.stdout or "{}") or {}).get("items") or []:
            hosts = (route.get("spec") or {}).get("hostnames") or []
            name = (route.get("metadata") or {}).get("name")
            rns = (route.get("metadata") or {}).get("namespace")
            print(f"  {rns}/{name}  {', '.join(hosts)}")
    return 0


def cmd_doctor(env: Env, runner: Optional[RunFn] = None) -> int:
    logger.info("doctor env=%s namespace=%s", env.name, env.namespace)
    info = discover_platform(env, runner=runner)
    checks = [
        ("DATABASE_URL", bool(info.database_url)),
        ("OPENAI_BASE_URL", bool(info.openai_base_url)),
        ("MCP_URL", bool(info.mcp_url)),
        ("Agents host", bool(info.agents_host)),
        ("CE license", True),
    ]
    failed = 0
    for label, ok in checks:
        status = "ok" if ok else "missing"
        if label == "CE license":
            status = "n/a"
        print(f"{label}: {status}")
        if not ok:
            failed += 1
    return 1 if failed else 0


def cmd_version(env: Optional[Env], runner: Optional[RunFn] = None) -> int:
    print(f"zelkor {__version__}")
    if env is None:
        return 0
    try:
        info = discover_platform(env, runner=runner)
        print(f"platform chart {info.chart_version or info.release}")
    except Exception as exc:
        print(f"platform: {exc}", file=sys.stderr)
    return 0


def _chunk_field(chunk: object, key: str):
    if isinstance(chunk, dict):
        return chunk.get(key)
    return getattr(chunk, key, None)


_PROGRESS_START = {
    "on_chain_start": "node",
    "on_chat_model_start": "model",
    "on_llm_start": "model",
    "on_tool_start": "tool",
}
_SKIP_PROGRESS = frozenset(
    {
        "LangGraph",
        "RunnableSequence",
        "RunnableLambda",
        "RunnableParallel",
        "RunnableEach",
        "ChannelWrite",
        "ChannelRead",
        "Pregel",
        "__start__",
        "__end__",
    }
)


def format_run_progress(chunk: object) -> str | None:
    """One stderr line for node/model/tool start. No event payloads."""
    event = _chunk_field(chunk, "event")
    data = _chunk_field(chunk, "data")
    if not isinstance(data, dict):
        data = {}
    if event == "custom":
        kind = str(data.get("kind") or "")
        name = str(data.get("name") or "").strip()
        if not kind or not name:
            return None
        phase = str(data.get("phase") or "start")
        if phase == "wait":
            return f"agent: {kind} {name} wait {int(data.get('elapsed_s') or 0)}s"
        return f"agent: {kind} {name}"
    lc_event = event if event in _PROGRESS_START else data.get("event")
    name = str(data.get("name") or _chunk_field(chunk, "name") or "").strip()
    if lc_event not in _PROGRESS_START:
        return None
    if not name or name in _SKIP_PROGRESS or name.startswith("Runnable") or name.startswith("Channel"):
        return None
    return f"agent: {_PROGRESS_START[lc_event]} {name}"


def cmd_run(
    root: Path,
    env: Env,
    *,
    message: str,
    url: str,
    auth: str,
    graph_id_flag: str = "",
    runner: Optional[RunFn] = None,
) -> int:
    shape = detect(root, graph_id_flag)
    logger.info("run graph_id=%s", shape.graph_id)
    info = discover_platform(env, runner=runner)
    base = url or os.getenv("ZELKOR_AGENTS_URL") or os.getenv("ZELKOR_AEGRA_URL") or (
        f"http://{info.agents_host}" if info.agents_host else ""
    )
    if not base:
        print("no agents URL; pass --url or set ZELKOR_AGENTS_URL", file=sys.stderr)
        return 1
    token = auth or os.getenv("ZELKOR_AUTH_TOKEN") or os.getenv("AEGRA_AUTH_TOKEN") or ""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    from urllib.parse import urlparse

    parsed = urlparse(base)
    if info.agents_host and parsed.hostname != info.agents_host:
        headers["Host"] = info.agents_host
    headers["X-Graph-ID"] = shape.graph_id
    try:
        from langgraph_sdk import get_sync_client

        logger.info("run stream url=%s graph_id=%s", base, shape.graph_id)
        client = get_sync_client(url=base, headers=headers)
        thread = client.threads.create()
        errored = False
        for chunk in client.runs.stream(
            thread["thread_id"],
            shape.graph_id,
            input={"messages": [{"role": "human", "content": message}]},
            stream_mode=["events", "updates"],
        ):
            line = format_run_progress(chunk)
            if line:
                print(line, file=sys.stderr)
            stream_event = _chunk_field(chunk, "event")
            if stream_event in ("updates", "error"):
                print(chunk)
            if stream_event == "error" or (isinstance(chunk, dict) and chunk.get("event") == "error"):
                errored = True
        if errored:
            return 1
    except ImportError:
        print("langgraph-sdk is required for zelkor run", file=sys.stderr)
        return 1
    return 0


def _store_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "store", "") or os.getenv("ZELKOR_ENV_FILE", "")
    return Path(raw) if raw else None


def _env_from_args(args: argparse.Namespace, *, prefer_local: bool = False) -> Env:
    return resolve_env(
        name=getattr(args, "env", "") or "",
        prefer_local=prefer_local,
        store_path=_store_path(args),
    )


def _boot_logging() -> None:
    try:
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    common = Path(__file__).resolve().parents[3] / "images" / "common"
    if (common / "zelkor_logging.py").is_file() and str(common) not in sys.path:
        sys.path.insert(0, str(common))
    try:
        from zelkor_logging import configure_logging
    except ImportError:
        logging.basicConfig(
            level=getattr(logging, os.getenv("ZELKOR_LOG_LEVEL", "INFO").upper(), logging.INFO)
        )
        return
    if not os.getenv("ZELKOR_LOG_FORMAT"):
        os.environ["ZELKOR_LOG_FORMAT"] = "text" if sys.stderr.isatty() else "json"
    configure_logging("zelkor-cli", stream=sys.stderr)


def main(argv: Optional[list[str]] = None, runner: Optional[RunFn] = None) -> int:
    _boot_logging()
    parser = argparse.ArgumentParser(prog="zelkor", description="One packager for every Zelkor agent")
    parser.add_argument("--env", default="", help="named env (kubecontext + namespace)")
    parser.add_argument("--store", default="", help=argparse.SUPPRESS)
    parser.add_argument("--chart", default="", help="path to charts/zelkor-agent")
    parser.add_argument("--platform-chart", default="", help="path to charts/zelkor-platform")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="scaffold deploy-first agent.json + AGENTS.md")
    p_init.add_argument("directory", nargs="?", default=".")

    sub.add_parser("dev", help="build and helm upgrade without registry push")
    sub.add_parser("deploy", help="build, push, helm upgrade")
    p_run = sub.add_parser("run", help="Agent Protocol create-run + stream")
    p_run.add_argument("directory", nargs="?", default=".")
    p_run.add_argument("--input", default="hello", dest="message")
    p_run.add_argument("--url", default="")
    p_run.add_argument("--auth", default="")
    p_run.add_argument("--graph-id", default="")
    p_undeploy = sub.add_parser("undeploy", help="helm uninstall the agent release")
    p_undeploy.add_argument("--graph-id", default="")
    p_undeploy.add_argument("--namespace", default="", help="agent release namespace (default: discover)")
    p_undeploy.add_argument("directory", nargs="?", default=".")
    p_logs = sub.add_parser("logs", help="follow the agent Deployment")
    p_logs.add_argument("--graph-id", default="")
    p_logs.add_argument("--namespace", default="", help="agent release namespace (default: discover)")
    p_logs.add_argument("--tail", default="")
    p_logs.add_argument("--follow", dest="follow", action="store_true", default=True)
    p_logs.add_argument("--no-follow", dest="follow", action="store_false")
    p_logs.add_argument("directory", nargs="?", default=".")
    p_status = sub.add_parser("status", help="agent Helm releases and HTTPRoutes")
    p_status.add_argument("--namespace", default="", help="filter agent releases to this namespace")
    sub.add_parser("doctor", help="check discovered platform endpoints")
    sub.add_parser("version", help="CLI and platform chart version")

    p_token = sub.add_parser("token", help="mint RS256 tokens from cluster signing key")
    token_sub = p_token.add_subparsers(dest="token_cmd", required=True)
    p_mint = token_sub.add_parser("mint", help="mint a tenant JWT")
    p_mint.add_argument("--release", required=True)
    p_mint.add_argument("--tenant", required=True)
    p_mint.add_argument("--namespace", default="")
    p_mint.add_argument("--kubeconfig", default="")
    p_mint.add_argument("--context", default="")
    p_mint.add_argument("--issuer", default="")
    p_mint.add_argument("--audience", default="")
    p_mint.add_argument("--ttl", default="")
    p_mint.add_argument("--out", default="")
    p_jwks = token_sub.add_parser("jwks", help="write public JWKS to a file")
    p_jwks.add_argument("--release", required=True)
    p_jwks.add_argument("--out", required=True)
    p_jwks.add_argument("--env-file", default="")
    p_jwks.add_argument("--namespace", default="")
    p_jwks.add_argument("--kubeconfig", default="")
    p_jwks.add_argument("--context", default="")

    p_env = sub.add_parser("env", help="named kubecontext targets")
    env_sub = p_env.add_subparsers(dest="env_cmd", required=True)
    p_add = env_sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("--kube-context", required=True)
    p_add.add_argument("--namespace", required=True)
    p_add.add_argument("--kubeconfig", default="")
    env_sub.add_parser("list")
    p_use = env_sub.add_parser("use")
    p_use.add_argument("name")
    p_rm = env_sub.add_parser("remove")
    p_rm.add_argument("name")

    for paid in sorted(PAID):
        paid_p = sub.add_parser(paid, help="Pro/Enterprise")
        paid_p.add_argument("rest", nargs=argparse.REMAINDER)

    for p in (sub.choices["dev"], sub.choices["deploy"]):
        p.add_argument("--graph-id", default="")
        p.add_argument("--namespace", default="", help="agent Helm namespace (env stays the platform ns)")
        p.add_argument("--timeout", default="", help="workload.intent.timeout (Envoy/Aegra)")
        p.add_argument("--max-tokens", type=int, default=0, help="workload.intent.maxTokens")
        p.add_argument("--approval-threshold", default="", help="workload.intent.approval.threshold (Pro)")
        p.add_argument("--registry", default="", help="container registry for agent image (required off kind)")
        p.add_argument(
            "--tools",
            default="",
            help="MCP backend prefixes the agent may bind (Mode B), e.g. postgres,sandbox",
        )
        p.add_argument("--runtime", default="aegra", choices=["aegra", "a2a", "opencode"],
                       help="agent runtime: aegra (LangGraph / Deep Agents), a2a (any A2A server), opencode")
        p.add_argument("--a2a-framework", default="pydantic-ai", choices=["pydantic-ai", "crewai"],
                       help="base image for a deploy-first --runtime a2a project")
        p.add_argument(
            "--all-tools",
            action="store_true",
            help="bind every tool the MCP gateway lists for the tenant (natives and extras)",
        )
        p.add_argument("directory", nargs="?", default=".")
    sub.choices["deploy"].add_argument(
        "-f",
        "--values",
        action="append",
        default=[],
        dest="values_files",
        help="zelkor-agent values overlay (repeatable; builds sibling Dockerfile unless ZELKOR_SKIP_BUILD=1)",
    )

    args = parser.parse_args(argv)
    logger.info("cli cmd=%s", args.cmd)
    if args.cmd in PAID:
        print(UPGRADE, file=sys.stderr)
        return 2
    if args.cmd == "token":
        if args.token_cmd == "mint":
            return cmd_token_mint(args)
        if args.token_cmd == "jwks":
            return cmd_token_jwks(args)
        return 2
    if args.cmd == "init":
        return cmd_init(Path(args.directory))
    if args.cmd == "env":
        return cmd_env(args, _store_path(args))
    if args.cmd == "version":
        try:
            env = _env_from_args(args)
        except KeyError:
            env = None
        return cmd_version(env, runner=runner)

    try:
        env = _env_from_args(args, prefer_local=args.cmd == "dev")
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    logger.info("using env=%s context=%s namespace=%s", env.name, env.kube_context, env.namespace)

    if args.cmd == "status":
        return cmd_status(env, runner=runner, agent_namespace=getattr(args, "namespace", "") or "")
    if args.cmd == "doctor":
        return cmd_doctor(env, runner=runner)
    if args.cmd == "undeploy":
        try:
            platform_chart = find_chart(
                Path(args.directory).resolve(),
                "zelkor-platform",
                args.platform_chart,
                "ZELKOR_PLATFORM_CHART",
            )
            return cmd_undeploy(
                Path(args.directory).resolve(),
                env,
                graph_id_flag=args.graph_id,
                platform_chart=platform_chart,
                runner=runner,
                agent_namespace=getattr(args, "namespace", "") or "",
            )
        except (FileNotFoundError, DetectError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.cmd == "logs":
        try:
            return cmd_logs(
                Path(args.directory).resolve(),
                env,
                graph_id_flag=args.graph_id,
                follow=args.follow,
                tail=args.tail,
                runner=runner,
                agent_namespace=getattr(args, "namespace", "") or "",
            )
        except DetectError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.cmd == "run":
        return cmd_run(
            Path(args.directory),
            env,
            message=args.message,
            url=args.url,
            auth=args.auth,
            graph_id_flag=args.graph_id,
            runner=runner,
        )

    root = Path(args.directory).resolve()
    try:
        agent_chart = find_chart(root, "zelkor-agent", args.chart, "ZELKOR_AGENT_CHART")
        platform_chart = find_chart(root, "zelkor-platform", args.platform_chart, "ZELKOR_PLATFORM_CHART")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        if args.cmd == "deploy" and getattr(args, "values_files", None):
            files = [Path(p).resolve() for p in args.values_files]
            result = deploy_from_values(
                values_path=files[0],
                extra_values=files[1:],
                env=env,
                agent_chart=agent_chart,
                platform_chart=platform_chart,
                runner=runner,
                approval_threshold=getattr(args, "approval_threshold", "") or "",
                image_registry=getattr(args, "registry", "") or "",
                agent_namespace=getattr(args, "namespace", "") or "",
            )
        else:
            result = deploy_agent(
                root=root,
                env=env,
                push=args.cmd == "deploy",
                graph_id_flag=args.graph_id,
                agent_chart=agent_chart,
                platform_chart=platform_chart,
                runner=runner,
                skip_build=os.getenv("ZELKOR_SKIP_BUILD", "").strip().lower() in {"1", "true", "yes"},
                run_timeout=getattr(args, "timeout", "") or "",
                max_tokens=int(getattr(args, "max_tokens", 0) or 0),
                approval_threshold=getattr(args, "approval_threshold", "") or "",
                image_registry=getattr(args, "registry", "") or "",
                agent_namespace=getattr(args, "namespace", "") or "",
                tool_prefixes=getattr(args, "tools", "") or "",
                all_tools=bool(getattr(args, "all_tools", False)),
                runtime=getattr(args, "runtime", "aegra") or "aegra",
                a2a_framework=getattr(args, "a2a_framework", "pydantic-ai") or "pydantic-ai",
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except DetectError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
