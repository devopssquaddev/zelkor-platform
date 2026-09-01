ARG ZELKOR_AEGRA_IMAGE=ghcr.io/devopssquaddev/zelkor-aegra:dev
FROM ${ZELKOR_AEGRA_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Zelkor Aegra + Deep Agents factory (CLI workers; not the front door)"

USER root
COPY images/aegra-deep/requirements.txt /tmp/requirements-deep.txt
RUN pip install -r /tmp/requirements-deep.txt && rm /tmp/requirements-deep.txt

COPY images/aegra-deep/zelkor_deep_factory.py /app/zelkor_deep_factory.py
COPY images/aegra-deep/zelkor_gvisor_backend.py /app/zelkor_gvisor_backend.py
COPY images/aegra-deep/langgraph.json /app/langgraph.json

# Parent ships empty-graphs aegra.json and AEGRA_CONFIG pointing at it. Aegra prefers
# aegra.json over langgraph.json — remove it and leave AEGRA_CONFIG unset.
RUN rm -f /app/aegra.json \
    && chown zelkor:zelkor /app/zelkor_deep_factory.py /app/zelkor_gvisor_backend.py /app/langgraph.json
ENV AEGRA_CONFIG=
USER 1000
