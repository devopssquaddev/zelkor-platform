FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="FinServe demo agent (not part of the platform chart)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY images/example-finserve/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY examples/finserve/chart/files/agent_server.py /app/agent_server.py
COPY examples/finserve/chart/files/finserve_agent.py /app/finserve_agent.py

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown -R zelkor:zelkor /app
USER 1000

EXPOSE 8080
CMD ["python", "/app/agent_server.py"]
