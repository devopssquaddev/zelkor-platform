"""Load Langfuse project routing, then run the NeMo CLI in-process."""
import logging
import sys

from zelkor_logging import configure_logging, wrap_uvicorn_run

configure_logging("zelkor-nemo")
wrap_uvicorn_run()
logger = logging.getLogger("zelkor-nemo")

from otel_project_route import install

install()
# opentelemetry-instrument's sitecustomize shadows ours, so install here, before the CLI.
from quiet_verbose import install as install_quiet_verbose

install_quiet_verbose()
# Same reason: the server process never runs our sitecustomize, so a missing `content` key would
# still reach NeMo (KeyError -> 500) if the patch were installed only there.
from message_content import install as install_message_content

install_message_content()
logger.info("NeMo intercept ready", extra={"event": "startup"})
sys.argv = ["nemoguardrails"] + sys.argv[1:]
from nemoguardrails.cli import app  # noqa: E402

from quiet_verbose import keep_component_level  # noqa: E402

keep_component_level("zelkor-nemo")  # the CLI import just set the root logger to WARNING
app()
