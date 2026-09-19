{{- $selfCheck := eq (include "zelkor-platform.nemoSelfCheckEnabled" .) "true" }}
{{- $selfCheckModel := include "zelkor-platform.nemoSelfCheckModel" . }}
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
{{- if $selfCheck }}
  - type: self_check_input
    engine: openai
    model: {{ $selfCheckModel | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayInternalUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        {{- if .Values.gateway.hosts.aiGateway }}
        Host: {{ .Values.gateway.hosts.aiGateway | quote }}
        {{- end }}
  - type: self_check_output
    engine: openai
    model: {{ $selfCheckModel | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayInternalUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        {{- if .Values.gateway.hosts.aiGateway }}
        Host: {{ .Values.gateway.hosts.aiGateway | quote }}
        {{- end }}
{{- end }}

# Required for OpenAI-style tools on NeMo's /v1 (I/O rails when selfCheck.enabled).
passthrough: true

{{- if eq (include "zelkor-platform.nemoOtelEnabled" .) "true" }}
tracing:
  enabled: true
  enable_content_capture: {{ .Values.guardrails.nemo.observability.otel.captureContent | default false }}
  adapters:
    - name: OpenTelemetry
{{- end }}

rails:
{{- if .Values.guardrails.nemo.extraRailsConfig }}
  config:
{{ toYaml .Values.guardrails.nemo.extraRailsConfig | indent 4 }}
{{- end }}
  input:
{{- if or $selfCheck .Values.guardrails.nemo.extraInputFlows }}
    flows:
{{- if $selfCheck }}
      - self check input
{{- end }}
{{- range .Values.guardrails.nemo.extraInputFlows }}
      - {{ . }}
{{- end }}
{{- else }}
    flows: []
{{- end }}
  output:
    streaming:
      enabled: true
{{- if $selfCheck }}
    flows:
      - self check output
{{- else }}
    flows: []
{{- end }}
