models:
  - type: main
    engine: openai
    model: {{ .Values.guardrails.nemo.model | default "openai/gpt-4o-mini" | quote }}
    parameters:
      openai_api_base: {{ include "zelkor-platform.aiGatewayInternalUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        {{- if .Values.gateway.hosts.aiGateway }}
        Host: {{ .Values.gateway.hosts.aiGateway | quote }}
        {{- end }}

rails:
  input:
    flows:
      - self check input
  output:
    flows:
      - self check output
