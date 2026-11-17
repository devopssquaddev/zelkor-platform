{{- $inMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "input") }}
{{- $outMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "output") }}
{{- $selfCheckModel := include "zelkor-platform.nemoSelfCheckModel" . }}
{{- $mainModel := include "zelkor-platform.nemoEffectiveModel" . }}
models:
  - type: main
    engine: openai
    model: {{ $mainModel | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayNemoUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        X-Ai-Eg-Model: {{ $mainModel | quote }}
        {{- if not .Values.aiGateway.inClusterService.enabled }}
        Host: {{ include "zelkor-platform.aiGatewayNemoHost" . | quote }}
        {{- end }}
{{- if ne $inMode "none" }}
  - type: self_check_input
    engine: openai
    model: {{ $selfCheckModel | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayNemoUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        X-Ai-Eg-Model: {{ $selfCheckModel | quote }}
        {{- if not .Values.aiGateway.inClusterService.enabled }}
        Host: {{ include "zelkor-platform.aiGatewayNemoHost" . | quote }}
        {{- end }}
{{- end }}
{{- if ne $outMode "none" }}
  - type: self_check_output
    engine: openai
    model: {{ $selfCheckModel | quote }}
    parameters:
      base_url: {{ include "zelkor-platform.aiGatewayNemoUrl" . | quote }}
      default_headers:
        X-Zelkor-Guardrails-Bypass: "1"
        X-Ai-Eg-Model: {{ $selfCheckModel | quote }}
        {{- if not .Values.aiGateway.inClusterService.enabled }}
        Host: {{ include "zelkor-platform.aiGatewayNemoHost" . | quote }}
        {{- end }}
{{- end }}

# Required for OpenAI-style tools on NeMo's /v1 (I/O rails when self-check is on).
passthrough: true

{{- if eq (include "zelkor-platform.nemoOtelEnabled" .) "true" }}
tracing:
  enabled: true
  enable_content_capture: {{ include "zelkor-platform.nemoOtelCaptureContent" . }}
  adapters:
    - name: OpenTelemetry
{{- end }}

rails:
{{- if .Values.guardrails.nemo.extraRailsConfig }}
  config:
{{ toYaml .Values.guardrails.nemo.extraRailsConfig | indent 4 }}
{{- end }}
  input:
{{- if or (ne $inMode "none") .Values.guardrails.nemo.extraInputFlows }}
    flows:
{{- if ne $inMode "none" }}
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
{{- if ne $outMode "none" }}
    flows:
      - self check output
{{- else }}
    flows: []
{{- end }}
