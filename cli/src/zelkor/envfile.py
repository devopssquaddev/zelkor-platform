"""Named kubecontext envs. No hosts, tokens, or DSNs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

HOME_FILE = Path.home() / ".zelkor" / "envs.yaml"


@dataclass(frozen=True)
class Env:
    name: str
    kube_context: str
    namespace: str
    kubeconfig: str = ""


def _parse_env_map(raw: Any) -> dict[str, Env]:
    out: dict[str, Env] = {}
    if not isinstance(raw, dict):
        return out
    envs = raw.get("envs") if "envs" in raw else raw
    if not isinstance(envs, dict):
        return out
    for name, body in envs.items():
        if not isinstance(body, dict):
            continue
        ctx = str(body.get("kubeContext") or body.get("kube_context") or "").strip()
        ns = str(body.get("namespace") or "").strip()
        if not ctx or not ns:
            continue
        out[str(name)] = Env(
            name=str(name),
            kube_context=ctx,
            namespace=ns,
            kubeconfig=str(body.get("kubeconfig") or "").strip(),
        )
    return out


def load_store(path: Path | None = None) -> dict[str, Any]:
    target = path or HOME_FILE
    if not target.is_file():
        return {"current": "", "envs": {}}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"current": "", "envs": {}}
    return data


def save_store(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or HOME_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    dump: dict[str, Any] = {"current": data.get("current") or "", "envs": {}}
    for name, env in _parse_env_map(data).items():
        body: dict[str, str] = {"kubeContext": env.kube_context, "namespace": env.namespace}
        if env.kubeconfig:
            body["kubeconfig"] = env.kubeconfig
        dump["envs"][name] = body
        if not dump["current"]:
            dump["current"] = name
    if data.get("current"):
        dump["current"] = data["current"]
    target.write_text(yaml.safe_dump(dump, sort_keys=False), encoding="utf-8")


def project_env(cwd: Path | None = None) -> Optional[Env]:
    path = (cwd or Path.cwd()) / ".zelkor" / "env"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "project").strip()
    ctx = str(data.get("kubeContext") or data.get("kube_context") or "").strip()
    ns = str(data.get("namespace") or "").strip()
    if not ctx or not ns:
        return None
    return Env(
        name=name,
        kube_context=ctx,
        namespace=ns,
        kubeconfig=str(data.get("kubeconfig") or "").strip(),
    )


def resolve_env(
    *,
    name: str = "",
    prefer_local: bool = False,
    cwd: Path | None = None,
    store_path: Path | None = None,
) -> Env:
    proj = project_env(cwd)
    store = load_store(store_path)
    envs = _parse_env_map(store)
    if name:
        if name in envs:
            return envs[name]
        raise KeyError(f"unknown env {name}")
    if prefer_local and "local" in envs:
        return envs["local"]
    if proj:
        return proj
    current = str(store.get("current") or "")
    if current and current in envs:
        return envs[current]
    if len(envs) == 1:
        return next(iter(envs.values()))
    raise KeyError("no env selected; run `zelkor env add` or pass --env")


def add_env(env: Env, *, store_path: Path | None = None, make_current: bool = True) -> None:
    data = load_store(store_path)
    envs = _parse_env_map(data)
    envs[env.name] = env
    save_store(
        {
            "current": env.name if make_current else (data.get("current") or env.name),
            "envs": {
                k: {
                    "kubeContext": v.kube_context,
                    "namespace": v.namespace,
                    **({"kubeconfig": v.kubeconfig} if v.kubeconfig else {}),
                }
                for k, v in envs.items()
            },
        },
        store_path,
    )


def remove_env(name: str, *, store_path: Path | None = None) -> None:
    data = load_store(store_path)
    envs = _parse_env_map(data)
    envs.pop(name, None)
    current = str(data.get("current") or "")
    if current == name:
        current = next(iter(envs), "")
    save_store(
        {
            "current": current,
            "envs": {
                k: {
                    "kubeContext": v.kube_context,
                    "namespace": v.namespace,
                    **({"kubeconfig": v.kubeconfig} if v.kubeconfig else {}),
                }
                for k, v in envs.items()
            },
        },
        store_path,
    )


def list_envs(store_path: Path | None = None) -> list[Env]:
    data = load_store(store_path)
    return list(_parse_env_map(data).values())
