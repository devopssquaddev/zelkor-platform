ARG ZELKOR_AEGRA_DEEP_IMAGE=ghcr.io/devopssquaddev/zelkor-aegra-deep:2.3.1
FROM ${ZELKOR_AEGRA_DEEP_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Unmodified GPT Researcher deep_agents wrap; not part of the platform chart"

USER root
ARG GPTR_VERSION=v3.7.0
ADD https://github.com/assafelovic/gpt-researcher/archive/refs/tags/${GPTR_VERSION}.tar.gz /tmp/gptr.tar.gz
RUN tar -xzf /tmp/gptr.tar.gz -C /tmp \
    && SRC="/tmp/gpt-researcher-${GPTR_VERSION#v}" \
    && pip install "$SRC" \
    && pip install -r "$SRC/deep_agents/requirements.txt" \
    && cp -a "$SRC/gpt_researcher" /app/gpt_researcher \
    && cp -a "$SRC/deep_agents" /app/deep_agents \
    && cp "$SRC/LICENSE" /app/LICENSE.gpt-researcher \
    && rm -rf /tmp/gptr.tar.gz "$SRC"

COPY examples/armored-agents/gpt-researcher/langgraph.json /app/langgraph.json
COPY examples/armored-agents/gpt-researcher/graph.py /app/graph.py
RUN chown -R zelkor:zelkor /app/gpt_researcher /app/deep_agents /app/langgraph.json /app/graph.py /app/LICENSE.gpt-researcher \
    && rm -f /app/aegra.json
ENV AEGRA_CONFIG=
ENV PYTHONPATH=/app
USER 1000
