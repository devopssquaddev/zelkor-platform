{{- $inMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "input") }}
{{- $outMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "output") }}
{{- $timeout := (.Values.guardrails.nemo.selfCheck | default dict).timeoutMs | default 1500 | int }}
define bot refuse to respond
  {{ .Values.guardrails.nemo.safetyRefusal | default "I can't help with that request." | quote }}
{{- if ne $inMode "none" }}

# zelkor_self_check returns {blocked, verdict, status}; blocked is true only in block mode.
define flow self check input
  $verdict = execute zelkor_self_check(side="input", mode="{{ $inMode }}", timeout_ms={{ $timeout }})
  if $verdict.blocked
    bot refuse to respond
    stop
{{- end }}
{{- if ne $outMode "none" }}

define flow self check output
  $verdict = execute zelkor_self_check(side="output", mode="{{ $outMode }}", timeout_ms={{ $timeout }})
  if $verdict.blocked
    bot refuse to respond
    stop
{{- end }}
{{- if .Values.guardrails.nemo.extraColang }}

{{ .Values.guardrails.nemo.extraColang }}
{{- end }}
