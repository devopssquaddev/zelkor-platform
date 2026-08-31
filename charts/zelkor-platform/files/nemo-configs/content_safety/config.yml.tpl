models:
  - type: main
    engine: openai
    model: {{ .Values.guardrails.nemo.model | default "openai/gpt-4o-mini" | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayInternalUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        {{- if .Values.gateway.hosts.aiGateway }}
        Host: {{ .Values.gateway.hosts.aiGateway | quote }}
        {{- end }}

# Required for OpenAI-style tools on NeMo's /v1 (still runs input/output rails).
passthrough: true

rails:
{{- if .Values.guardrails.nemo.extraRailsConfig }}
  config:
{{ toYaml .Values.guardrails.nemo.extraRailsConfig | indent 4 }}
{{- end }}
  input:
    flows:
      - self check input
{{- range .Values.guardrails.nemo.extraInputFlows }}
      - {{ . }}
{{- end }}
  output:
    flows:
      - self check output
