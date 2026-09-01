{{/*
Expand the name of the chart.
*/}}
{{- define "zelkor-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "zelkor-platform.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "zelkor-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "zelkor-platform.labels" -}}
helm.sh/chart: {{ include "zelkor-platform.chart" . }}
{{ include "zelkor-platform.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Identity env for Aegra and MCP. Dev token shortcuts are off unless a local overlay sets them.
*/}}
{{- define "zelkor-platform.authEnv" -}}
- name: AUTH_DEV_TOKENS_ENABLED
  value: {{ ((.Values.auth.devTokens).enabled | default false) | quote }}
- name: AUTH_DEV_TOKEN_PREFIX
  value: {{ ((.Values.auth.devTokens).prefix | default "") | quote }}
- name: AUTH_TRUST_TENANT_HEADER
  value: {{ (.Values.auth.trustTenantHeader | default false) | quote }}
- name: AUTH_JWT_SECRET
  value: {{ (.Values.auth.jwtSecret | default "") | quote }}
{{- end }}

{{/*
Aegra OTel → Langfuse. Uses in-cluster Langfuse Service DNS, not *.localhost.
Only emitted when otelTargets or init keys are set.
*/}}
{{- define "zelkor-platform.aegraOtelEnv" -}}
{{- $targets := (.Values.aegra.otelTargets | default "") | toString | trim -}}
{{- $hasKeys := and .Values.langfuse.enabled .Values.langfuse.init.projectPublicKey .Values.langfuse.init.projectSecretKey -}}
{{- if or $targets $hasKeys }}
- name: OTEL_TARGETS
  value: {{ if $targets }}{{ $targets | quote }}{{ else }}{{ "LANGFUSE" | quote }}{{ end }}
- name: LANGFUSE_BASE_URL
  value: {{ printf "http://%s-langfuse:3000" (include "zelkor-platform.fullname" .) | quote }}
{{- if $hasKeys }}
- name: LANGFUSE_PUBLIC_KEY
  value: {{ .Values.langfuse.init.projectPublicKey | quote }}
- name: LANGFUSE_SECRET_KEY
  value: {{ .Values.langfuse.init.projectSecretKey | quote }}
{{- end }}
{{- end }}
{{- end }}

{{- define "zelkor-platform.postgresPassword" -}}
{{- required "postgresql.auth.password must be set in a values overlay. The chart ships no default password." .Values.postgresql.auth.password -}}
{{- end }}

{{- define "zelkor-platform.postgresUrl" -}}
{{- $db := index . 1 -}}
{{- $root := index . 0 -}}
{{- printf "postgresql://%s:%s@%s-postgresql:5432/%s" $root.Values.postgresql.auth.username (include "zelkor-platform.postgresPassword" $root) (include "zelkor-platform.fullname" $root) $db -}}
{{- end }}

{{- define "zelkor-platform.clickhousePassword" -}}
{{- required "clickhouse.auth.password must be set in a values overlay. The chart ships no default password." .Values.clickhouse.auth.password -}}
{{- end }}

{{- define "zelkor-platform.valkeyPassword" -}}
{{- .Values.valkey.auth.password | default "" -}}
{{- end }}

{{- define "zelkor-platform.valkeyUrl" -}}
{{- $pass := include "zelkor-platform.valkeyPassword" . -}}
{{- if $pass -}}
{{- printf "redis://:%s@%s-valkey:6379/0" $pass (include "zelkor-platform.fullname" .) -}}
{{- else -}}
{{- printf "redis://%s-valkey:6379/0" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.seaweedfsAccessKey" -}}
{{- required "seaweedfs.auth.accessKey must be set in a values overlay. The chart ships no default credentials." .Values.seaweedfs.auth.accessKey -}}
{{- end }}

{{- define "zelkor-platform.seaweedfsSecretKey" -}}
{{- required "seaweedfs.auth.secretKey must be set in a values overlay. The chart ships no default credentials." .Values.seaweedfs.auth.secretKey -}}
{{- end }}

{{- define "zelkor-platform.seaweedfsEndpoint" -}}
{{- printf "http://%s-seaweedfs:8333" (include "zelkor-platform.fullname" .) -}}
{{- end }}

{{- define "zelkor-platform.langfuseS3Env" -}}
{{- $bucket := .Values.langfuse.s3.bucket | default "langfuse" -}}
{{- $region := .Values.langfuse.s3.region | default "auto" -}}
{{- $endpoint := include "zelkor-platform.seaweedfsEndpoint" . -}}
{{- $accessKey := include "zelkor-platform.seaweedfsAccessKey" . -}}
{{- $secretKey := include "zelkor-platform.seaweedfsSecretKey" . -}}
- name: LANGFUSE_S3_EVENT_UPLOAD_BUCKET
  value: {{ $bucket | quote }}
- name: LANGFUSE_S3_EVENT_UPLOAD_PREFIX
  value: "events/"
- name: LANGFUSE_S3_EVENT_UPLOAD_REGION
  value: {{ $region | quote }}
- name: LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT
  value: {{ $endpoint | quote }}
- name: LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID
  value: {{ $accessKey | quote }}
- name: LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY
  value: {{ $secretKey | quote }}
- name: LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE
  value: "true"
- name: LANGFUSE_S3_MEDIA_UPLOAD_BUCKET
  value: {{ $bucket | quote }}
- name: LANGFUSE_S3_MEDIA_UPLOAD_PREFIX
  value: "media/"
- name: LANGFUSE_S3_MEDIA_UPLOAD_REGION
  value: {{ $region | quote }}
- name: LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT
  value: {{ $endpoint | quote }}
- name: LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID
  value: {{ $accessKey | quote }}
- name: LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY
  value: {{ $secretKey | quote }}
- name: LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE
  value: "true"
{{- end }}

{{- define "zelkor-platform.langfuseCoreEnv" -}}
- name: DATABASE_URL
  value: {{ include "zelkor-platform.postgresUrl" (list . "langfuse") | quote }}
- name: CLICKHOUSE_URL
  value: {{ printf "http://%s-clickhouse:8123" (include "zelkor-platform.fullname" .) | quote }}
- name: CLICKHOUSE_MIGRATION_URL
  value: {{ printf "clickhouse://%s-clickhouse:9000/default" (include "zelkor-platform.fullname" .) | quote }}
- name: CLICKHOUSE_USER
  value: {{ .Values.clickhouse.auth.username | default "clickhouse" | quote }}
- name: CLICKHOUSE_PASSWORD
  value: {{ include "zelkor-platform.clickhousePassword" . | quote }}
- name: CLICKHOUSE_DB
  value: "default"
- name: CLICKHOUSE_CLUSTER_ENABLED
  value: "false"
- name: REDIS_HOST
  value: {{ printf "%s-valkey" (include "zelkor-platform.fullname" .) | quote }}
- name: REDIS_PORT
  value: "6379"
{{- $redisPass := include "zelkor-platform.valkeyPassword" . -}}
{{- if $redisPass }}
- name: REDIS_AUTH
  value: {{ $redisPass | quote }}
{{- end }}
- name: SALT
  valueFrom:
    secretKeyRef:
      name: {{ include "zelkor-platform.fullname" . }}-langfuse
      key: salt
- name: ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "zelkor-platform.fullname" . }}-langfuse
      key: encryption-key
- name: TELEMETRY_ENABLED
  value: "false"
- name: LANGFUSE_MIGRATION_V4_WRITE_MODE
  value: {{ .Values.langfuse.migration.v4WriteMode | default "legacy" | quote }}
- name: LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL
  value: {{ .Values.langfuse.migration.enableHistoricBackfill | default false | quote }}
- name: LANGFUSE_MIGRATION_V4_NATIVE_OTEL_BEHAVIOUR
  value: {{ .Values.langfuse.migration.nativeOtelBehaviour | default "dual_write" | quote }}
{{ include "zelkor-platform.langfuseS3Env" . }}
{{- end }}

{{- define "zelkor-platform.langfuseWaitScript" -}}
until nc -z -w 2 {{ include "zelkor-platform.fullname" . }}-postgresql 5432; do
  echo "Waiting for postgresql..."
  sleep 1
done
until nc -z -w 2 {{ include "zelkor-platform.fullname" . }}-clickhouse 8123; do
  echo "Waiting for clickhouse..."
  sleep 1
done
until nc -z -w 2 {{ include "zelkor-platform.fullname" . }}-valkey 6379; do
  echo "Waiting for valkey..."
  sleep 1
done
until nc -z -w 2 {{ include "zelkor-platform.fullname" . }}-seaweedfs 8333; do
  echo "Waiting for seaweedfs..."
  sleep 1
done
echo "Dependencies ready."
{{- end }}

{{- define "zelkor-platform.qdrantUrl" -}}
{{- $override := .Values.mcp.qdrantMCP.url | default "" -}}
{{- if $override -}}
{{- $override -}}
{{- else -}}
{{- printf "http://%s-qdrant:6333" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{/*
True when NeMo I/O intercept is active on default /v1 traffic.
Defaults to true when guardrails.nemo.enabled unless explicitly disabled.
*/}}
{{- define "zelkor-platform.nemoInterceptEnabled" -}}
{{- if not .Values.guardrails.nemo.enabled -}}
false
{{- else if hasKey (.Values.guardrails.nemo.intercept | default dict) "enabled" -}}
{{- .Values.guardrails.nemo.intercept.enabled | toString -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{/*
NeMo AIServiceBackend is required for intercept or legacy nemo/* prefix routing.
*/}}
{{- define "zelkor-platform.nemoAiGatewayBackendEnabled" -}}
{{- if not .Values.guardrails.nemo.enabled -}}
false
{{- else if eq (include "zelkor-platform.nemoInterceptEnabled" .) "true" -}}
true
{{- else -}}
{{- (.Values.guardrails.nemo.aiGatewayRoute.enabled | default false) | toString -}}
{{- end -}}
{{- end }}

{{/*
Hostnames accepted by AIGatewayRoute (external dev + in-cluster service DNS).
*/}}
{{- define "zelkor-platform.aiGatewayHostnames" -}}
{{- $hosts := list -}}
{{- if .Values.gateway.hosts.aiGateway -}}
{{- $hosts = append $hosts .Values.gateway.hosts.aiGateway -}}
{{- end -}}
{{- if .Values.aiGateway.inClusterService.enabled -}}
{{- $short := printf "%s-ai-gateway" (include "zelkor-platform.fullname" .) -}}
{{- $fqdn := printf "%s.%s.svc.cluster.local" $short .Release.Namespace -}}
{{- $hosts = append $hosts $short -}}
{{- $hosts = append $hosts $fqdn -}}
{{- end -}}
{{- $hosts | uniq | toJson -}}
{{- end }}

{{/*
OpenAI-compatible base URL for in-cluster agent runtimes (Aegra, MCP).
*/}}
{{- define "zelkor-platform.openAiBaseUrl" -}}
{{- /* Prefer *-ai-gateway Service DNS (Host matches AIGatewayRoute). internalUrl is the Envoy
     data-plane FQDN for NeMo, which sets Host: gateway.hosts.aiGateway separately. */ -}}
{{- if .Values.aiGateway.inClusterService.enabled -}}
{{- $port := .Values.aiGateway.inClusterService.port | default 80 -}}
{{- printf "http://%s-ai-gateway:%v/v1" (include "zelkor-platform.fullname" .) $port -}}
{{- else if .Values.aiGateway.internalUrl -}}
{{- .Values.aiGateway.internalUrl -}}
{{- else -}}
{{- printf "http://%s-ai-gateway:8080/v1" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.mcpGatewayUrl" -}}
{{- printf "http://%s-mcp-gateway:8080" (include "zelkor-platform.fullname" .) -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayInternalUrl" -}}
{{- $override := .Values.aiGateway.internalUrl | default "" -}}
{{- if not $override -}}
{{- $override = .Values.mcp.qdrantMCP.aiGatewayUrl | default "" -}}
{{- end -}}
{{- if $override -}}
{{- $override -}}
{{- else -}}
{{- $ns := "envoy-gateway-system" -}}
{{- $found := "" -}}
{{- range (lookup "v1" "Service" $ns "").items -}}
{{- if and (not $found) (hasPrefix "envoy-default-" .metadata.name) (contains "gateway-" .metadata.name) -}}
{{- $found = printf "http://%s.%s.svc.cluster.local:80/v1" .metadata.name $ns -}}
{{- end -}}
{{- end -}}
{{- if $found -}}
{{- $found -}}
{{- else -}}
{{- printf "http://envoy-default-%s-gateway.%s.svc.cluster.local:80/v1" (include "zelkor-platform.fullname" .) $ns -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.nemoOtelEnabled" -}}
{{- if and .Values.guardrails.nemo.observability.otel.enabled .Values.langfuse.enabled .Values.langfuse.init.projectPublicKey .Values.langfuse.init.projectSecretKey -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.nemoOtelEnv" -}}
{{- if eq (include "zelkor-platform.nemoOtelEnabled" .) "true" }}
- name: OTEL_SERVICE_NAME
  value: {{ printf "%s-nemo" (include "zelkor-platform.fullname" .) | quote }}
- name: OTEL_TRACES_EXPORTER
  value: otlp
- name: OTEL_METRICS_EXPORTER
  value: none
- name: OTEL_LOGS_EXPORTER
  value: none
- name: OTEL_EXPORTER_OTLP_PROTOCOL
  value: http/protobuf
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ printf "http://%s-langfuse:3000/api/public/otel" (include "zelkor-platform.fullname" .) | quote }}
- name: OTEL_EXPORTER_OTLP_HEADERS
  value: {{ printf "Authorization=Basic %s" (b64enc (printf "%s:%s" .Values.langfuse.init.projectPublicKey .Values.langfuse.init.projectSecretKey)) | quote }}
- name: OTEL_PYTHON_FASTAPI_EXCLUDED_URLS
  value: "/v1/health"
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "zelkor-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zelkor-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Render a container image from {repository, tag, digest}. Digest wins when set.
Usage: {{ include "zelkor-platform.image" .Values.aegra.image }}
*/}}
{{- define "zelkor-platform.image" -}}
{{- $img := . -}}
{{- if and $img.digest (ne $img.digest "") -}}
{{- printf "%s@%s" $img.repository $img.digest -}}
{{- else -}}
{{- printf "%s:%s" $img.repository ($img.tag | default "dev") -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.imagePullPolicy" -}}
{{- $img := .image | default dict -}}
{{- $root := .root -}}
{{- $img.pullPolicy | default $root.Values.global.imagePullPolicy | default "IfNotPresent" -}}
{{- end }}

{{- define "zelkor-platform.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Render startup/liveness/readiness probes and resources from a component values object.
Usage: {{ include "zelkor-platform.containerProbes" (dict "root" . "values" .Values.aegra) | nindent 10 }}
Set a probe to null in values to omit it. Strings inside probes are tpl-evaluated against root.
*/}}
{{- define "zelkor-platform.containerProbes" -}}
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

