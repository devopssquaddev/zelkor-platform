{{/*
FinServe chart helpers
*/}}
{{- define "finserve.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "finserve.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "finserve.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "finserve.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "finserve.image" -}}
{{- $img := . -}}
{{- if and $img.digest (ne $img.digest "") -}}
{{- printf "%s@%s" $img.repository $img.digest -}}
{{- else -}}
{{- printf "%s:%s" $img.repository ($img.tag | default "dev") -}}
{{- end -}}
{{- end }}

{{- define "finserve.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Resolve in-cluster Envoy AI Gateway /v1 base URL.
Envoy Gateway publishes a hashed Service in envoy-gateway-system; discover at helm upgrade time.
*/}}
{{- define "finserve.aiGatewayUrl" -}}
{{- $fallback := .Values.platform.aiGatewayUrl -}}
{{- if .Values.platform.aiGatewayAutoDiscover | default true -}}
{{- $ns := .Values.platform.aiGatewayNamespace | default "envoy-gateway-system" -}}
{{- $found := "" -}}
{{- range (lookup "v1" "Service" $ns "").items -}}
{{- if and (not $found) (hasPrefix "envoy-default-" .metadata.name) (contains "gateway-" .metadata.name) -}}
{{- $found = printf "http://%s.%s.svc.cluster.local:80/v1" .metadata.name $ns -}}
{{- end -}}
{{- end -}}
{{- if $found -}}
{{- $found -}}
{{- else -}}
{{- $fallback -}}
{{- end -}}
{{- else -}}
{{- $fallback -}}
{{- end -}}
{{- end -}}

{{/*
Render startup/liveness/readiness probes and resources.
Usage: {{ include "finserve.containerProbes" (dict "root" . "values" .Values.agent) | nindent 10 }}
*/}}
{{- define "finserve.containerProbes" -}}
{{- $root := .root -}}
{{- $v := .values -}}
{{- with $v.startupProbe }}
startupProbe:
  {{- tpl (toYaml .) $root | nindent 2 }}
{{- end }}
{{- with $v.livenessProbe }}
livenessProbe:
  {{- tpl (toYaml .) $root | nindent 2 }}
{{- end }}
{{- with $v.readinessProbe }}
readinessProbe:
  {{- tpl (toYaml .) $root | nindent 2 }}
{{- end }}
{{- with $v.resources }}
resources:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

