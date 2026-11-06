ARG ZELKOR_SANDBOX_WORKER_IMAGE=ghcr.io/devopssquaddev/zelkor-sandbox-worker:2.4.2
FROM ${ZELKOR_SANDBOX_WORKER_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Example sandbox worker with a private package and python-dateutil; not part of the platform chart"

USER root
COPY images/example-sandbox-python/requirements.txt /tmp/requirements.txt
COPY examples/sandbox-python/desk_risk /tmp/desk_risk
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps /tmp/desk_risk \
    && rm -rf /tmp/requirements.txt /tmp/desk_risk
USER 1000
