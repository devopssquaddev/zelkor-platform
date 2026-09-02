FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor gVisor sandbox worker for MCP execute_python"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY images/sandbox-worker/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY mcp/sandbox/worker.py /app/worker.py
COPY images/common/zelkor_logging.py /app/zelkor_logging.py

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown -R zelkor:zelkor /app
USER 1000

EXPOSE 8081
CMD ["python", "/app/worker.py"]
