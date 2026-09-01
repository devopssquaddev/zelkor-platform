"""zelkor CLI — one packager for every agent."""
from __future__ import annotations

import argparse
import json
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
    customer_dockerfile,
    deploy_first_langgraph,
    detect,
    helm_release_name,
    should_attach_as_default,
)
from zelkor.envfile import Env, add_env, list_envs, load_store, remove_env, resolve_env

PAID = frozenset({"login", "license", "whoami", "team", "budget", "audit"})
NOT_YET = frozenset({"undeploy", "logs"})
UPGRADE = "This command requires Zelkor Pro or Enterprise. Community Edition does not apply it."
LATER = "This command is not in this release; it ships before v1.0.0-ce."

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
    aegra_host: str = ""
    gateway_name: str = ""
    gateway_namespace: str = ""
    jwt_secret: str = ""
    auth_dev_tokens_enabled: str = ""
    auth_dev_token_prefix: str = ""
    auth_trust_tenant_header: str = ""
    default_llm_model: str = ""
    agent_route_names: list[str] = field(default_factory=list)


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


def _run(
    argv: list[str],
    *,
    runner: Optional[RunFn] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    fn = runner or subprocess.run
    res = fn(argv, capture_output=capture, text=True, check=False)
    if check and res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(f"{' '.join(argv)} failed: {err}")
    return res


def kube_argv(env: Env, *args: str) -> list[str]:
    cmd = ["kubectl", "--context", env.kube_context, "-n", env.namespace]
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
    info = PlatformInfo()
    listed = _run(helm_argv(env, "list", "-o", "json"), runner=runner)
    releases = json.loads(listed.stdout or "[]")
    for rel in releases:
        chart = str(rel.get("chart") or "")
        if chart.startswith("zelkor-platform"):
            info.release = str(rel.get("name") or "")
            info.chart_version = chart.split("-")[-1] if "-" in chart else chart
            break
    if not info.release:
        raise RuntimeError("zelkor-platform Helm release not found in this env")
    values_raw = _run(helm_argv(env, "get", "values", info.release, "-o", "yaml"), runner=runner)
    values = yaml.safe_load(values_raw.stdout or "") or {}
    hosts = ((values.get("gateway") or {}).get("hosts") or {})
    info.aegra_host = str(hosts.get("aegra") or "")
    info.gateway_namespace = env.namespace
    deploys = _run(
        kube_argv(env, "get", "deploy", "-l", "app.kubernetes.io/component=aegra", "-o", "json"),
        runner=runner,
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
        info.jwt_secret = env_map.get("AUTH_JWT_SECRET", "")
        info.auth_dev_tokens_enabled = env_map.get("AUTH_DEV_TOKENS_ENABLED", "")
        info.auth_dev_token_prefix = env_map.get("AUTH_DEV_TOKEN_PREFIX", "")
        info.auth_trust_tenant_header = env_map.get("AUTH_TRUST_TENANT_HEADER", "")
        info.default_llm_model = default_llm_model_from(env_map, values)
        name = (dep.get("metadata") or {}).get("name") or ""
        if name:
            info.gateway_name = f"{str(name).rsplit('-aegra', 1)[0]}-gateway"
        break
    routes = _run(kube_argv(env, "get", "httproute", "-o", "json"), runner=runner, check=False)
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
    return str(((values.get("guardrails") or {}).get("nemo") or {}).get("model") or "").strip()


def _truthy(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def auth_values(info: PlatformInfo) -> dict[str, Any]:
    """Copy live platform wrap auth onto the worker. Do not invent secrets."""
    return {
        "jwtSecret": info.jwt_secret,
        "devTokens": {
            "enabled": _truthy(info.auth_dev_tokens_enabled),
            "prefix": info.auth_dev_token_prefix,
        },
        "trustTenantHeader": _truthy(info.auth_trust_tenant_header),
    }


def merge_extra_backends(existing: list[Any], extra: list[dict[str, str]]) -> list[dict[str, str]]:
    by_name: dict[str, dict[str, str]] = {}
    for row in existing or []:
        if isinstance(row, dict) and row.get("name") and row.get("url"):
            by_name[str(row["name"])] = {"name": str(row["name"]), "url": str(row["url"])}
    for row in extra:
        by_name[row["name"]] = {"name": row["name"], "url": row["url"]}
    return list(by_name.values())


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
        customer_dockerfile(os.getenv("ZELKOR_DEEP_IMAGE", "ghcr.io/devopssquaddev/zelkor-aegra-deep:dev")),
        encoding="utf-8",
    )
    if shape_kind == "deploy-first":
        (dest / "langgraph.json").write_text(
            json.dumps(deploy_first_langgraph(graph_id), indent=2),
            encoding="utf-8",
        )


def _is_kind(env: Env) -> bool:
    return env.kube_context.startswith("kind-") or os.getenv("KIND_CLUSTER", "") != ""


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
) -> dict[str, Any]:
    shape = detect(root, graph_id_flag)
    release = helm_release_name(shape.graph_id)
    info = discover_platform(env, runner=runner)
    as_default = should_attach_as_default(info.agent_route_names, release)
    registry = os.getenv("ZELKOR_IMAGE_REGISTRY", "ghcr.io/devopssquaddev").rstrip("/")
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
            "host": info.aegra_host,
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
        },
        "auth": auth_values(info),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(overlay, fh)
        values_file = fh.name
    try:
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
        )
        plat_args = helm_argv(env, "upgrade", info.release, str(platform_chart), "--reuse-values")
        plat_file = ""
        if as_default:
            plat_args.extend(["--set", "aegra.attachDefaultRoute=false"])
        if shape.mcp_servers:
            current = yaml.safe_load(
                _run(helm_argv(env, "get", "values", info.release, "-o", "yaml"), runner=runner).stdout or ""
            ) or {}
            plat = {
                "mcp": {
                    "extraBackends": merge_extra_backends(
                        ((current.get("mcp") or {}).get("extraBackends") or []),
                        list(shape.mcp_servers),
                    )
                }
            }
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as pfh:
                yaml.safe_dump(plat, pfh)
                plat_file = pfh.name
            plat_args.extend(["-f", plat_file])
        if as_default or shape.mcp_servers:
            try:
                _run(plat_args, runner=runner)
            finally:
                if plat_file:
                    Path(plat_file).unlink(missing_ok=True)
        _run(
            kube_argv(
                env,
                "rollout",
                "status",
                f"deployment/{release}-zelkor-agent",
                "--timeout=180s",
            ),
            runner=runner,
        )
    finally:
        Path(values_file).unlink(missing_ok=True)
    return {"release": release, "graph_id": shape.graph_id, "as_default": as_default, "image": image_ref}


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
    listed = _run(helm_argv(env, "list", "-o", "json"), runner=runner)
    print("Helm releases:")
    for rel in json.loads(listed.stdout or "[]"):
        chart = str(rel.get("chart") or "")
        if "zelkor-agent" in chart or str(rel.get("name") or "").endswith("zelkor-agent"):
            print(f"  {rel.get('name')}  {chart}  {rel.get('status')}")
        if chart.startswith("zelkor-platform"):
            print(f"  {rel.get('name')}  {chart}  {rel.get('status')}")
    routes = _run(kube_argv(env, "get", "httproute", "-o", "json"), runner=runner, check=False)
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
        ("Aegra host", bool(info.aegra_host)),
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
    base = url or os.getenv("ZELKOR_AEGRA_URL") or (f"http://{info.aegra_host}" if info.aegra_host else "")
    if not base:
        print("no Aegra URL; pass --url or set ZELKOR_AEGRA_URL", file=sys.stderr)
        return 1
    token = auth or os.getenv("ZELKOR_AUTH_TOKEN") or os.getenv("AEGRA_AUTH_TOKEN") or ""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    from urllib.parse import urlparse

    parsed = urlparse(base)
    if info.aegra_host and parsed.hostname != info.aegra_host:
        headers["Host"] = info.aegra_host
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


def main(argv: Optional[list[str]] = None, runner: Optional[RunFn] = None) -> int:
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
    sub.add_parser("status", help="agent Helm releases and HTTPRoutes")
    sub.add_parser("doctor", help="check discovered platform endpoints")
    sub.add_parser("version", help="CLI and platform chart version")

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
    for later in sorted(NOT_YET):
        later_p = sub.add_parser(later, help="ships before v1.0.0-ce")
        later_p.add_argument("rest", nargs=argparse.REMAINDER)

    for p in (sub.choices["dev"], sub.choices["deploy"]):
        p.add_argument("--graph-id", default="")
        p.add_argument("directory", nargs="?", default=".")

    args = parser.parse_args(argv)
    if args.cmd in PAID:
        print(UPGRADE, file=sys.stderr)
        return 2
    if args.cmd in NOT_YET:
        print(LATER, file=sys.stderr)
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
        result = deploy_agent(
            root=root,
            env=env,
            push=args.cmd == "deploy",
            graph_id_flag=args.graph_id,
            agent_chart=agent_chart,
            platform_chart=platform_chart,
            runner=runner,
        )
    except DetectError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
