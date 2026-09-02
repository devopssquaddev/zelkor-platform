FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor NeMo Guardrails FastAPI server (CPU-native)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY images/guardrails/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY images/guardrails/otel_project_route.py /app/otel_project_route.py
COPY images/guardrails/boot.py /app/boot.py

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && mkdir -p /etc/nemoguardrails/configs/content_safety \
    && chown -R zelkor:zelkor /etc/nemoguardrails /app/otel_project_route.py /app/boot.py
USER 1000

EXPOSE 8000
CMD ["nemoguardrails", "server", "--config", "/etc/nemoguardrails/configs", "--port", "8000", "--default-config-id", "content_safety", "--disable-chat-ui"]
