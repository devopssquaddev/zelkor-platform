FROM python:3.14.9-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY images/sidecar/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY images/sidecar/zelkor_sidecar /app/zelkor_sidecar
COPY mcp/common/jwt_verifier.py /app/jwt_verifier.py
COPY images/aegra/sandbox_trace.py /app/sandbox_trace.py
COPY images/common/zelkor_logging.py /app/zelkor_logging.py

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin zelkor \
    && chmod -R a+rX /app
USER 1000

EXPOSE 8000
ENTRYPOINT ["python", "-m"]
CMD ["zelkor_sidecar.main"]
