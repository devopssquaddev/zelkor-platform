# Your agent on the stock Zelkor Pydantic AI runtime: same A2A server, plus your own tools.
FROM ghcr.io/devopssquaddev/zelkor-runtime-pydantic-ai:2.5.4
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
COPY agent.json AGENTS.md /app/
COPY agent.py github_tools.py /opt/example/
RUN chmod -R a+rX /app /opt/example
ENV PYTHONPATH=/opt/example:/opt/zelkor
USER 1000
CMD ["python", "/opt/example/agent.py"]
