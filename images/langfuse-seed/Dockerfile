FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor Langfuse surface seed (LLM connection, MCP tools, code evaluators)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY images/langfuse-seed/seed.py /app/seed.py

RUN pip install --no-cache-dir "psycopg[binary]==3.2.10" "bcrypt==4.3.0" \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown zelkor:zelkor /app/seed.py
USER 1000

CMD ["python", "/app/seed.py"]
