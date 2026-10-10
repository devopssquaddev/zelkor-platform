ARG ZELKOR_AEGRA_IMAGE=ghcr.io/devopssquaddev/zelkor-aegra:2.3.1
FROM ${ZELKOR_AEGRA_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/devopssquaddev/zelkor-platform"
LABEL org.opencontainers.image.description="Legal-redline example agent (not part of the platform chart)"

USER root
RUN pip install --no-cache-dir 'boto3>=1.35,<2'
COPY examples/legal-redline/chart/files/clause_check.py /app/clause_check.py
COPY examples/legal-redline/chart/files/legal_redline_agent.py /app/legal_redline_agent.py
COPY examples/legal-redline/chart/files/seed.py /app/seed.py
COPY examples/legal-redline/chart/files/contract.txt /app/contract.txt
COPY examples/legal-redline/chart/files/aegra.json /app/aegra.json
RUN chown -R zelkor:zelkor /app/clause_check.py /app/legal_redline_agent.py /app/seed.py /app/contract.txt /app/aegra.json
USER 1000
