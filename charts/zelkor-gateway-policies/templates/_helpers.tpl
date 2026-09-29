{{- define "zelkor-gateway-policies.listenerPort" -}}
{{- $p := . -}}
{{- if kindIs "map" . -}}
{{- $p = .port -}}
{{- end -}}
{{- int $p -}}
{{- end -}}

{{- define "zelkor-gateway-policies.containerPort" -}}
{{- $p := int . -}}
{{- if lt $p 1024 -}}
{{- add $p 10000 -}}
{{- else -}}
{{- $p -}}
{{- end -}}
{{- end -}}
