{{- $selfCheck := eq (include "zelkor-platform.nemoSelfCheckEnabled" .) "true" }}
define bot refuse to respond
  {{ .Values.guardrails.nemo.safetyRefusal | default "I can't help with that request." | quote }}
{{- if $selfCheck }}

# nemoguardrails 0.24 actions return a RailOutcome (always truthy): branch on is_blocked.
define flow self check input
  $response = execute self_check_input
  if $response.is_blocked
    bot refuse to respond
    stop

define flow self check output
  $response = execute self_check_output
  if $response.is_blocked
    bot refuse to respond
    stop
{{- end }}
{{- if .Values.guardrails.nemo.extraColang }}

{{ .Values.guardrails.nemo.extraColang }}
{{- end }}
