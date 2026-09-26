"""Run NeMo Langfuse OTLP routing before opentelemetry-instrument configures exporters."""
import logging
import sys

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

_log = logging.getLogger("zelkor-nemo-otel")

try:
    from otel_project_route import install

    install()
    _log.info("NeMo OTEL route patch applied (sitecustomize)")
except Exception:
    _log.exception("NeMo OTEL route patch failed (sitecustomize)")
