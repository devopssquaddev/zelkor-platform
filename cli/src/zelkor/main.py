"""zelkor CLI — one packager for every agent."""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from zelkor import __version__
from zelkor.detect import (
    DetectError,
    agent_deployment_name,
    customer_dockerfile,
    deploy_first_langgraph,
    detect,
    helm_release_name,
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
    consumer_key: str = ""
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


def _run(
    argv: list[str],
    *,
    runner: Optional[RunFn] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    logger.debug("run %s", " ".join(argv))
    fn = runner or subprocess.run
    kw: dict[str, Any] = {"text": True, "check": False}
    if timeout is not None:
        kw["timeout"] = timeout
    if capture:
        kw["capture_output"] = True
    else:
        kw["stdout"] = sys.stderr
        kw["stderr"] = sys.stderr
    try:
        res = fn(argv, **kw)
    except TypeError:
        res = fn(argv, capture_output=capture, text=True, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(argv)} timed out after {timeout}s") from exc
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


def discover_platform(env: Env, runner: Optional[RunFn] = None) -> PlatformInfo:
    logger.info(
        "discover platform env=%s context=%s namespace=%s",
        env.name,
        env.kube_context,
        env.namespace,
    )
    info = PlatformInfo()
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
    values_raw = _run(
        helm_argv(env, "get", "values", info.release, "-o", "yaml"),
        runner=runner,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    values = yaml.safe_load(values_raw.stdout or "") or {}
    hosts = ((values.get("gateway") or {}).get("hosts") or {})
    info.agents_host = str(hosts.get("agents") or hosts.get("aegra") or "")
    info.image_pull_secrets = list((values.get("global") or {}).get("imagePullSecrets") or [])
    info.gateway_namespace = env.namespace
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
        info.consumer_key = env_map.get("OPENAI_API_KEY", "")
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


def _write_build_context(src: Path, dest: Path, shape_kind: str, graph_id: str) -> None:
    ignore = {".git", ".zelkor", "__pycache__", ".venv", ".pytest_cache"}
    for item in src.iterdir():
        if item.name in ignore:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*ignore, "*.pyc"))
        else:
            shutil.copy2(item, target)
    (dest / "Dockerfile").write_text(
        customer_dockerfile(os.getenv("ZELKOR_DEEP_IMAGE", "ghcr.io/devopssquaddev/zelkor-aegra-deep:1.2.5")),
        encoding="utf-8",
    )
    if shape_kind == "deploy-first":
        (dest / "langgraph.json").write_text(
            json.dumps(deploy_first_langgraph(graph_id), indent=2),
            encoding="utf-8",
        )


def _is_kind(env: Env) -> bool:
    return env.kube_context.startswith("kind-") or os.getenv("KIND_CLUSTER", "") != ""


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


def discovered_worker_values(info: PlatformInfo) -> dict[str, Any]:
    platform: dict[str, Any] = {
        "releaseName": info.release,
        "databaseUrl": info.database_url,
        "openaiBaseUrl": info.openai_base_url,
        "mcpUrl": info.mcp_url,
        "consumerKey": info.consumer_key,
        "valkeyUrl": info.redis_url,
        "mcpInject": True,
    }
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


def _pod_wait_summary(env: Env, release: str, runner: Optional[RunFn] = None) -> str:
    res = _run(
        kube_argv(env, "get", "pods", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if res.returncode != 0:
        return (res.stderr or res.stdout or "get pods failed").strip()
    parts: list[str] = []
    for pod in (json.loads(res.stdout or "{}") or {}).get("items") or []:
        name = str((pod.get("metadata") or {}).get("name") or "pod")
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
    return "; ".join(parts) or "no pods"


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
            pods = _pod_wait_summary(env, release, runner=runner)
            raise RuntimeError(
                f"deployment/{name} not ready within {wait_for:.0f}s ({summary}); pods: {pods}"
            )
        if last_log == 0.0 or now - last_log >= 10:
            pods = _pod_wait_summary(env, release, runner=runner)
            logger.info("waiting rollout deployment/%s %s pods=%s", name, summary, pods)
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
) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(overlay, fh)
        values_file = fh.name
    try:
        logger.info("helm upgrade --install %s", release)
        _run(
            helm_argv(
                env,
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
        _wait_agent_rollout(env, release, runner=runner)
    finally:
        Path(values_file).unlink(missing_ok=True)


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
) -> dict[str, Any]:
    if approval_threshold:
        raise RuntimeError(UPGRADE)
    registry = (image_registry or os.getenv("ZELKOR_IMAGE_REGISTRY", "")).strip().rstrip("/")
    if not _is_kind(env) and not registry:
        raise RuntimeError(
            "Set ZELKOR_IMAGE_REGISTRY or pass --registry when deploying to a non-kind cluster"
        )
    if not registry:
        registry = "ghcr.io/devopssquaddev"
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    info = discover_platform(env, runner=runner)
    platform_values: dict[str, Any] = {}
    if shape.mcp_servers:
        values_raw = _run(
            helm_argv(env, "get", "values", info.release, "-o", "yaml"),
            runner=runner,
            timeout=KUBE_RUN_TIMEOUT_SEC,
        )
        platform_values = yaml.safe_load(values_raw.stdout or "") or {}
        missing = missing_extra_registrations(shape.mcp_servers, platform_values)
        if missing:
            raise RuntimeError(format_missing_extras_error(missing))
    as_default = should_attach_as_default(info.agent_route_names, release)
    tag = os.getenv("ZELKOR_IMAGE_TAG") or ("dev" if not push else time.strftime("%Y%m%d%H%M%S"))
    image_repo = f"{registry}/zelkor-agent-{release}"
    image_ref = f"{image_repo}:{tag}"
    if not skip_build:
        with tempfile.TemporaryDirectory(prefix="zelkor-build-") as tmp:
            ctx = Path(tmp)
            _write_build_context(root, ctx, shape.kind, shape.graph_id)
            _run(["docker", "build", "-t", image_ref, str(ctx)], runner=runner)
        if push:
            _run(["docker", "push", image_ref], runner=runner)
        elif _is_kind(env):
            cluster = os.getenv("KIND_CLUSTER") or env.kube_context.removeprefix("kind-")
            _run(["kind", "load", "docker-image", image_ref, "--name", cluster], runner=runner)
    overlay: dict[str, Any] = {
        "graphId": shape.graph_id,
        "image": {"repository": image_repo, "tag": tag},
        "aegraConfig": "",
        "sharedRoute": {
            "host": info.agents_host,
            "gatewayName": info.gateway_name,
            "gatewayNamespace": info.gateway_namespace,
            "asDefault": as_default,
        },
        "platform": {
            "databaseUrl": info.database_url,
            "openaiBaseUrl": info.openai_base_url,
            "mcpUrl": info.mcp_url,
            "consumerKey": info.consumer_key,
            "valkeyUrl": info.redis_url,
            "mcpInject": shape.mcp_inject,
            **({"defaultLlmModel": info.default_llm_model} if info.default_llm_model else {}),
            **({"langfuseBaseUrl": info.langfuse_base_url} if info.langfuse_base_url else {}),
            **({"langfusePublicKey": info.langfuse_public_key} if info.langfuse_public_key else {}),
            **({"langfuseSecretKey": info.langfuse_secret_key} if info.langfuse_secret_key else {}),
            **({"otelTargets": info.otel_targets} if info.otel_targets else {}),
        },
        "auth": auth_values(info),
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


def _apply_image_tag_override(file_values: dict[str, Any]) -> dict[str, Any]:
    tag = os.getenv("ZELKOR_IMAGE_TAG", "").strip()
    if not tag:
        return file_values
    image = dict(file_values.get("image") or {})
    image["tag"] = tag
    out = dict(file_values)
    out["image"] = image
    logger.info("image.tag from ZELKOR_IMAGE_TAG=%s", tag)
    return out


def deploy_from_values(
    *,
    values_path: Path,
    env: Env,
    agent_chart: Path,
    platform_chart: Path,
    runner: Optional[RunFn] = None,
    approval_threshold: str = "",
    extra_values: Optional[list[Path]] = None,
) -> dict[str, Any]:
    if approval_threshold:
        raise RuntimeError(UPGRADE)
    paths = [values_path, *(extra_values or [])]
    file_values = _apply_image_tag_override(_merge_values_files(paths))
    if not isinstance(file_values, dict):
        raise RuntimeError(f"{values_path} must be a YAML mapping")
    graph_id = str(file_values.get("graphId") or "").strip()
    if not graph_id:
        raise RuntimeError("values file must set graphId")
    image = file_values.get("image") or {}
    if not str((image or {}).get("repository") or "").strip():
        raise RuntimeError("values file must set image.repository")
    logger.info("deploy -f %s graph_id=%s image=%s:%s", values_path, graph_id, image.get("repository"), image.get("tag"))
    info = discover_platform(env, runner=runner)
    overlay = merge_catalog_values(file_values, discovered_worker_values(info))
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
    )
    image_ref = str(image.get("repository") or "")
    tag = str(image.get("tag") or "")
    digest = str(image.get("digest") or "")
    if digest:
        ref = f"{image_ref}@{digest}"
    elif tag:
        ref = f"{image_ref}:{tag}"
    else:
        ref = image_ref
    return {"release": release, "graph_id": graph_id, "as_default": as_default, "image": ref}


def cmd_undeploy(
    root: Path,
    env: Env,
    *,
    graph_id_flag: str = "",
    platform_chart: Path,
    runner: Optional[RunFn] = None,
) -> int:
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    info = discover_platform(env, runner=runner)
    got = _run(
        helm_argv(env, "get", "values", release, "-o", "yaml"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    if got.returncode != 0:
        print(f"agent release {release} not found", file=sys.stderr)
        return 1
    values = yaml.safe_load(got.stdout or "") or {}
    as_default = bool(((values.get("sharedRoute") or {}).get("asDefault")))
    _run(helm_argv(env, "uninstall", release), runner=runner, capture=False, timeout=KUBE_RUN_TIMEOUT_SEC)
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
) -> int:
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    deploy = f"deployment/{agent_deployment_name(release)}"
    argv = kube_argv(env, "logs", deploy)
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


def cmd_status(env: Env, runner: Optional[RunFn] = None) -> int:
    listed = _run(helm_argv(env, "list", "-o", "json"), runner=runner, timeout=KUBE_RUN_TIMEOUT_SEC)
    print("Helm releases:")
    for rel in json.loads(listed.stdout or "[]"):
        chart = str(rel.get("chart") or "")
        if "zelkor-agent" in chart or str(rel.get("name") or "").endswith("zelkor-agent"):
            print(f"  {rel.get('name')}  {chart}  {rel.get('status')}")
        if chart.startswith("zelkor-platform"):
            print(f"  {rel.get('name')}  {chart}  {rel.get('status')}")
    routes = _run(
        kube_argv(env, "get", "httproute", "-o", "json"),
        runner=runner,
        check=False,
        timeout=KUBE_RUN_TIMEOUT_SEC,
    )
    print("HTTPRoutes:")
    if routes.returncode == 0:
        for route in (json.loads(routes.stdout or "{}") or {}).get("items") or []:
            hosts = (route.get("spec") or {}).get("hostnames") or []
            name = (route.get("metadata") or {}).get("name")
            print(f"  {name}  {', '.join(hosts)}")
    return 0


def cmd_doctor(env: Env, runner: Optional[RunFn] = None) -> int:
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
    as_default = should_attach_as_default(info.agent_route_names, helm_release_name(shape.graph_id))
    if not as_default:
        headers["X-Graph-ID"] = shape.graph_id
    try:
        from langgraph_sdk import get_sync_client

        client = get_sync_client(url=base, headers=headers)
        thread = client.threads.create()
        errored = False
        for chunk in client.runs.stream(
            thread["thread_id"],
            shape.graph_id,
            input={"messages": [{"role": "human", "content": message}]},
            stream_mode="updates",
        ):
            print(chunk)
            event = getattr(chunk, "event", None)
            if event == "error" or (isinstance(chunk, dict) and chunk.get("event") == "error"):
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
    p_undeploy.add_argument("directory", nargs="?", default=".")
    p_logs = sub.add_parser("logs", help="follow the agent Deployment")
    p_logs.add_argument("--graph-id", default="")
    p_logs.add_argument("--tail", default="")
    p_logs.add_argument("--follow", dest="follow", action="store_true", default=True)
    p_logs.add_argument("--no-follow", dest="follow", action="store_false")
    p_logs.add_argument("directory", nargs="?", default=".")
    sub.add_parser("status", help="agent Helm releases and HTTPRoutes")
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
        p.add_argument("--timeout", default="", help="workload.intent.timeout (Envoy/Aegra)")
        p.add_argument("--max-tokens", type=int, default=0, help="workload.intent.maxTokens")
        p.add_argument("--approval-threshold", default="", help="workload.intent.approval.threshold (Pro)")
        p.add_argument("--registry", default="", help="container registry for agent image (required off kind)")
        p.add_argument("directory", nargs="?", default=".")
    sub.choices["deploy"].add_argument(
        "-f",
        "--values",
        action="append",
        default=[],
        dest="values_files",
        help="zelkor-agent values overlay (repeatable; skip docker build)",
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

    if args.cmd == "status":
        return cmd_status(env, runner=runner)
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
