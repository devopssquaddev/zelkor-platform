{{/*
Legal-redline chart helpers (seed Job). The agent Deployment comes from zelkor-agent.
*/}}
{{- define "legal-redline.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "legal-redline.fullname" -}}
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

{{- define "legal-redline.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "legal-redline.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "legal-redline.platformReleaseName" -}}
{{- ((.Values.platform).releaseName | default "") | toString -}}
{{- end }}

{{- define "legal-redline.qdrantHost" -}}
{{- $explicit := ((.Values.platform).qdrantHost | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "legal-redline.platformReleaseName" .) -}}
{{- printf "%s-qdrant" (include "legal-redline.platformReleaseName" .) -}}
{{- else -}}
{{- required "platform.qdrantHost or platform.releaseName must be set" .Values.platform.qdrantHost -}}
{{- end -}}
{{- end }}

{{- define "legal-redline.qdrantUrl" -}}
{{- $explicit := ((.Values.platform).qdrantUrl | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- printf "http://%s:%v" (include "legal-redline.qdrantHost" .) ((.Values.platform).qdrantPort | default 6333) -}}
{{- end -}}
{{- end }}

{{- define "legal-redline.objectEndpoint" -}}
{{- $explicit := ((.Values.objectStore).endpoint | default "") | toString -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else if (include "legal-redline.platformReleaseName" .) -}}
{{- printf "http://%s-seaweedfs:8333" (include "legal-redline.platformReleaseName" .) -}}
{{- else -}}
{{- required "objectStore.endpoint or platform.releaseName must be set" .Values.objectStore.endpoint -}}
{{- end -}}
{{- end }}

{{- define "legal-redline.image" -}}
{{- $img := ((.Values.legalRedline).image | default dict) -}}
{{- $repo := $img.repository | default "ghcr.io/devopssquaddev/zelkor-example-legal-redline" -}}
{{- $tag := $img.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end }}
