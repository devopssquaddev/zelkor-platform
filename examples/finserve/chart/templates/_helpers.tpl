{{/*
FinServe chart helpers (jobs and optional HTTPRoute).
The agent Deployment comes from the zelkor-agent subchart.
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

{{- define "finserve.platformReleaseName" -}}
{{- ((.Values.platform).releaseName | default "") | toString -}}
{{- end }}

{{- define "finserve.postgresHost" -}}
{{- $explicit := ((.Values.platform).postgresHost | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (.Values.platform).cnpgClusterName -}}
{{- printf "%s-rw" .Values.platform.cnpgClusterName -}}
{{- else if (include "finserve.platformReleaseName" .) -}}
{{- printf "%s-postgresql" (include "finserve.platformReleaseName" .) -}}
{{- else -}}
{{- required "platform.postgresHost, platform.cnpgClusterName, or platform.releaseName must be set" .Values.platform.postgresHost -}}
{{- end -}}
{{- end }}

{{- define "finserve.qdrantHost" -}}
{{- $explicit := ((.Values.platform).qdrantHost | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "finserve.platformReleaseName" .) -}}
{{- printf "%s-qdrant" (include "finserve.platformReleaseName" .) -}}
{{- else -}}
{{- required "platform.qdrantHost or platform.releaseName must be set" .Values.platform.qdrantHost -}}
{{- end -}}
{{- end }}

{{- define "finserve.qdrantUrl" -}}
{{- $explicit := ((.Values.platform).qdrantUrl | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- printf "http://%s:%v" (include "finserve.qdrantHost" .) ((.Values.platform).qdrantPort | default 6333) -}}
{{- end -}}
{{- end }}

{{- define "finserve.langfuseHost" -}}
{{- $explicit := ((.Values.platform).langfuseHost | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "finserve.platformReleaseName" .) -}}
{{- printf "http://%s-langfuse:3000" (include "finserve.platformReleaseName" .) -}}
{{- else -}}
{{- required "platform.langfuseHost or platform.releaseName must be set when langfuseSeed.enabled" .Values.platform.langfuseHost -}}
{{- end -}}
{{- end }}

{{- define "finserve.gatewayName" -}}
{{- $explicit := ((.Values.gateway).gatewayName | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "finserve.platformReleaseName" .) -}}
{{- printf "%s-gateway" (include "finserve.platformReleaseName" .) -}}
{{- else -}}
{{- required "gateway.gatewayName or platform.releaseName must be set when gateway.enabled" .Values.gateway.gatewayName -}}
{{- end -}}
{{- end }}

{{- define "finserve.gatewayNamespace" -}}
{{- $explicit := ((.Values.gateway).namespace | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- .Release.Namespace -}}
{{- end -}}
{{- end }}
