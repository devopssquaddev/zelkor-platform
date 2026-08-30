FROM ghcr.io/devopssquaddev/zelkor-aegra:dev

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="FinServe demo agent (Mode B drop-in, not part of the platform chart)"

USER root
COPY examples/finserve/chart/files/finserve_agent.py /app/finserve_agent.py
COPY examples/finserve/chart/files/aegra.json /app/aegra.json
RUN chown -R zelkor:zelkor /app/finserve_agent.py /app/aegra.json
USER 1000
