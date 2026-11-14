"""Kind installer: --profile is the product mode (Helm `profile`), --stage the install stage;
the closing summary describes what the selected mode installed (no cluster)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _parse(*flags: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    script = (f'source "{ROOT}/install.sh"; install_parse_flags "$@"; '
              'echo "INSTALL_PROFILE=${INSTALL_PROFILE:-}"; echo "REST=${INSTALL_PASSTHRU[*]:-}"')
    clean = {k: v for k, v in os.environ.items() if k != "INSTALL_PROFILE"}
    return subprocess.run(["bash", "-c", script, "_", *flags], capture_output=True, text=True,
                          env={**clean, **(env or {})}, check=False)


def _profile(proc: subprocess.CompletedProcess[str]) -> str:
    assert proc.returncode == 0, proc.stderr
    return next(line.split("=", 1)[1] for line in proc.stdout.splitlines() if line.startswith("INSTALL_PROFILE="))


@pytest.mark.parametrize("flags, expected", [
    (("--profile=perimeter",), "perimeter"),
    (("--profile", "perimeter"), "perimeter"),
    (("--stage=full",), "full"),
    (("--stage", "fast"), "fast"),
    (("--profile=full",), ""),  # the full product is the default; the stage stays the default
])
def test_profile_selects_the_mode_and_stage_the_kind_stage(flags, expected):
    assert _profile(_parse(*flags)) == expected


def test_profile_fast_still_works_as_a_deprecated_stage_alias():
    proc = _parse("--profile=fast")
    assert _profile(proc) == "fast"
    assert "--stage=fast" in proc.stderr


def test_unknown_profile_is_rejected_and_other_flags_pass_through():
    assert _parse("--profile=bogus").returncode != 0
    proc = _parse("--profile=perimeter", "--skip-operators")
    assert "REST=--skip-operators" in proc.stdout


def _footer(perimeter: bool, tmp_path: Path, extra: str = "") -> str:
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "kubectl").write_text("#!/bin/sh\nexit 1\n")
    (stub / "kubectl").chmod(0o755)
    script = f"""
source <(sed -n '/^install_print_access_footer()/,/^}}/p' "{ROOT}/scripts/install-engine.sh")
mcp_dataplane_print_token_banner() {{ :; }}
KCTX=kind-zelkor HELM_RELEASE_NAME=zelkor-platform INSTALL_EXAMPLES=false
LLM_PROVIDER_SUMMARY=openai DEFAULT_LLM_MODEL=gpt-x DOWNLOAD_DURATION=0
INSTALL_MINUTES=1 INSTALL_SECONDS=2 INSTALL_DURATION=62 DEGRADED_COMPONENTS=() NOT_VERIFIED=()
PERIMETER={"true" if perimeter else "false"} {extra}
install_print_access_footer
"""
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                          env={**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_perimeter_summary_shows_what_perimeter_installed(tmp_path):
    out = _footer(True, tmp_path)
    for absent in ("Langfuse", "Aegra", "PostgreSQL", "NeMo"):
        assert absent not in out, absent
    for present in ("http://ai-gateway.localhost:8088", "zelkor deploy", "zelkor run", "llm_access",
                    "zelkor token mint --release zelkor-platform --tenant tenant-a"):
        assert present in out, present


def test_full_summary_is_unchanged_in_substance(tmp_path):
    out = _footer(False, tmp_path)
    for present in ("Langfuse", "Aegra", "PostgreSQL", "http://ai-gateway.localhost:8088"):
        assert present in out, present


def _ux(call: str, profile: str) -> str:
    script = f'source "{ROOT}/install.sh"; ux_init_colors; ux_init_glyphs; INSTALL_PROFILE={profile}; {call}'
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                          env={**os.environ, "NO_COLOR": "1"})
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_progress_panel_names_the_perimeter_mode():
    header = _ux("ux_panel_mode_lines zelkor", "perimeter")
    assert "perimeter" in header and "fast" not in header
    assert "fast" in _ux("ux_panel_mode_lines zelkor", "fast")
    assert _ux("ux_phase_label 3", "perimeter").strip() == "Platform chart"
    assert _ux("ux_phase_label 3", "fast").strip() == "Datastores"


def test_opt_in_flags_export_the_perimeter_opt_ins():
    script = (f'source "{ROOT}/install.sh"; install_parse_flags "$@"; '
              'echo "G=${PERIMETER_GUARDRAILS:-} S=${PERIMETER_SANDBOX:-} REST=${INSTALL_PASSTHRU[*]:-}"')
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("PERIMETER_", "INSTALL_PROFILE"))}
    proc = subprocess.run(["bash", "-c", script, "_", "--profile=perimeter", "--with-guardrails", "--with-sandbox"],
                          capture_output=True, text=True, env=clean, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "G=true S=true REST=" in proc.stdout
    warn = subprocess.run(["bash", "-c", script, "_", "--with-sandbox"], capture_output=True, text=True,
                          env=clean, check=False)
    assert "apply to --profile=perimeter" in warn.stderr


def test_perimeter_summary_names_the_opt_ins(tmp_path):
    out = _footer(True, tmp_path, "PERIMETER_GUARDRAILS=true PERIMETER_SANDBOX=true")
    assert "NeMo Guardrails" in out and "sandbox__execute_python" in out
    assert "Langfuse" not in out and "Aegra" not in out


def test_progress_panel_names_the_perimeter_opt_ins():
    script = (f'source "{ROOT}/install.sh"; ux_init_colors; ux_init_glyphs; INSTALL_PROFILE=perimeter; '
              'PERIMETER_GUARDRAILS=true PERIMETER_SANDBOX=true; ux_panel_mode_lines zelkor')
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                         env={**os.environ, "NO_COLOR": "1"}).stdout
    assert "perimeter + NeMo + sandbox" in out
