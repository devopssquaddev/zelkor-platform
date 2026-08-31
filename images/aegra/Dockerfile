FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor Aegra production runtime (aegra-api + tenant auth)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    AEGRA_CONFIG=/app/aegra.json \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY images/aegra/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY agents/tenant_auth.py /app/tenant_auth.py
COPY images/aegra/aegra.json /app/aegra.json
COPY images/aegra/auth_inject.py /app/auth_inject.py
COPY images/aegra/mcp_inject.py /app/mcp_inject.py
COPY images/aegra/sitecustomize.py /usr/local/lib/python3.12/site-packages/sitecustomize.py

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown -R zelkor:zelkor /app
USER 1000

EXPOSE 8000
CMD ["uvicorn", "aegra_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
