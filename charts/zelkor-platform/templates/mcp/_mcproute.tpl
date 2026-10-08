{{/*
MCPRoute helpers: native/extra backend refs, compile extras for Langfuse seed.
CE does not emit Envoy egress NetworkPolicies from extra FQDN CIDRs.
*/}}
{{- define "zelkor-platform.mcpReservedBackendNames" -}}
postgres,qdrant,sandbox,aigateway,nemo,aegra,langfuse,object
{{- end }}

{{- define "zelkor-platform.mcpMcprouteEnabled" -}}
{{- if and .Values.mcp.enabled (or .Values.gateway.enabled ((.Values.gateway.parentRef).name | default "")) -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.mcpNativeBackends" -}}
{{- $fn := include "zelkor-platform.fullname" . -}}
{{- $ns := .Release.Namespace -}}
{{- $list := list -}}
{{- if (.Values.mcp.postgresMCP).enabled -}}
{{- $list = append $list (dict "name" "postgres" "hostname" (printf "%s-mcp-postgres.%s.svc.cluster.local" $fn $ns)) -}}
{{- end -}}
{{- if (.Values.mcp.qdrantMCP).enabled -}}
{{- $list = append $list (dict "name" "qdrant" "hostname" (printf "%s-mcp-qdrant.%s.svc.cluster.local" $fn $ns)) -}}
{{- end -}}
{{- if (.Values.mcp.sandboxMCP).enabled -}}
{{- $list = append $list (dict "name" "sandbox" "hostname" (printf "%s-mcp-sandbox.%s.svc.cluster.local" $fn $ns)) -}}
{{- end -}}
{{- if (.Values.mcp.aigatewayMCP).enabled -}}
{{- $list = append $list (dict "name" "aigateway" "hostname" (printf "%s-mcp-aigateway.%s.svc.cluster.local" $fn $ns)) -}}
{{- end -}}
{{- if (.Values.mcp.objectMCP).enabled -}}
{{- $list = append $list (dict "name" "object" "hostname" (printf "%s-mcp-object.%s.svc.cluster.local" $fn $ns)) -}}
{{- end -}}
{{- $list | toJson -}}
{{- end }}

{{- define "zelkor-platform.compile.mcpExtraBackends" -}}
{{- $root := . -}}
{{- $items := (.Values.mcp.extraBackends | default list) -}}
{{- $reserved := splitList "," (include "zelkor-platform.mcpReservedBackendNames" .) -}}
{{- $seed := list -}}
{{- range $idx, $item := $items -}}
{{- if not (kindIs "map" $item) -}}
{{- fail (printf "workspace.tools.extraBackends[%d] must be an object" $idx) -}}
{{- end -}}
{{- $allowed := list "name" "service" "fqdn" "path" "apiKey" "tls" "toolSelector" "forwardHeaders" "egress" -}}
{{- range $k, $_ := $item -}}
{{- if not (has $k $allowed) -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: unknown key %q (allowed: %s)" $idx $k (join ", " $allowed)) -}}
{{- end -}}
{{- end -}}
{{- $name := ($item.name | default "" | trim) -}}
{{- if not $name -}}{{- fail (printf "workspace.tools.extraBackends[%d].name is required" $idx) -}}{{- end -}}
{{- if has $name $reserved -}}{{- fail (printf "workspace.tools.extraBackends[%d].name %q is reserved" $idx $name) -}}{{- end -}}
{{- $svc := $item.service | default dict -}}
{{- $fqdn := $item.fqdn | default dict -}}
{{- $svcPort := $svc.port | default 0 | int -}}
{{- $fqdnPort := $fqdn.port | default 0 | int -}}
{{- $hasSvc := and ($svc.name | default "") (ne $svcPort 0) -}}
{{- $hasFqdn := and ($fqdn.hostname | default "") (ne $fqdnPort 0) -}}
{{- if and $hasSvc $hasFqdn -}}{{- fail (printf "workspace.tools.extraBackends[%d]: set exactly one of service or fqdn" $idx) -}}{{- end -}}
{{- if not (or $hasSvc $hasFqdn) -}}{{- fail (printf "workspace.tools.extraBackends[%d]: service or fqdn is required" $idx) -}}{{- end -}}
{{- range $fh := $item.forwardHeaders | default list -}}
{{- $hn := $fh -}}
{{- if kindIs "map" $fh -}}{{- $hn = $fh.name | default "" -}}{{- end -}}
{{- if eq $hn "Authorization" -}}
{{- fail (printf "workspace.tools.extraBackends[%d]: forwardHeaders must not include Authorization" $idx) -}}
{{- end -}}
{{- end -}}
{{- $seed = append $seed (dict "name" $name "path" ($item.path | default "/mcp")) -}}
{{- end -}}
{{- $_ := set $root.Values "__mcpExtraBackendSeedJson" ($seed | toJson) -}}
{{- end -}}

{{- define "zelkor-platform.objectStoreInCluster" -}}
{{- $obj := (.Values.mcp.objectMCP | default dict) -}}
{{- $endpoint := (($obj.s3).endpoint | default "") -}}
{{- $host := printf "%s-seaweedfs" (include "zelkor-platform.fullname" .) -}}
{{- $epHost := $endpoint | trimPrefix "http://" | trimPrefix "https://" -}}
{{- $epHost = splitList "/" $epHost | first -}}
{{- $epHost = splitList ":" $epHost | first -}}
{{- if and $obj.enabled (or (contains $host $endpoint) (and (not (contains "." $epHost)) (hasSuffix "-seaweedfs" $epHost))) -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.seaweedfsRender" -}}
{{- $inCluster := eq (include "zelkor-platform.objectStoreInCluster" .) "true" -}}
{{- if and .Values.seaweedfs.enabled (or .Values.langfuse.enabled $inCluster) -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}

{{- define "zelkor-platform.compile.objectMCP" -}}
{{- $obj := (.Values.mcp.objectMCP | default dict) -}}
{{- if $obj.enabled -}}
{{- $s3 := $obj.s3 | default dict -}}
{{- $endpoint := $s3.endpoint | default "" | trim -}}
{{- $bucket := $s3.bucket | default "" | trim -}}
{{- if not $endpoint -}}{{- fail "workspace.tools.objectMCP.s3.endpoint is required when objectMCP.enabled" -}}{{- end -}}
{{- if not $bucket -}}{{- fail "workspace.tools.objectMCP.s3.bucket is required when objectMCP.enabled" -}}{{- end -}}
{{- if not (regexMatch "^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$" $bucket) -}}
{{- fail "workspace.tools.objectMCP.s3.bucket must be a DNS-style S3 bucket name" -}}
{{- end -}}
{{- $auth := $s3.auth | default dict -}}
{{- $ref := $auth.secretRef | default "" | trim -}}
{{- $ak := $auth.accessKey | default "" | trim -}}
{{- $sk := $auth.secretKey | default "" | trim -}}
{{- if and $ref (or $ak $sk) -}}
{{- fail "workspace.tools.objectMCP.s3.auth: set secretRef or accessKey and secretKey, not both" -}}
{{- end -}}
{{- if and (not $ref) (or (not $ak) (not $sk)) -}}
{{- fail "workspace.tools.objectMCP.s3.auth.accessKey and secretKey are required when secretRef is empty" -}}
{{- end -}}
{{- $inCluster := eq (include "zelkor-platform.objectStoreInCluster" .) "true" -}}
{{- if $inCluster -}}
{{- if not .Values.seaweedfs.enabled -}}
{{- fail "seaweedfs.enabled must be true when objectMCP.s3.endpoint points at in-cluster SeaweedFS" -}}
{{- end -}}
{{- $ident := .Values.seaweedfs.objectIdentity | default dict -}}
{{- if or (not ($ident.accessKey | default "" | trim)) (not ($ident.secretKey | default "" | trim)) -}}
{{- fail "seaweedfs.objectIdentity.accessKey and secretKey are required when objectMCP uses in-cluster SeaweedFS" -}}
{{- end -}}
{{- if and (not $ref) (or (ne $ak ($ident.accessKey | trim)) (ne $sk ($ident.secretKey | trim))) -}}
{{- fail "workspace.tools.objectMCP.s3.auth must match seaweedfs.objectIdentity when using in-cluster SeaweedFS" -}}
{{- end -}}
{{- end -}}
{{- if and (not $inCluster) .Values.security.networkPolicies.enabled (eq (len ($s3.egressCIDRs | default list)) 0) -}}
{{- fail "workspace.tools.objectMCP.s3.egressCIDRs is required for an external S3 endpoint when security.networkPolicies.enabled" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "zelkor-platform.tenantJwtValidate" -}}
{{- $jwt := ((.Values.platform.tenants).jwt | default dict) -}}
{{- $issuer := $jwt.issuer | default "" | trim -}}
{{- $audiences := $jwt.audiences | default list -}}
{{- $ls := ($jwt.localSigning | default dict) -}}
{{- $sources := 0 -}}
{{- $rawJwks := $jwt.jwks | default "" -}}
{{- $inlineJwks := false -}}
{{- if kindIs "string" $rawJwks -}}
{{- if $rawJwks | trim -}}{{- $inlineJwks = true -}}{{- end -}}
{{- else if $rawJwks -}}{{- $inlineJwks = true -}}{{- end -}}
{{- if and $inlineJwks (not $ls.enabled) -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- if $jwt.jwksConfigMap | default "" | trim -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- if $jwt.remoteJwksUri | default "" | trim -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- if $ls.enabled -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- if or (not $issuer) (eq (len $audiences) 0) (eq $sources 0) -}}
{{- fail "platform.tenants.jwt requires issuer, non-empty audiences, and one JWKS source (jwks, jwksConfigMap, remoteJwksUri, or localSigning.enabled)" -}}
{{- end -}}
{{- if gt $sources 1 -}}
{{- fail "platform.tenants.jwt: only one JWKS source may be set" -}}
{{- end -}}
{{- if and ($jwt.remoteJwksUri | default "" | trim) .Values.security.networkPolicies.enabled (eq (len ($jwt.jwksEgressCIDRs | default list)) 0) -}}
{{- fail "platform.tenants.jwt.remoteJwksUri requires jwksEgressCIDRs when security.networkPolicies.enabled" -}}
{{- end -}}
{{- $lfTools := ((.Values.langfuse | default dict).surfaces | default dict).tools | default dict -}}
{{- if and ($ls.enabled) (not ($ls.seedTenant | default "" | trim)) ($lfTools.seedFromMcp | default false) -}}
{{- fail "platform.tenants.jwt.localSigning.seedTenant is required when langfuse surfaces seed MCP tools" -}}
{{- end -}}
{{- end -}}

{{- define "zelkor-platform.mcpRouteValidate" -}}
{{- if not (eq (include "zelkor-platform.mcpMcprouteEnabled" .) "true") -}}
{{- if .Values.mcp.enabled -}}
{{- fail "mcp.enabled requires gateway.enabled or gateway.parentRef.name for MCPRoute" -}}
{{- end -}}
{{- else -}}
{{- include "zelkor-platform.tenantJwtValidate" . -}}
{{- $pr := (.Values.gateway.parentRef | default dict) -}}
{{- $ownsGw := or .Values.gateway.enabled (eq (include "zelkor-platform.envoyProxyEmit" . | trim) "true") -}}
{{- if and (not $ownsGw) ($pr.name | default "") (not (.Values.mcp.mcproute.sharedGatewayAck | default false)) -}}
{{- fail "shared Gateway topology requires gateway.mcproute.sharedGatewayAck: true" -}}
{{- end -}}
{{- $target := include "zelkor-platform.envoyDataplaneHost" . | trim -}}
{{- if and (not $target) (not (.Values.security.mcp.acceptUnprotectedBackends | default false)) -}}
{{- fail "aiGateway.inClusterService.targetHost must be set when the chart does not emit EnvoyProxy (or set security.mcp.acceptUnprotectedBackends for lab overlays)" -}}
{{- end -}}
{{- end -}}
{{- end -}}
