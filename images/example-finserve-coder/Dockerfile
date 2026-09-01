ARG ZELKOR_AEGRA_DEEP_IMAGE=ghcr.io/devopssquaddev/zelkor-aegra-deep:dev
FROM ${ZELKOR_AEGRA_DEEP_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="FinServe deploy-first Deep Agent (coder); not part of the platform chart"

USER root
COPY examples/finserve/coder/ /app/
COPY images/example-finserve-coder/langgraph.json /app/langgraph.json
RUN chown -R zelkor:zelkor /app/agent.json /app/AGENTS.md /app/skills /app/langgraph.json
USER 1000
