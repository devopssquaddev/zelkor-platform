{{- define "zelkor-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zelkor-agent.fullname" -}}
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

{{- define "zelkor-agent.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "zelkor-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: aegra
zelkor.io/workload-type: agent
{{- end }}

{{- define "zelkor-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zelkor-agent.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: aegra
{{- end }}

{{- define "zelkor-agent.primaryGraphId" -}}
{{- $ids := .Values.graphIds | default list -}}
{{- if $ids -}}
{{- first $ids -}}
{{- else if .Values.graphId -}}
{{- .Values.graphId -}}
{{- else -}}
{{- fail "graphId or graphIds must be set (the independently released graph id(s))" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.redisPrefix" -}}
{{- $explicit := ((.Values.redis).prefix | default "") | toString | trimSuffix ":" -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- printf "aegra:%s" .Release.Name -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.redisChannelPrefix" -}}
{{- $v := ((.Values.redis).channelPrefix | default "") | toString -}}
{{- if $v -}}
{{- $v -}}
{{- else -}}
{{- printf "%s:run:" (include "zelkor-agent.redisPrefix" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.workerQueueKey" -}}
{{- $v := ((.Values.redis).queueKey | default "") | toString -}}
{{- if $v -}}
{{- $v -}}
{{- else -}}
{{- printf "%s:jobs" (include "zelkor-agent.redisPrefix" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.image" -}}
{{- $img := . -}}
{{- if and $img.digest (ne $img.digest "") -}}
{{- printf "%s@%s" $img.repository $img.digest -}}
{{- else -}}
{{- printf "%s:%s" $img.repository ($img.tag | default "1.0.0") -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.logLevel" -}}
{{- $c := .Values.logging | default dict -}}
{{- $c.level | default "INFO" | upper -}}
{{- end }}

{{- define "zelkor-agent.logFormat" -}}
{{- $c := .Values.logging | default dict -}}
{{- $c.format | default "json" | lower -}}
{{- end }}

{{- define "zelkor-agent.platformReleaseName" -}}
{{- ((.Values.platform).releaseName | default "") | toString -}}
{{- end }}

{{- define "zelkor-agent.openaiBaseUrl" -}}
{{- $explicit := ((.Values.platform).openaiBaseUrl | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "zelkor-agent.platformReleaseName" .) -}}
{{- printf "http://%s-ai-gateway:80/v1" (include "zelkor-agent.platformReleaseName" .) -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.mcpUrl" -}}
{{- $explicit := ((.Values.platform).mcpUrl | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "zelkor-agent.platformReleaseName" .) -}}
{{- printf "http://%s-mcp" (include "zelkor-agent.platformReleaseName" .) -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.sharedRouteGatewayName" -}}
{{- $sr := .Values.sharedRoute | default dict -}}
{{- $explicit := ($sr.gatewayName | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "zelkor-agent.platformReleaseName" .) -}}
{{- printf "%s-gateway" (include "zelkor-agent.platformReleaseName" .) -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.langfuseBaseUrl" -}}
{{- $explicit := ((.Values.platform).langfuseBaseUrl | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "zelkor-agent.platformReleaseName" .) -}}
{{- printf "http://%s-langfuse:3000" (include "zelkor-agent.platformReleaseName" .) -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.langfuseOtelSecretName" -}}
{{- $release := include "zelkor-agent.platformReleaseName" . -}}
{{- if $release -}}
{{- printf "%s-langfuse-otel" $release -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{/*
OTEL env. Explicit platform.langfuse* wins over envFrom of {release}-langfuse-otel.
*/}}
{{- define "zelkor-agent.langfuseEnv" -}}
{{- $url := include "zelkor-agent.langfuseBaseUrl" . -}}
{{- if $url }}
- name: OTEL_TARGETS
  value: {{ .Values.platform.otelTargets | default "LANGFUSE" | quote }}
- name: LANGFUSE_BASE_URL
  value: {{ $url | quote }}
{{- if .Values.platform.langfusePublicKey }}
- name: LANGFUSE_PUBLIC_KEY
  value: {{ .Values.platform.langfusePublicKey | quote }}
- name: LANGFUSE_SECRET_KEY
  value: {{ .Values.platform.langfuseSecretKey | quote }}
{{- end }}
{{- end }}
{{- end }}

{{- define "zelkor-agent.logEnv" -}}
- name: ZELKOR_LOG_LEVEL
  value: {{ include "zelkor-agent.logLevel" . | quote }}
- name: ZELKOR_LOG_FORMAT
  value: {{ include "zelkor-agent.logFormat" . | quote }}
- name: ZELKOR_LOG_COMPONENT
  value: "zelkor-aegra"
{{- end }}

{{- define "zelkor-agent.tenantJwksConfigMapName" -}}
{{- $auth := .Values.auth | default dict -}}
{{- $explicit := ($auth.jwksConfigMap | default "") | trim -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "zelkor-agent.platformReleaseName" .) -}}
{{- printf "%s-tenant-jwks" (include "zelkor-agent.platformReleaseName" .) -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end }}

{{- define "zelkor-agent.tenantAuthEnv" -}}
{{- $auth := .Values.auth | default dict -}}
{{- $issuer := ($auth.issuer | default "") | trim -}}
{{- $audiences := $auth.audiences | default list -}}
{{- $claims := $auth.tenantClaims | default list -}}
{{- if eq (len $claims) 0 -}}
{{- $claims = list "tenant_id" "org_id" "sub" -}}
{{- end -}}
{{- $remote := ($auth.jwksUri | default "") | trim -}}
{{- if not $issuer -}}
{{- fail "auth.issuer must be set (or set platform.releaseName and inherit from the platform contract ConfigMap)" -}}
{{- end -}}
{{- if eq (len $audiences) 0 -}}
{{- fail "auth.audiences must be a non-empty list" -}}
{{- end -}}
{{- if and (not $remote) (not (include "zelkor-agent.tenantJwksConfigMapName" .)) -}}
{{- fail "auth.jwksUri or auth.jwksConfigMap (or platform.releaseName for default JWKS ConfigMap) is required" -}}
{{- end -}}
{{- if $remote }}
- name: AUTH_JWKS_URI
  value: {{ $remote | quote }}
{{- else }}
- name: AUTH_JWKS_PATH
  value: "/etc/zelkor/tenant-jwks"
{{- end }}
- name: AUTH_JWT_ISSUER
  value: {{ $issuer | quote }}
- name: AUTH_JWT_AUDIENCES
  value: {{ $audiences | toJson | quote }}
- name: AUTH_TENANT_CLAIMS
  value: {{ $claims | toJson | quote }}
- name: TENANT_ORG_MAPPINGS
  value: {{ ($auth.orgMappings | default dict) | toJson | quote }}
{{- end }}

{{- define "zelkor-agent.tenantAuthVolumeMount" -}}
{{- $auth := .Values.auth | default dict -}}
{{- $remote := ($auth.jwksUri | default "") | trim -}}
{{- if not $remote }}
- name: tenant-jwks
  mountPath: /etc/zelkor/tenant-jwks
  readOnly: true
{{- end }}
{{- end }}

{{- define "zelkor-agent.tenantAuthVolume" -}}
{{- $auth := .Values.auth | default dict -}}
{{- $remote := ($auth.jwksUri | default "") | trim -}}
{{- $cm := include "zelkor-agent.tenantJwksConfigMapName" . | trim -}}
{{- if and (not $remote) $cm }}
- name: tenant-jwks
  configMap:
    name: {{ $cm | quote }}
{{- end }}
{{- end }}

{{/*
Render startup/liveness/readiness probes from chart values.
Usage: {{ include "zelkor-agent.containerProbes" (dict "root" . "values" .Values) | nindent 12 }}
Set a probe to null in values to omit it. Strings inside probes are tpl-evaluated against root.
*/}}
{{- define "zelkor-agent.containerProbes" -}}
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
{{- end }}
