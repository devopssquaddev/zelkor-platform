models:
  - type: main
    engine: openai
    model: {{ .Values.guardrails.nemo.model | default "openai/gpt-4o-mini" | quote }}
    parameters:
      openai_api_base: {{ include "zelkor-platform.aiGatewayInternalUrl" . | quote }}
      default_headers:
        Host: {{ .Values.gateway.hosts.aiGateway | default "ai-gateway.localhost" | quote }}

rails:
  input:
    flows:
      - self check input
  output:
    flows:
      - self check output
