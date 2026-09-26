{{/*
Compile workspace.tools.extraBackends into MCP_EXTRA_BACKENDS JSON (no secret values) plus secret env refs.
Sets .Values.__mcpExtraBackendEnv and .Values.__mcpExtraBackendVolumes when compile runs.
*/}}
{{- define "zelkor-platform.mcpUrlIsInCluster" -}}
{{- $u := . | trim -}}
{{- if or (contains ".svc" $u) (contains ".svc.cluster.local" $u) -}}
true
{{- else -}}
{{- $host := (regexReplaceAll "^https?://([^/:]+).*" $u "$1") -}}
{{- if and $host (not (contains "." $host)) -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "zelkor-platform.compile.mcpExtraBackends" -}}
{{- $root := . -}}
{{- $items := (.Values.mcp.extraBackends | default list) -}}
{{- $compiled := list -}}
{{- $env := list -}}
{{- $volumes := list -}}
{{- $volumeMounts := list -}}
{{- $ipBlocks := list -}}
{{- range $idx, $item := $items -}}
{{- if not (kindIs "map" $item) -}}
{{- fail (printf "workspace.tools.extraBackends[%d] must be an object" $idx) -}}
{{- end -}}
{{- $name := ($item.name | default "" | trim) -}}
{{- $url := ($item.url | default "" | trim) -}}
{{- if not $name -}}{{- fail (printf "workspace.tools.extraBackends[%d].name is required" $idx) -}}{{- end -}}
{{- if not $url -}}{{- fail (printf "workspace.tools.extraBackends[%d].url is required" $idx) -}}{{- end -}}
{{- $auth := ($item.auth | default dict) -}}
{{- $authType := ($auth.type | default "none" | trim) -}}
{{- if and (eq $authType "bearer") (not ($auth.secretRef).name) -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: auth.secretRef.name required for bearer auth" $idx) -}}
{{- end -}}
{{- if and (eq $authType "header") (or (not ($auth.secretRef).name) (not ($auth.headerName | default "" | trim))) -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: auth.headerName and auth.secretRef required for header auth" $idx) -}}
{{- end -}}
{{- if and (eq $authType "basic") (or (not ($auth.usernameSecretRef).name) (not ($auth.passwordSecretRef).name)) -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: auth.usernameSecretRef and passwordSecretRef required for basic auth" $idx) -}}
{{- end -}}
{{- $egress := ($item.egress | default dict) -}}
{{- $cidrs := ($egress.cidrs | default list) -}}
{{- if and $root.Values.security.networkPolicies.enabled (not (eq (include "zelkor-platform.mcpUrlIsInCluster" $url) "true")) (eq (len $cidrs) 0) -}}
{{- fail (printf "workspace.tools.extraBackends[%d] (%s): external URL requires egress.cidrs when security.networkPolicies.enabled" $idx $name) -}}
{{- end -}}
{{- $entry := dict "name" $name "url" $url "path" ($item.path | default "/mcp") "timeoutSeconds" ($item.timeoutSeconds | default 30) "forwardAuthorization" ($item.forwardAuthorization | default true) "forwardTenantHeader" ($item.forwardTenantHeader | default true) "injectTenantArg" ($item.injectTenantArg | default true) -}}
{{- if $item.headers -}}{{- $_ := set $entry "headers" $item.headers -}}{{- end -}}
{{- if eq $authType "bearer" -}}
{{- $envName := printf "ZELKOR_XB_%d_BEARER" $idx -}}
{{- $env = append $env (dict "name" $envName "valueFrom" (dict "secretKeyRef" (dict "name" ($auth.secretRef.name) "key" ($auth.secretRef.key | default "token")))) -}}
{{- $_ := set $entry "auth" (dict "type" "bearer" "bearerEnv" $envName) -}}
{{- $_ := set $entry "forwardAuthorization" false -}}
{{- else if eq $authType "header" -}}
{{- $envName := printf "ZELKOR_XB_%d_HDR" $idx -}}
{{- $env = append $env (dict "name" $envName "valueFrom" (dict "secretKeyRef" (dict "name" ($auth.secretRef.name) "key" ($auth.secretRef.key | default "token")))) -}}
{{- $_ := set $entry "auth" (dict "type" "header" "headerName" $auth.headerName "headerEnv" $envName) -}}
{{- $_ := set $entry "forwardAuthorization" false -}}
{{- else if eq $authType "basic" -}}
{{- $userEnv := printf "ZELKOR_XB_%d_USER" $idx -}}
{{- $passEnv := printf "ZELKOR_XB_%d_PASS" $idx -}}
{{- $env = append $env (dict "name" $userEnv "valueFrom" (dict "secretKeyRef" (dict "name" ($auth.usernameSecretRef.name) "key" ($auth.usernameSecretRef.key | default "username")))) -}}
{{- $env = append $env (dict "name" $passEnv "valueFrom" (dict "secretKeyRef" (dict "name" ($auth.passwordSecretRef.name) "key" ($auth.passwordSecretRef.key | default "password")))) -}}
{{- $_ := set $entry "auth" (dict "type" "basic" "usernameEnv" $userEnv "passwordEnv" $passEnv) -}}
{{- $_ := set $entry "forwardAuthorization" false -}}
{{- else if ne $authType "none" -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: auth.type must be none, bearer, basic, or header" $idx) -}}
{{- end -}}
{{- $headersFrom := list -}}
{{- range $hi, $hf := ($item.headersFrom | default list) -}}
{{- if ($hf.secretRef).name -}}
{{- $hEnv := printf "ZELKOR_XB_%d_HF_%d" $idx $hi -}}
{{- $env = append $env (dict "name" $hEnv "valueFrom" (dict "secretKeyRef" (dict "name" $hf.secretRef.name "key" ($hf.secretRef.key | default "value")))) -}}
{{- $headersFrom = append $headersFrom (dict "header" $hf.header "env" $hEnv) -}}
{{- end -}}
{{- end -}}
{{- if gt (len $headersFrom) 0 -}}{{- $_ := set $entry "headersFrom" $headersFrom -}}{{- end -}}
{{- $tls := ($item.tls | default dict) -}}
{{- if ($tls.caSecretRef).name -}}
{{- $volName := printf "mcp-xb-%d-ca" $idx -}}
{{- $mountPath := printf "/etc/zelkor/mcp-extra/%s" $name -}}
{{- $volumes = append $volumes (dict "name" $volName "secret" (dict "secretName" $tls.caSecretRef.name)) -}}
{{- $volumeMounts = append $volumeMounts (dict "name" $volName "mountPath" $mountPath "readOnly" true) -}}
{{- $_ := set $entry "tls" (dict "caPath" (printf "%s/%s" $mountPath ($tls.caSecretRef.key | default "ca.crt"))) -}}
{{- end -}}
{{- range $cidrs -}}
{{- $ipBlocks = append $ipBlocks (dict "cidr" . "ports" ($egress.ports | default (list 443))) -}}
{{- end -}}
{{- $compiled = append $compiled $entry -}}
{{- end -}}
{{- $_ := set $root.Values "__mcpExtraBackendJson" ($compiled | toJson) -}}
{{- $_ := set $root.Values "__mcpExtraBackendEnv" $env -}}
{{- $_ := set $root.Values "__mcpExtraBackendVolumes" $volumes -}}
{{- $_ := set $root.Values "__mcpExtraBackendVolumeMounts" $volumeMounts -}}
{{- $_ := set $root.Values "__mcpExtraBackendIpBlocks" $ipBlocks -}}
{{- end -}}
