"""Load Langfuse project routing, then run the NeMo CLI in-process."""
import sys

from otel_project_route import install

install()
sys.argv = ["nemoguardrails"] + sys.argv[1:]
from nemoguardrails.cli import app  # noqa: E402

app()
