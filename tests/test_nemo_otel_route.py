import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "guardrails"))

from otel_project_route import (  # noqa: E402
    basic_auth_header,
    identity_from_headers,
    install,
    is_orphan_http_client,
    parse_extra_otlp,
    pk_from_span,
    stamp_identity,
    traces_endpoint,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: E402
from opentelemetry.sdk.trace.export import SpanExportResult  # noqa: E402


def test_parse_extra_otlp():
    raw = json.dumps(
        [
            {
                "publicKey": "pk-lf-team-a-dev-00000000000000000000",
                "secretKey": "sk-lf-team-a-dev-00000000000000000000",
            }
        ]
    )
    mapped = parse_extra_otlp(raw)
    assert mapped["pk-lf-team-a-dev-00000000000000000000"] == "sk-lf-team-a-dev-00000000000000000000"
    assert parse_extra_otlp("") == {}


def test_pk_from_span_falls_back():
    class _Span:
        attributes = {"zelkor.langfuse.pk": "pk-extra"}

    assert pk_from_span(_Span(), "pk-default") == "pk-extra"

    class _Empty:
        attributes = {}

    assert pk_from_span(_Empty(), "pk-default") == "pk-default"
    assert basic_auth_header("pk", "sk").startswith("Basic ")


def test_traces_endpoint_appends_v1_traces():
    base = "http://zelkor-platform-langfuse:3000/api/public/otel"
    assert traces_endpoint(base) == base + "/v1/traces"
    assert traces_endpoint(base + "/v1/traces") == base + "/v1/traces"
    assert traces_endpoint("") == ""


def test_is_orphan_http_client():
    class _Orphan:
        name = "POST /v1/chat/completions http send"
        kind = type("K", (), {"name": "CLIENT"})()
        parent = None

    class _Nested:
        name = "POST /v1/chat/completions http send"
        kind = type("K", (), {"name": "CLIENT"})()
        parent = type("P", (), {"is_valid": lambda self: True})()

    class _Server:
        name = "POST /v1/chat/completions"
        kind = type("K", (), {"name": "SERVER"})()
        parent = None

    assert is_orphan_http_client(_Orphan())
    assert not is_orphan_http_client(_Nested())
    assert not is_orphan_http_client(_Server())


def test_identity_from_headers_and_stamp():
    values = identity_from_headers(
        {
            "x-zelkor-langfuse-pk": "pk-x",
            "x-zelkor-langfuse-trace-name": "finserve-advisor",
            "x-zelkor-langfuse-session-id": "th-1",
            "x-zelkor-langfuse-user-id": "Bank_Alpha",
        }
    )
    assert values["langfuse.trace.name"] == "finserve-advisor"
    assert values["zelkor.langfuse.pk"] == "pk-x"

    class _Span:
        def __init__(self) -> None:
            self.attrs: dict = {}

        def set_attribute(self, key, value) -> None:
            self.attrs[key] = value

    span = _Span()
    stamp_identity(span, values)
    assert span.attrs["langfuse.trace.name"] == "finserve-advisor"
    assert span.attrs["langfuse.session.id"] == "th-1"
    assert span.attrs["user.id"] == "Bank_Alpha"
    assert span.attrs["zelkor.langfuse.pk"] == "pk-x"


def _reset_install() -> None:
    install._done = False  # type: ignore[attr-defined]


def _span(name: str = "guardrails.request", pk: str | None = None):
    attrs = {}
    if pk:
        attrs["zelkor.langfuse.pk"] = pk
    return type("_Span", (), {"name": name, "attributes": attrs, "kind": None, "parent": None})()


def _install_with_export_stub(monkeypatch, *, extra_otlp: str, default_pk: str, default_sk: str):
    created: list[dict] = []
    root_exports: list[int] = []
    leaf_exports: list[int] = []
    orig_init = OTLPSpanExporter.__init__

    def _capture_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        created.append(dict(kwargs.get("headers") or {}))

    def _stub_export(self, spans):
        if getattr(self, "_zelkor_route_leaf", False):
            leaf_exports.append(len(spans))
            return SpanExportResult.SUCCESS
        root_exports.append(len(spans))
        return SpanExportResult.SUCCESS

    monkeypatch.setenv("LANGFUSE_EXTRA_OTLP", extra_otlp)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", default_pk)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", default_sk)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://zelkor-platform-langfuse:3000/api/public/otel",
    )
    monkeypatch.setattr(OTLPSpanExporter, "__init__", _capture_init)
    monkeypatch.setattr(OTLPSpanExporter, "export", _stub_export)
    _reset_install()
    install()
    return created, root_exports, leaf_exports


def test_export_uses_default_langfuse_auth_when_extra_empty(monkeypatch):
    created, root_exports, leaf_exports = _install_with_export_stub(
        monkeypatch,
        extra_otlp="[]",
        default_pk="pk-default",
        default_sk="sk-default",
    )
    root = OTLPSpanExporter(endpoint="http://ignored")
    OTLPSpanExporter.export(root, [_span()])

    assert root_exports == [], "root exporter must not export without Langfuse auth"
    assert leaf_exports == [1]
    assert basic_auth_header("pk-default", "sk-default") in {
        h.get("Authorization") for h in created
    }


def test_export_routes_default_pk_when_extra_has_other_projects(monkeypatch):
    created, root_exports, leaf_exports = _install_with_export_stub(
        monkeypatch,
        extra_otlp=json.dumps(
            [{"publicKey": "pk-extra", "secretKey": "sk-extra"}]
        ),
        default_pk="pk-default",
        default_sk="sk-default",
    )
    root = OTLPSpanExporter(endpoint="http://ignored")
    OTLPSpanExporter.export(root, [_span()])

    assert root_exports == []
    assert leaf_exports == [1]
    assert basic_auth_header("pk-default", "sk-default") in {
        h.get("Authorization") for h in created
    }
