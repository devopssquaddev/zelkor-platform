{{- $inMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "input") }}
{{- $outMode := include "zelkor-platform.nemoSelfCheckMode" (dict "root" . "side" "output") }}
{{- $sc := .Values.guardrails.nemo.selfCheck | default dict }}
{{- $timeout := $sc.timeoutMs | default 15000 | int }}
{{- $onUnavailable := $sc.onUnavailable | default "allow" | toString }}
{{- if not (has $onUnavailable (list "allow" "block")) }}
{{- fail (printf "workspace.policies.nemo.selfCheck.onUnavailable must be allow or block (got %q)" $onUnavailable) }}
{{- end }}
define bot refuse to respond
  {{ .Values.guardrails.nemo.safetyRefusal | default "I can't help with that request." | quote }}
{{- if ne $inMode "none" }}

# zelkor_self_check returns {blocked, verdict, status, mode, enforced}; blocked only in block mode.
define flow self check input
  $verdict = execute zelkor_self_check(side="input", mode="{{ $inMode }}", timeout_ms={{ $timeout }}, on_unavailable="{{ $onUnavailable }}")
  if $verdict.blocked
    bot refuse to respond
    stop
{{- end }}
{{- if ne $outMode "none" }}

define flow self check output
  $verdict = execute zelkor_self_check(side="output", mode="{{ $outMode }}", timeout_ms={{ $timeout }}, on_unavailable="{{ $onUnavailable }}")
  if $verdict.blocked
    bot refuse to respond
    stop
{{- end }}
{{- if .Values.guardrails.nemo.extraColang }}

{{ .Values.guardrails.nemo.extraColang }}
{{- end }}
