FROM python:3.14.9-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp PYDANTIC_AI_NO_BANNER=1
WORKDIR /app

COPY images/runtime-pydantic-ai/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY images/runtime-common/zelkor_runtime_spec.py /opt/zelkor/zelkor_runtime_spec.py
COPY images/common/zelkor_logging.py /opt/zelkor/zelkor_logging.py
COPY images/runtime-pydantic-ai/zelkor_runtime.py /opt/zelkor/zelkor_runtime.py
ENV PYTHONPATH=/opt/zelkor

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin zelkor \
    && chmod -R a+rX /opt/zelkor /app
USER 1000

# Customer image: FROM this, COPY agent.json AGENTS.md /app/
CMD ["python", "/opt/zelkor/zelkor_runtime.py"]
