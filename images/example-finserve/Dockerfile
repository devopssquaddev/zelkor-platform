ARG ZELKOR_AEGRA_IMAGE=ghcr.io/devopssquaddev/zelkor-aegra:1.2.2
FROM ${ZELKOR_AEGRA_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="FinServe demo agents (Mode B drop-in, not part of the platform chart)"

USER root
COPY examples/finserve/chart/files/mcp_tools.py /app/mcp_tools.py
COPY examples/finserve/chart/files/advisor_agent.py /app/advisor_agent.py
COPY examples/finserve/chart/files/research_agent.py /app/research_agent.py
COPY examples/finserve/chart/files/quant_agent.py /app/quant_agent.py
COPY examples/finserve/chart/files/aegra-desk.json /app/aegra-desk.json
COPY examples/finserve/chart/files/aegra-quant.json /app/aegra-quant.json
RUN chown -R zelkor:zelkor /app/mcp_tools.py /app/advisor_agent.py /app/research_agent.py /app/quant_agent.py /app/aegra-desk.json /app/aegra-quant.json
USER 1000
