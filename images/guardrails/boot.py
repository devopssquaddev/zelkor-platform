"""Load Langfuse project routing, then run the NeMo CLI in-process."""
import logging
import sys

from zelkor_logging import configure_logging

configure_logging("zelkor-nemo")
logger = logging.getLogger("zelkor-nemo")

from otel_project_route import install

install()
logger.info("NeMo intercept ready", extra={"event": "startup"})
sys.argv = ["nemoguardrails"] + sys.argv[1:]
from nemoguardrails.cli import app  # noqa: E402

app()
