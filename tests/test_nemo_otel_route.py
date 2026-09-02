import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "images" / "guardrails"))

from otel_project_route import (  # noqa: E402
    basic_auth_header,
    identity_from_headers,
    is_orphan_http_client,
    parse_extra_otlp,
    pk_from_span,
    stamp_identity,
    traces_endpoint,
)


def test_parse_extra_otlp():
    raw = json.dumps(
        [
            {
                "publicKey": "pk-lf-finserve-dev-00000000000000000000",
                "secretKey": "sk-lf-finserve-dev-00000000000000000000",
            }
        ]
    )
    mapped = parse_extra_otlp(raw)
    assert mapped["pk-lf-finserve-dev-00000000000000000000"] == "sk-lf-finserve-dev-00000000000000000000"
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
