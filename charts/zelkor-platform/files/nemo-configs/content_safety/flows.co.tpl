{{- $selfCheck := eq (include "zelkor-platform.nemoSelfCheckEnabled" .) "true" }}
define bot refuse to respond
  {{ .Values.guardrails.nemo.safetyRefusal | default "I can't help with that request." | quote }}
{{- if $selfCheck }}

define flow self check input
  $allowed = execute self_check_input
  if not $allowed
    bot refuse to respond
    stop

define flow self check output
  $allowed = execute self_check_output
  if not $allowed
    bot refuse to respond
    stop
{{- end }}
{{- if .Values.guardrails.nemo.extraColang }}

{{ .Values.guardrails.nemo.extraColang }}
{{- end }}
