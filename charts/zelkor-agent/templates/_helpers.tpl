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
{{- printf "%s:%s" $img.repository ($img.tag | default "dev") -}}
{{- end -}}
{{- end }}
