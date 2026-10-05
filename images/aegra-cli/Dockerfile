FROM python:3.14.8-slim-trixie

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor Aegra CLI (out-of-band alembic: aegra db upgrade)"

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

COPY images/aegra-cli/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY images/common/zelkor_logging.py /usr/local/lib/python3.14/site-packages/zelkor_logging.py
COPY images/aegra-cli/sitecustomize.py /usr/local/lib/python3.14/site-packages/sitecustomize.py

RUN chmod 644 /usr/local/lib/python3.14/site-packages/sitecustomize.py \
        /usr/local/lib/python3.14/site-packages/zelkor_logging.py \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin zelkor \
    && chown -R zelkor:zelkor /app
USER 1000

CMD ["aegra", "db", "upgrade"]
