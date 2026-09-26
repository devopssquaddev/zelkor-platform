{{/*
V2 compiler: map platform.* / workspace.* / workload.* onto the internal flat tree used by templates.
Idempotent; call via include "zelkor-platform.compile" . at the top of each template file.
*/}}
{{- define "zelkor-platform.compile" -}}
{{- if not (hasKey .Values "__compiled") -}}
{{- if hasKey .Values "aiGateway" -}}
{{- fail "aiGateway.* was removed in V2. Declare models under workspace.models. See docs/adding-llm-providers-and-models.md." -}}
{{- end -}}
{{- if hasKey .Values "auth" -}}
{{- fail "auth.* was removed in V2. Declare tenants under platform.tenants. See docs/helm-install.md." -}}
{{- end -}}
{{- if hasKey .Values "langfuse" -}}
{{- fail "langfuse.* was removed in V2. Declare observability under platform.telemetry.langfuse. See docs/helm-install.md." -}}
{{- end -}}
{{- if hasKey .Values "aegra" -}}
{{- fail "aegra.* was removed in V2. Declare agents under workload.agents. See docs/agent-deploy.md." -}}
{{- end -}}
{{- if hasKey .Values "guardrails" -}}
{{- fail "guardrails.* was removed in V2. Declare policies under workspace.policies. See docs/helm-install.md." -}}
{{- end -}}
{{- if hasKey .Values "mcp" -}}
{{- fail "mcp.* was removed in V2. Declare tools under workspace.tools. See docs/helm-install.md." -}}
{{- end -}}
{{- if hasKey .Values "logging" -}}
{{- fail "logging.* was removed in V2. Declare telemetry under platform.telemetry (level/format). See docs/helm-install.md." -}}
{{- end -}}
{{- $_ := set .Values "__compiled" true -}}
{{- include "zelkor-platform.compile.telemetry" . -}}
{{- include "zelkor-platform.compile.tenants" . -}}
{{- include "zelkor-platform.compile.models" . -}}
{{- include "zelkor-platform.compile.policies" . -}}
{{- include "zelkor-platform.compile.tools" . -}}
{{- include "zelkor-platform.compile.workload" . -}}
{{- include "zelkor-platform.compile.intent" . -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.telemetry" -}}
{{- $p := .Values.platform | default dict -}}
{{- $tel := $p.telemetry | default dict -}}
{{- $_ := set .Values "logging" (dict "level" ($tel.level | default "INFO") "format" ($tel.format | default "json")) -}}
{{- if $tel.langfuse -}}
{{- $_ := set .Values "langfuse" $tel.langfuse -}}
{{- end -}}
{{- $agents := (.Values.workload.agents | default dict) -}}
{{- if $tel.aegraOtelTargets -}}
{{- $_ := set $agents "otelTargets" $tel.aegraOtelTargets -}}
{{- $_ := set .Values.workload "agents" $agents -}}
{{- end -}}
{{- $no := $tel.nemoOtel | default dict -}}
{{- if or $no.enabled $no.captureContent -}}
{{- $pol := (.Values.workspace.policies | default dict) -}}
{{- $nemo := $pol.nemo | default dict -}}
{{- $obs := $nemo.observability | default dict -}}
{{- $_ := set $obs "otel" (dict "enabled" ($no.enabled | default false) "captureContent" ($no.captureContent | default false)) -}}
{{- $_ := set $nemo "observability" $obs -}}
{{- $_ := set $pol "nemo" $nemo -}}
{{- $_ := set .Values.workspace "policies" $pol -}}
{{- end -}}
{{- if $p.mTLS -}}
{{- $sec := .Values.security | default dict -}}
{{- $_ := set $sec "mTLS" $p.mTLS -}}
{{- $_ := set .Values "security" $sec -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.tenants" -}}
{{- $t := (.Values.platform.tenants | default dict) -}}
{{- $_ := set .Values "auth" (dict "sso" ($t.sso | default dict) "jwtSecret" ($t.jwtSecret | default "") "devTokens" ($t.devTokens | default dict) "trustTenantHeader" ($t.trustTenantHeader | default false)) -}}
{{- $agents := (.Values.workload.agents | default dict) -}}
{{- if $t.orgMappings -}}
{{- $_ := set $agents "tenantOrgMappings" $t.orgMappings -}}
{{- else -}}
{{- $_ := set $agents "tenantOrgMappings" ($agents.tenantOrgMappings | default dict) -}}
{{- end -}}
{{- $_ := set .Values.workload "agents" $agents -}}
{{- end }}

{{- define "zelkor-platform.compile.models" -}}
{{- $m := (.Values.workspace.models | default dict) -}}
{{- if $m -}}
{{- $_ := set .Values "aiGateway" $m -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.policies" -}}
{{- $pol := (.Values.workspace.policies | default dict) -}}
{{- if $pol -}}
{{- $_ := set .Values "guardrails" $pol -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.tools" -}}
{{- $tools := (.Values.workspace.tools | default dict) -}}
{{- if $tools -}}
{{- $_ := set .Values "mcp" $tools -}}
{{- end -}}
{{- include "zelkor-platform.compile.mcpExtraBackends" . -}}
{{- end }}

{{- define "zelkor-platform.compile.workload" -}}
{{- $agents := (.Values.workload.agents | default dict) -}}
{{- if $agents -}}
{{- $_ := set .Values "aegra" $agents -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.intent" -}}
{{- $intent := (.Values.workload.intent | default dict) -}}
{{- $_ := set .Values "__workloadIntent" $intent -}}
{{- end }}

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
Common labels. Pass (dict "root" . "intent" "postgresql") to set zelkor.io/intent; plain . omits intent.
*/}}
{{- define "zelkor-platform.labels" -}}
{{- $root := . -}}
{{- $intent := "" -}}
{{- if kindIs "map" . -}}
{{- if hasKey . "root" -}}{{- $root = .root -}}{{- end -}}
{{- if hasKey . "intent" -}}{{- $intent = .intent -}}{{- end -}}
{{- end -}}
helm.sh/chart: {{ include "zelkor-platform.chart" $root }}
{{ include "zelkor-platform.selectorLabels" $root }}
{{- if $root.Chart.AppVersion }}
app.kubernetes.io/version: {{ $root.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ $root.Release.Service }}
{{- if $intent }}
zelkor.io/intent: {{ $intent | quote }}
{{- end }}
{{- end }}

{{/*
Tier gate: true when umbrella listed entitlement suppresses a CE reserved-key fail.
*/}}
{{- define "zelkor-platform.hasEntitlement" -}}
{{- $name := .name -}}
{{- $ents := list -}}
{{- if and .Values.global.zelkor (kindIs "map" .Values.global.zelkor) .Values.global.zelkor.entitlements -}}
{{- $ents = .Values.global.zelkor.entitlements -}}
{{- end -}}
{{- if has $name $ents -}}true{{- else -}}false{{- end -}}
{{- end }}

{{/*
Process log level. Per-workload <component>.logging.level overrides logging.level.
*/}}
{{- define "zelkor-platform.logLevel" -}}
{{- $root := .root -}}
{{- $c := .component | default dict -}}
{{- if not (kindIs "map" $c) -}}
{{- $c = dict -}}
{{- end -}}
{{- $cl := $c.logging | default dict -}}
{{- $gl := $root.Values.logging | default dict -}}
{{- $cl.level | default $gl.level | default "INFO" | upper -}}
{{- end }}

{{- define "zelkor-platform.logFormat" -}}
{{- $root := .root -}}
{{- $c := .component | default dict -}}
{{- if not (kindIs "map" $c) -}}
{{- $c = dict -}}
{{- end -}}
{{- $cl := $c.logging | default dict -}}
{{- $gl := $root.Values.logging | default dict -}}
{{- $cl.format | default $gl.format | default "json" | lower -}}
{{- end }}

{{/*
ZELKOR_LOG_* for first-party containers.
Usage: {{ include "zelkor-platform.logEnv" (dict "root" . "component" .Values.aegra "name" "zelkor-aegra") }}
*/}}
{{- define "zelkor-platform.logEnv" -}}
- name: ZELKOR_LOG_LEVEL
  value: {{ include "zelkor-platform.logLevel" . | quote }}
- name: ZELKOR_LOG_FORMAT
  value: {{ include "zelkor-platform.logFormat" . | quote }}
{{- if .name }}
- name: ZELKOR_LOG_COMPONENT
  value: {{ .name | quote }}
{{- end }}
{{- end }}

{{/*
Map platform logging.level onto a vendor knob.
vendor: langfuse | postgres | qdrant | valkey | envoy | clickhouse | seaweedfs
*/}}
{{- define "zelkor-platform.vendorLogLevel" -}}
{{- $level := include "zelkor-platform.logLevel" (dict "root" .root "component" (.component | default dict)) -}}
{{- $v := .vendor -}}
{{- if eq $v "postgres" -}}
{{- if eq $level "DEBUG" }}debug1{{ else if eq $level "INFO" }}info{{ else if eq $level "WARNING" }}warning{{ else if eq $level "ERROR" }}error{{ else }}fatal{{ end -}}
{{- else if eq $v "qdrant" -}}
{{- if eq $level "WARNING" }}WARN{{ else if eq $level "CRITICAL" }}ERROR{{ else }}{{ $level }}{{ end -}}
{{- else if eq $v "langfuse" -}}
{{- if eq $level "WARNING" }}warn{{ else if eq $level "CRITICAL" }}error{{ else }}{{ $level | lower }}{{ end -}}
{{- else if eq $v "valkey" -}}
{{- if eq $level "DEBUG" }}verbose{{ else if eq $level "INFO" }}notice{{ else }}warning{{ end -}}
{{- else if eq $v "envoy" -}}
{{- if eq $level "WARNING" }}warn{{ else if eq $level "CRITICAL" }}error{{ else }}{{ $level | lower }}{{ end -}}
{{- else if eq $v "clickhouse" -}}
{{- if eq $level "DEBUG" }}debug{{ else if eq $level "INFO" }}information{{ else if eq $level "WARNING" }}warning{{ else if eq $level "ERROR" }}error{{ else }}fatal{{ end -}}
{{- else if eq $v "seaweedfs" -}}
{{- if eq $level "DEBUG" }}2{{ else }}0{{ end -}}
{{- else -}}
{{- $level | lower -}}
{{- end -}}
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
- name: TENANT_ORG_MAPPINGS
  value: {{ .Values.aegra.tenantOrgMappings | default dict | toJson | quote }}
{{- end }}

{{/*
Aegra OTel → Langfuse. When langfuse.init is enabled, envFrom {release}-langfuse-otel supplies OTEL_TARGETS and LANGFUSE_*.
Optional aegra.otelTargets overrides OTEL_TARGETS when set.
*/}}
{{- define "zelkor-platform.aegraOtelEnv" -}}
{{- $targets := (.Values.aegra.otelTargets | default "") | toString | trim -}}
{{- if $targets }}
- name: OTEL_TARGETS
  value: {{ $targets | quote }}
{{- end }}
{{- end }}

{{- define "zelkor-platform.aegraLangfuseOtelEnvFrom" -}}
{{- $init := .Values.langfuse.init | default dict -}}
{{- if and .Values.langfuse.enabled $init.enabled }}
- secretRef:
    name: {{ include "zelkor-platform.langfuseOtelSecretName" . }}
{{- end }}
{{- end }}

{{- define "zelkor-platform.dbMode" -}}
{{- .Values.databases.mode | default "in-cluster-basic" -}}
{{- end }}

{{- define "zelkor-platform.postgresPassword" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- $ext := ((.Values.databases.postgresql).external) | default dict -}}
{{- if and (eq $mode "external") $ext.password -}}
{{- $ext.password -}}
{{- else -}}
{{- required "postgresql.auth.password must be set in a values overlay. The chart ships no default password." .Values.postgresql.auth.password -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.postgresHost" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- required "databases.postgresql.external.host must be set when databases.mode is external" ((.Values.databases.postgresql).external).host -}}
{{- else -}}
{{- printf "%s-postgresql" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.postgresPort" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- $p := ((.Values.databases.postgresql).external).port | default 5432 -}}
{{- $p -}}
{{- else -}}
5432
{{- end -}}
{{- end }}

{{- define "zelkor-platform.postgresUrl" -}}
{{- $db := index . 1 -}}
{{- $root := index . 0 -}}
{{- $mode := include "zelkor-platform.dbMode" $root -}}
{{- $user := $root.Values.postgresql.auth.username -}}
{{- $ext := (($root.Values.databases.postgresql).external) | default dict -}}
{{- if and (eq $mode "external") $ext.username -}}
{{- $user = $ext.username -}}
{{- end -}}
{{- $pass := include "zelkor-platform.postgresPassword" $root | urlquery -}}
{{- printf "postgresql://%s:%s@%s:%v/%s" $user $pass (include "zelkor-platform.postgresHost" $root) (include "zelkor-platform.postgresPort" $root) $db -}}
{{- end }}

{{- define "zelkor-platform.clickhousePassword" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- $ext := ((.Values.databases.clickhouse).external) | default dict -}}
{{- if and (eq $mode "external") $ext.password -}}
{{- $ext.password -}}
{{- else -}}
{{- required "clickhouse.auth.password must be set in a values overlay. The chart ships no default password." .Values.clickhouse.auth.password -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.clickhouseClientNetworks" -}}
{{- $nets := ((.Values.databases.clickhouse).clientNetworks) | default list -}}
{{- if $nets -}}
{{- range $nets }}
        - {{ . | quote }}
{{- end }}
{{- else }}
        - "10.0.0.0/8"
        - "172.16.0.0/12"
        - "192.168.0.0/16"
{{- end }}
{{- end }}

{{- define "zelkor-platform.clickhouseHost" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- required "databases.clickhouse.external.host must be set when databases.mode is external" ((.Values.databases.clickhouse).external).host -}}
{{- else -}}
{{- printf "%s-clickhouse" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.clickhouseHttpPort" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- ((.Values.databases.clickhouse).external).httpPort | default 8123 -}}
{{- else -}}
8123
{{- end -}}
{{- end }}

{{- define "zelkor-platform.clickhouseNativePort" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- ((.Values.databases.clickhouse).external).nativePort | default 9000 -}}
{{- else -}}
9000
{{- end -}}
{{- end }}

{{- define "zelkor-platform.valkeyPassword" -}}
{{- .Values.valkey.auth.password | default "" -}}
{{- end }}

{{- define "zelkor-platform.valkeyHost" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- required "databases.valkey.external.host must be set when databases.mode is external" ((.Values.databases.valkey).external).host -}}
{{- else -}}
{{- printf "%s-valkey" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.valkeyPort" -}}
{{- $mode := include "zelkor-platform.dbMode" . -}}
{{- if eq $mode "external" -}}
{{- ((.Values.databases.valkey).external).port | default 6379 -}}
{{- else -}}
6379
{{- end -}}
{{- end }}

{{- define "zelkor-platform.valkeyUrl" -}}
{{- $pass := include "zelkor-platform.valkeyPassword" . -}}
{{- $host := include "zelkor-platform.valkeyHost" . -}}
{{- $port := include "zelkor-platform.valkeyPort" . -}}
{{- if $pass -}}
{{- printf "redis://:%s@%s:%v/0" $pass $host $port -}}
{{- else -}}
{{- printf "redis://%s:%v/0" $host $port -}}
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
  value: {{ printf "http://%s:%v" (include "zelkor-platform.clickhouseHost" .) (include "zelkor-platform.clickhouseHttpPort" .) | quote }}
- name: CLICKHOUSE_MIGRATION_URL
  value: {{ printf "clickhouse://%s:%v/default" (include "zelkor-platform.clickhouseHost" .) (include "zelkor-platform.clickhouseNativePort" .) | quote }}
- name: CLICKHOUSE_USER
  value: {{ .Values.clickhouse.auth.username | default "clickhouse" | quote }}
- name: CLICKHOUSE_PASSWORD
  value: {{ include "zelkor-platform.clickhousePassword" . | quote }}
- name: CLICKHOUSE_DB
  value: "default"
- name: CLICKHOUSE_CLUSTER_ENABLED
  value: "false"
- name: REDIS_HOST
  value: {{ include "zelkor-platform.valkeyHost" . | quote }}
- name: REDIS_PORT
  value: {{ include "zelkor-platform.valkeyPort" . | quote }}
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
  value: {{ .Values.langfuse.migration.v4WriteMode | default "events_only" | quote }}
{{- $surfaces := .Values.langfuse.surfaces | default dict }}
{{- $llmConn := $surfaces.llmConnection | default dict }}
{{- if $llmConn.enabled }}
- name: LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST
  value: {{ printf "%s-ai-gateway,%s-ai-gateway.%s.svc.cluster.local" (include "zelkor-platform.fullname" .) (include "zelkor-platform.fullname" .) .Release.Namespace | quote }}
{{- end }}
- name: LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL
  value: {{ .Values.langfuse.migration.enableHistoricBackfill | default false | quote }}
- name: LANGFUSE_MIGRATION_V4_NATIVE_OTEL_BEHAVIOUR
  value: {{ .Values.langfuse.migration.nativeOtelBehaviour | default "direct" | quote }}
- name: LANGFUSE_MIGRATION_V4_ALLOW_PREVIEW_OPT_IN
  value: {{ .Values.langfuse.migration.allowPreviewOptIn | default true | quote }}
- name: LANGFUSE_LOG_LEVEL
  value: {{ include "zelkor-platform.vendorLogLevel" (dict "root" . "component" .Values.langfuse "vendor" "langfuse") | quote }}
{{ include "zelkor-platform.langfuseS3Env" . }}
{{- end }}

{{- define "zelkor-platform.langfuseWaitScript" -}}
until nc -z -w 2 {{ include "zelkor-platform.postgresHost" . }} {{ include "zelkor-platform.postgresPort" . }}; do
  echo "Waiting for postgresql..."
  sleep 1
done
until nc -z -w 2 {{ include "zelkor-platform.clickhouseHost" . }} {{ include "zelkor-platform.clickhouseHttpPort" . }}; do
  echo "Waiting for clickhouse..."
  sleep 1
done
until nc -z -w 2 {{ include "zelkor-platform.valkeyHost" . }} {{ include "zelkor-platform.valkeyPort" . }}; do
  echo "Waiting for valkey..."
  sleep 1
done
{{- if and .Values.seaweedfs.enabled .Values.langfuse.enabled }}
until nc -z -w 2 {{ include "zelkor-platform.fullname" . }}-seaweedfs 8333; do
  echo "Waiting for seaweedfs..."
  sleep 1
done
{{- end }}
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
LLM self-check I/O rails on content_safety (Yes/No completions via the gateway).
Chart default true. false omits those flows; intercept and extra* overlays remain.
*/}}
{{- define "zelkor-platform.nemoSelfCheckEnabled" -}}
{{- $sc := .Values.guardrails.nemo.selfCheck | default dict -}}
{{- if hasKey $sc "enabled" -}}
{{- $sc.enabled | toString -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{/*
Default model id from enabled providers. Matches scripts/lib/cluster-install.sh DEFAULT_LLM_MODEL precedence.
*/}}
{{- define "zelkor-platform.aiGatewayDerivedDefaultModel" -}}
{{- $p := .Values.aiGateway.providers | default dict -}}
{{- if $p.openai.apiKey -}}
openai/gpt-4o-mini
{{- else if $p.ollamaCloud.apiKey -}}
gpt-oss:20b
{{- else if $p.ollamaLocal.host -}}
ollama/llama3.2
{{- else if $p.anthropic.apiKey -}}
anthropic/claude-3-5-sonnet
{{- else if $p.gemini.apiKey -}}
gemini/gemini-2.0-flash
{{- else if $p.vllm.backendUrl -}}
vllm/default
{{- else if eq (include "zelkor-platform.aiGatewayAzureEnabled" .) "true" -}}
azure/gpt-4o-mini
{{- else if eq (include "zelkor-platform.aiGatewayBedrockEnabled" .) "true" -}}
bedrock/amazon.titan-text-lite-v1
{{- else if eq (include "zelkor-platform.aiGatewayVertexEnabled" .) "true" -}}
vertex/gemini-2.0-flash
{{- else if eq (include "zelkor-platform.aiGatewayCohereEnabled" .) "true" -}}
cohere/command-r
{{- end -}}
{{- end }}

{{/*
Pinned NeMo main/self-check model: nemo.model, aiGateway.defaultModel, provider-derived, else openai/gpt-4o-mini.
Request model injects onto type=main only at runtime and must not change this.
*/}}
{{- define "zelkor-platform.nemoEffectiveModel" -}}
{{- $explicit := .Values.guardrails.nemo.model | default "" -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- $default := .Values.aiGateway.defaultModel | default "" -}}
{{- if $default -}}
{{- $default -}}
{{- else -}}
{{- $derived := include "zelkor-platform.aiGatewayDerivedDefaultModel" . -}}
{{- if $derived -}}
{{- $derived -}}
{{- else -}}
openai/gpt-4o-mini
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Model id for self-check Yes/No rails. selfCheck.model, else nemoEffectiveModel.
*/}}
{{- define "zelkor-platform.nemoSelfCheckModel" -}}
{{- $sc := .Values.guardrails.nemo.selfCheck | default dict -}}
{{- $explicit := $sc.model | default "" -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- include "zelkor-platform.nemoEffectiveModel" . -}}
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
Public Agent Protocol hostname. Prefer gateway.hosts.agents (product-neutral).
gateway.hosts.aegra is a one-upgrade fallback for existing overlays.
*/}}
{{- define "zelkor-platform.agentsHost" -}}
{{- $h := "" -}}
{{- if and (hasKey .Values.gateway "hosts") (hasKey .Values.gateway.hosts "agents") -}}
{{- $h = .Values.gateway.hosts.agents | default "" -}}
{{- end -}}
{{- if and (not $h) (hasKey .Values.gateway "hosts") (hasKey .Values.gateway.hosts "aegra") -}}
{{- $h = .Values.gateway.hosts.aegra | default "" -}}
{{- end -}}
{{- $h -}}
{{- end }}

{{/*
Helm `default` treats false as empty. Use hasKey for create* flags.
*/}}
{{- define "zelkor-platform.gatewayCreateGatewayClass" -}}
{{- if hasKey .Values.gateway "createGatewayClass" -}}
{{- .Values.gateway.createGatewayClass -}}
{{- else -}}
true
{{- end -}}
{{- end }}
{{- define "zelkor-platform.gatewayCreateGateway" -}}
{{- if hasKey .Values.gateway "createGateway" -}}
{{- .Values.gateway.createGateway -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gatewayClassName" -}}
{{- .Values.gateway.gatewayClassName | default "eg" -}}
{{- end }}

{{- define "zelkor-platform.envoyDataplaneServiceName" -}}
{{- $ep := .Values.gateway.envoyProxy | default dict -}}
{{- $svc := $ep.service | default dict -}}
{{- $explicit := $svc.name | default "" -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- printf "%s-%s-dataplane" .Release.Namespace (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.envoyDataplaneHost" -}}
{{- $override := ((.Values.aiGateway.inClusterService).targetHost) | default "" -}}
{{- if $override -}}
{{- $override -}}
{{- else if eq (include "zelkor-platform.envoyProxyEmit" . | trim) "true" -}}
{{- printf "%s.envoy-gateway-system.svc.cluster.local" (include "zelkor-platform.envoyDataplaneServiceName" .) -}}
{{- end -}}
{{- end }}

{{/*
parentRefs target: overlay gateway.parentRef or this release's Gateway.
*/}}
{{- define "zelkor-platform.gatewayParentRef" -}}
{{- $pr := .Values.gateway.parentRef | default dict -}}
{{- $name := $pr.name | default "" -}}
{{- if not $name -}}
{{- $name = printf "%s-gateway" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- $ns := $pr.namespace | default "" -}}
{{- if not $ns -}}
{{- $ns = .Release.Namespace -}}
{{- end -}}
- group: gateway.networking.k8s.io
  kind: Gateway
  name: {{ $name | quote }}
  namespace: {{ $ns | quote }}
{{- with $pr.sectionName }}
  sectionName: {{ . | quote }}
{{- end }}
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
{{- /* Same Host as AIGatewayRoute (*-ai-gateway). Envoy dataplane FQDN 404s. */ -}}
{{- if .Values.aiGateway.inClusterService.enabled -}}
{{- $port := .Values.aiGateway.inClusterService.port | default 80 -}}
{{- printf "http://%s-ai-gateway:%v/v1" (include "zelkor-platform.fullname" .) $port -}}
{{- else -}}
{{- $override := .Values.aiGateway.internalUrl | default "" -}}
{{- if not $override -}}
{{- $override = .Values.mcp.qdrantMCP.aiGatewayUrl | default "" -}}
{{- end -}}
{{- if $override -}}
{{- $override -}}
{{- else -}}
{{- printf "http://%s:80/v1" (include "zelkor-platform.envoyDataplaneHost" .) -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.nemoOtelEnabled" -}}
{{- $init := .Values.langfuse.init | default dict -}}
{{- if and .Values.guardrails.nemo.observability.otel.enabled .Values.langfuse.enabled $init.enabled -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{/*
Resolved Langfuse ingest keys for init project (values, BYO secret, or cluster init secret).
*/}}
{{- define "zelkor-platform.langfuseInitIngestCredentials" -}}
{{- $init := .Values.langfuse.init | default dict -}}
{{- $pk := $init.projectPublicKey | default "" | toString | trim -}}
{{- $sk := $init.projectSecretKey | default "" | toString | trim -}}
{{- $initSecretName := include "zelkor-platform.langfuseInitSecretName" . -}}
{{- if and (not $pk) (not $sk) $init.existingSecret }}
{{- $byo := lookup "v1" "Secret" .Release.Namespace $init.existingSecret -}}
{{- if and $byo $byo.data (index $byo.data "publicKey") (index $byo.data "secretKey") }}
{{- $pk = index $byo.data "publicKey" | b64dec -}}
{{- $sk = index $byo.data "secretKey" | b64dec -}}
{{- end }}
{{- end }}
{{- if and (not $pk) (not $sk) (not $init.existingSecret) }}
{{- $existing := lookup "v1" "Secret" .Release.Namespace $initSecretName -}}
{{- if and $existing $existing.data (index $existing.data "publicKey") (index $existing.data "secretKey") }}
{{- $pk = index $existing.data "publicKey" | b64dec -}}
{{- $sk = index $existing.data "secretKey" | b64dec -}}
{{- end }}
{{- end }}
{{- printf "publicKey: %s\nsecretKey: %s" $pk $sk -}}
{{- end }}

{{- define "zelkor-platform.nemoOtelEnv" -}}
{{- if eq (include "zelkor-platform.nemoOtelEnabled" .) "true" }}
{{- $creds := include "zelkor-platform.langfuseInitIngestCredentials" . | fromYaml -}}
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
{{- if and $creds.publicKey $creds.secretKey }}
- name: OTEL_EXPORTER_OTLP_HEADERS
  value: {{ printf "Authorization=Basic %s" (b64enc (printf "%s:%s" $creds.publicKey $creds.secretKey)) | quote }}
{{- end }}
- name: OTEL_PYTHON_FASTAPI_EXCLUDED_URLS
  value: "/v1/health"
- name: LANGFUSE_EXTRA_OTLP
  value: {{ (.Values.langfuse.extraProjects | default list) | toJson | quote }}
{{- end }}
{{- end }}

{{- define "zelkor-platform.nemoLangfuseOtelEnvFrom" -}}
{{- if eq (include "zelkor-platform.nemoOtelEnabled" .) "true" }}
- secretRef:
    name: {{ include "zelkor-platform.langfuseOtelSecretName" . }}
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
{{- printf "%s:%s" $img.repository ($img.tag | default "1.0.0") -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.langfuseInitKeysConfigured" -}}
{{- $init := .Values.langfuse.init | default dict -}}
{{- if and .Values.langfuse.enabled $init.enabled -}}
true
{{- end -}}
{{- end }}

{{- define "zelkor-platform.langfuseInitSecretName" -}}
{{- $init := .Values.langfuse.init | default dict -}}
{{- if $init.existingSecret -}}
{{- $init.existingSecret -}}
{{- else -}}
{{- printf "%s-langfuse-init" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.langfuseBootstrapWaitInitContainer" -}}
{{- if eq (include "zelkor-platform.langfuseInitKeysConfigured" .) "true" }}
{{- $init := .Values.langfuse.init | default dict -}}
{{- $pk := $init.projectPublicKey | default "" | toString | trim -}}
{{- $sk := $init.projectSecretKey | default "" | toString | trim -}}
{{- $lfHost := printf "http://%s-langfuse:3000" (include "zelkor-platform.fullname" .) -}}
- name: wait-langfuse-bootstrap
  image: {{ .Values.global.initContainerImage | default "busybox:1.37" | quote }}
  env:
    - name: LANGFUSE_HOST
      value: {{ $lfHost | quote }}
    {{- if and $pk $sk }}
    - name: LANGFUSE_PUBLIC_KEY
      value: {{ $pk | quote }}
    - name: LANGFUSE_SECRET_KEY
      value: {{ $sk | quote }}
    {{- else }}
    - name: LANGFUSE_PUBLIC_KEY
      valueFrom:
        secretKeyRef:
          name: {{ include "zelkor-platform.langfuseInitSecretName" . }}
          key: publicKey
    - name: LANGFUSE_SECRET_KEY
      valueFrom:
        secretKeyRef:
          name: {{ include "zelkor-platform.langfuseInitSecretName" . }}
          key: secretKey
    {{- end }}
  command:
    - sh
    - -c
    - |
      set -e
      deadline=$(( $(date +%s) + 1200 ))
      while [ "$(date +%s)" -lt "$deadline" ]; do
        if wget -q -O /dev/null "${LANGFUSE_HOST}/api/public/health" 2>/dev/null; then
          auth=$(printf '%s:%s' "${LANGFUSE_PUBLIC_KEY}" "${LANGFUSE_SECRET_KEY}" | base64 | tr -d '\n')
          if wget -q -O /dev/null --header="Authorization: Basic ${auth}" "${LANGFUSE_HOST}/api/public/llm-connections" 2>/dev/null; then
            echo "Langfuse init project API ready"
            exit 0
          fi
        fi
        sleep 5
      done
      echo "Timed out waiting for Langfuse bootstrap (init project API)" >&2
      exit 1
{{- end }}
{{- end }}

{{- define "zelkor-platform.langfuseAdminSecretName" -}}
{{- $a := .Values.langfuse.admin | default dict -}}
{{- if $a.existingSecret -}}
{{- $a.existingSecret -}}
{{- else -}}
{{- printf "%s-langfuse-admin" (include "zelkor-platform.fullname" .) -}}
{{- end -}}
{{- end }}

{{/*
OTEL ingest keys for GitOps zelkor-agent workers (envFrom). Same gate as aegraOtelEnv.
*/}}
{{- define "zelkor-platform.langfuseOtelSecretName" -}}
{{- printf "%s-langfuse-otel" (include "zelkor-platform.fullname" .) -}}
{{- end }}

{{- define "zelkor-platform.langfuseAdminEmailHost" -}}
{{- $host := .Values.gateway.hosts.langfuse | default "" -}}
{{- if not $host -}}
{{- $u := .Values.langfuse.nextauthUrl | default "" -}}
{{- $u = trimPrefix "https://" $u -}}
{{- $u = trimPrefix "http://" $u -}}
{{- $host = index (splitList "/" $u) 0 -}}
{{- $host = index (splitList ":" $host) 0 -}}
{{- end -}}
{{- if not $host -}}
{{- $host = "localhost" -}}
{{- end -}}
{{- $host -}}
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

{{/*
gVisor provisioning mode: auto renders as daemonset (preflight resolves auto before Helm when possible).
*/}}
{{- define "zelkor-platform.gvisorProvisioningMode" -}}
{{- $prov := .Values.security.sandbox.provisioning | default dict -}}
{{- $mode := $prov.mode | default "auto" -}}
{{- if eq $mode "auto" -}}
daemonset
{{- else -}}
{{ $mode }}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorInstallerEnabled" -}}
{{- if .Values.security.sandbox.enabled -}}
{{- eq (include "zelkor-platform.gvisorProvisioningMode" .) "daemonset" -}}
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorCreateRuntimeClass" -}}
{{- if kindIs "bool" .Values.security.sandbox.createRuntimeClass -}}
{{- if .Values.security.sandbox.createRuntimeClass -}}true{{- else -}}false{{- end -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorRuntimeClassEnabled" -}}
{{- if and .Values.security.sandbox.enabled (ne (include "zelkor-platform.gvisorProvisioningMode" .) "none") (eq (include "zelkor-platform.gvisorCreateRuntimeClass" .) "true") -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorVerifyHookEnabled" -}}
{{- $verify := .Values.security.sandbox.provisioning.verify | default dict -}}
{{- if kindIs "bool" $verify.enabled -}}
{{- if $verify.enabled -}}true{{- else -}}false{{- end -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorVerifyEnabled" -}}
{{- if and (eq (include "zelkor-platform.gvisorRuntimeClassEnabled" .) "true") (eq (include "zelkor-platform.gvisorVerifyHookEnabled" .) "true") -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.gvisorRelease" -}}
{{- $prov := .Values.security.sandbox.provisioning | default dict -}}
{{ $prov.gvisorRelease | default "20260817" }}
{{- end }}

{{- define "zelkor-platform.gvisorRuntimeClassName" -}}
{{ .Values.security.sandbox.runtimeClass | default "gvisor" }}
{{- end }}

{{/*
Shared nodeSelector / tolerations for gVisor installer DaemonSet pod spec (indented under spec:).
*/}}
{{- define "zelkor-platform.gvisorNodeScheduling" }}
{{- $nodes := .Values.security.sandbox.nodes | default dict }}
{{- $selector := $nodes.selector | default dict }}
{{- if $selector }}
nodeSelector:
{{ toYaml $selector | indent 2 }}
{{- end }}
{{- $tols := $nodes.tolerations | default list }}
tolerations:
{{- if $tols }}
{{ toYaml $tols | indent 2 }}
{{- end }}
  - operator: Exists
{{- end }}

{{/*
RuntimeClass scheduling block (indented under RuntimeClass spec).
*/}}
{{- define "zelkor-platform.gvisorRuntimeClassScheduling" }}
{{- $nodes := .Values.security.sandbox.nodes | default dict }}
{{- $selector := $nodes.selector | default dict }}
{{- $tols := $nodes.tolerations | default list }}
{{- if or $selector $tols }}
scheduling:
{{- if $selector }}
  nodeSelector:
{{ toYaml $selector | indent 4 }}
{{- end }}
{{- if $tols }}
  tolerations:
{{ toYaml $tols | indent 4 }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Sandbox execution log env (orchestrator + worker).
Usage: {{ include "zelkor-platform.sandboxExecutionLogEnv" . | nindent 12 }}
*/}}
{{- define "zelkor-platform.sandboxExecutionLogEnv" -}}
{{- $log := .Values.security.sandbox.executionLog | default dict -}}
- name: SANDBOX_EXECUTION_LOG_ENABLED
  value: {{ ternary "true" "false" ($log.enabled | default true) | quote }}
- name: SANDBOX_INCLUDE_STDOUT_PREVIEW
  value: {{ ternary "true" "false" ($log.includeStdoutPreview | default false) | quote }}
- name: SANDBOX_SUSPICIOUS_ON_PROBE_PLUS_ERROR
  value: {{ ternary "true" "false" ($log.suspiciousOnProbePlusError | default true) | quote }}
{{- end }}

{{/*
Path B HA. Chart default false.
*/}}
{{- define "zelkor-platform.haEnabled" -}}
{{- $ha := .Values.highAvailability | default dict -}}
{{- if $ha.enabled -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.serviceMonitorEnabled" -}}
{{- $obs := .Values.observability | default dict -}}
{{- $sm := $obs.serviceMonitor | default dict -}}
{{- if $sm.enabled -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.envoyProxyEmit" -}}
{{- $ep := .Values.gateway.envoyProxy | default dict -}}
{{- if or $ep.enabled (eq (include "zelkor-platform.haEnabled" . | trim) "true") -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayAzureEnabled" -}}
{{- $a := .Values.aiGateway.providers.azure | default dict -}}
{{- if and $a.apiKey $a.endpoint -}}true{{- else -}}false{{- end -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayBedrockEnabled" -}}
{{- $b := .Values.aiGateway.providers.bedrock | default dict -}}
{{- if and $b.accessKeyId $b.secretAccessKey -}}true{{- else -}}false{{- end -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayVertexEnabled" -}}
{{- $v := .Values.aiGateway.providers.vertex | default dict -}}
{{- if and $v.project $v.region -}}true{{- else -}}false{{- end -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayCohereEnabled" -}}
{{- $c := .Values.aiGateway.providers.cohere | default dict -}}
{{- if $c.apiKey -}}true{{- else -}}false{{- end -}}
{{- end }}

{{- define "zelkor-platform.azureHostname" -}}
{{- $ep := (.Values.aiGateway.providers.azure.endpoint | default "") -}}
{{- if not (contains "://" $ep) -}}
{{- $ep = printf "https://%s" $ep -}}
{{- end -}}
{{- (urlParse $ep).hostname | required "aiGateway.providers.azure.endpoint must include a hostname" -}}
{{- end }}

{{- define "zelkor-platform.vertexAnthropicRegion" -}}
{{- $v := .Values.aiGateway.providers.vertex | default dict -}}
{{- $v.anthropicRegion | default $v.region -}}
{{- end }}

{{/* GCP global location uses aiplatform.googleapis.com, not global-aiplatform.googleapis.com */}}
{{- define "zelkor-platform.vertexAIHostname" -}}
{{- $region := . | required "vertexAIHostname: region is required" -}}
{{- if eq $region "global" -}}
aiplatform.googleapis.com
{{- else -}}
{{- printf "%s-aiplatform.googleapis.com" $region -}}
{{- end -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayHasProviders" -}}
{{- $p := .Values.aiGateway.providers | default dict -}}
{{- $compat := $p.openaiCompat | default list -}}
{{- $n := 0 -}}
{{- if $p.openai.apiKey }}{{ $n = add $n 1 }}{{ end -}}
{{- if $p.anthropic.apiKey }}{{ $n = add $n 1 }}{{ end -}}
{{- if $p.gemini.apiKey }}{{ $n = add $n 1 }}{{ end -}}
{{- if $p.vllm.backendUrl }}{{ $n = add $n 1 }}{{ end -}}
{{- if $p.ollamaCloud.apiKey }}{{ $n = add $n 1 }}{{ end -}}
{{- if $p.ollamaLocal.host }}{{ $n = add $n 1 }}{{ end -}}
{{- if eq (include "zelkor-platform.aiGatewayAzureEnabled" .) "true" }}{{ $n = add $n 1 }}{{ end -}}
{{- if eq (include "zelkor-platform.aiGatewayBedrockEnabled" .) "true" }}{{ $n = add $n 1 }}{{ end -}}
{{- if eq (include "zelkor-platform.aiGatewayVertexEnabled" .) "true" }}{{ $n = add $n 1 }}{{ end -}}
{{- if eq (include "zelkor-platform.aiGatewayCohereEnabled" .) "true" }}{{ $n = add $n 1 }}{{ end -}}
{{- range $compat -}}
{{- if and .name .host .modelMatch }}{{ $n = add $n 1 }}{{ end -}}
{{- end -}}
{{- if gt $n 0 -}}true{{- else -}}false{{- end -}}
{{- end }}

{{/*
JSON array of backend+match pairs for AIGatewayRoute. Prefix-namespaced ids avoid gemini/claude collisions.
*/}}
{{- define "zelkor-platform.aiGatewayProviderMatches" -}}
{{- $p := .Values.aiGateway.providers | default dict -}}
{{- $full := include "zelkor-platform.fullname" . -}}
{{- $rules := list -}}
{{- if $p.openai.apiKey -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-openai" $full) "match" "^(openai/.*|gpt-[0-9].*|o1.*|o3.*|text-embedding.*|chatgpt-.*)") -}}
{{- end -}}
{{- if $p.anthropic.apiKey -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-anthropic" $full) "match" "^(anthropic/.*|claude-.*)") -}}
{{- end -}}
{{- if $p.gemini.apiKey -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-gemini" $full) "match" "^(gemini/.*|gemini-.*)") -}}
{{- end -}}
{{- if $p.vllm.backendUrl -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-vllm" $full) "match" "^(vllm/.*)") -}}
{{- end -}}
{{- if $p.ollamaCloud.apiKey -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-ollama-cloud" $full) "match" "^(gpt-oss.*|deepseek-r1.*|qwen3.*|gemma4.*|gemma.*)") -}}
{{- end -}}
{{- if $p.ollamaLocal.host -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-ollama-local" $full) "match" "^(ollama/.*|llama.*|deepseek.*|qwen.*|mistral.*|phi.*|codellama.*)") -}}
{{- end -}}
{{- if eq (include "zelkor-platform.aiGatewayAzureEnabled" .) "true" -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-azure" $full) "match" "^(azure/.*)") -}}
{{- end -}}
{{- if eq (include "zelkor-platform.aiGatewayBedrockEnabled" .) "true" -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-bedrock" $full) "match" "^(bedrock/.*)") -}}
{{- if $p.bedrock.anthropic -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-bedrock-anthropic" $full) "match" "^(bedrock-anthropic/.*)") -}}
{{- end -}}
{{- end -}}
{{- if eq (include "zelkor-platform.aiGatewayVertexEnabled" .) "true" -}}
{{- /* Envoy GCPVertexAI uses the request model id in the Vertex URL; vertex/ prefix is routing-only and must not be sent. */ -}}
{{- $vertexMatch := "^(vertex/.*)" -}}
{{- if not $p.gemini.apiKey -}}
{{- $vertexMatch = "^(gemini-.*)" -}}
{{- end -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-vertex" $full) "match" $vertexMatch) -}}
{{- if $p.vertex.anthropic -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-vertex-anthropic" $full) "match" "^(vertex-anthropic/.*)") -}}
{{- end -}}
{{- end -}}
{{- if eq (include "zelkor-platform.aiGatewayCohereEnabled" .) "true" -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-cohere" $full) "match" "^(cohere/.*)") -}}
{{- end -}}
{{- range $p.openaiCompat | default list -}}
{{- if and .name .host .modelMatch -}}
{{- $rules = append $rules (dict "backend" (printf "%s-backend-compat-%s" $full .name) "match" .modelMatch) -}}
{{- end -}}
{{- end -}}
{{- $rules | toJson -}}
{{- end }}

{{- define "zelkor-platform.aiGatewayDefaultBackend" -}}
{{- $p := .Values.aiGateway.providers | default dict -}}
{{- $full := include "zelkor-platform.fullname" . -}}
{{- if $p.openai.apiKey -}}
{{- printf "%s-backend-openai" $full -}}
{{- else if $p.ollamaCloud.apiKey -}}
{{- printf "%s-backend-ollama-cloud" $full -}}
{{- else if $p.ollamaLocal.host -}}
{{- printf "%s-backend-ollama-local" $full -}}
{{- else if $p.anthropic.apiKey -}}
{{- printf "%s-backend-anthropic" $full -}}
{{- else if $p.gemini.apiKey -}}
{{- printf "%s-backend-gemini" $full -}}
{{- else if $p.vllm.backendUrl -}}
{{- printf "%s-backend-vllm" $full -}}
{{- else if eq (include "zelkor-platform.aiGatewayAzureEnabled" .) "true" -}}
{{- printf "%s-backend-azure" $full -}}
{{- else if eq (include "zelkor-platform.aiGatewayBedrockEnabled" .) "true" -}}
{{- printf "%s-backend-bedrock" $full -}}
{{- else if eq (include "zelkor-platform.aiGatewayVertexEnabled" .) "true" -}}
{{- printf "%s-backend-vertex" $full -}}
{{- else if eq (include "zelkor-platform.aiGatewayCohereEnabled" .) "true" -}}
{{- printf "%s-backend-cohere" $full -}}
{{- else -}}
{{- $found := "" -}}
{{- range $p.openaiCompat | default list -}}
{{- if and (not $found) .name .host .modelMatch -}}
{{- $found = printf "%s-backend-compat-%s" $full .name -}}
{{- end -}}
{{- end -}}
{{- $found -}}
{{- end -}}
{{- end }}

