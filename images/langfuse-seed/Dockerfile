FROM python:3.14.8-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor Langfuse seed (admin signup, LLM connection, MCP tools, code evaluators)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY images/langfuse-seed/seed.py /app/seed.py
COPY images/langfuse-seed/evaluators /app/evaluators
COPY images/common/zelkor_logging.py /app/zelkor_logging.py

RUN pip install --no-cache-dir "psycopg[binary]==3.2.10" "bcrypt==4.3.0" "mcp==1.30.0" "httpx==0.28.1" \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown -R zelkor:zelkor /app/seed.py /app/zelkor_logging.py /app/evaluators
USER 1000

CMD ["python", "/app/seed.py"]
