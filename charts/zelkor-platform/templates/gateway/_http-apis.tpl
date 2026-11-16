{{- /*
CE-15a-4: secretless HTTP APIs. Validates workspace.tools.httpApis and stores the normalized list
as JSON in .Values.__httpApis: [{name, host, port, tls, prefix, credential:{secretRef, header},
rules:[{name, action, cel}]}]. Rules become first-match SecurityPolicy authorization CEL on the
agent-visible path; no match = Deny.
*/}}
{{- define "zelkor-platform.compile.httpApis" -}}
{{- $root := . -}}
{{- $items := ((.Values.workspace.tools | default dict).httpApis | default list) -}}
{{- $out := list -}}
{{- $seen := list -}}
{{- $methods := list "GET" "HEAD" "POST" "PUT" "DELETE" "CONNECT" "OPTIONS" "TRACE" "PATCH" -}}
{{- if and $items (not .Values.aiGateway.enabled) -}}
{{- fail "workspace.tools.httpApis needs the AI gateway (workspace.models.enabled): callers authenticate with its consumer key" -}}
{{- end -}}
{{- range $idx, $item := $items -}}
{{- $at := printf "workspace.tools.httpApis[%d]" $idx -}}
{{- if not (kindIs "map" $item) -}}{{- fail (printf "%s must be an object" $at) -}}{{- end -}}
{{- range $k, $_ := $item -}}
{{- if not (has $k (list "name" "url" "credential" "rules")) -}}
{{- fail (printf "%s: unknown key %q (allowed: name, url, credential, rules)" $at $k) -}}
{{- end -}}
{{- end -}}
{{- $name := $item.name | default "" | toString | trim -}}
{{- if not $name -}}{{- fail (printf "%s.name is required" $at) -}}{{- end -}}
{{- if not (regexMatch "^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$" $name) -}}
{{- fail (printf "%s.name %q must be a DNS label (lower-case, digits, '-', max 32)" $at $name) -}}
{{- end -}}
{{- if has $name $seen -}}{{- fail (printf "workspace.tools.httpApis: duplicate name %q" $name) -}}{{- end -}}
{{- $seen = append $seen $name -}}
{{- $url := $item.url | default "" | toString | trim -}}
{{- $u := urlParse $url -}}
{{- if or (not (has $u.scheme (list "http" "https"))) (not $u.hostname) -}}
{{- fail (printf "%s.url must be http(s)://host[:port][/prefix], got %q" $at $url) -}}
{{- end -}}
{{- $tls := eq $u.scheme "https" -}}
{{- $port := include "zelkor-platform.urlPort" (dict "url" $url "default" (ternary 443 80 $tls)) | int -}}
{{- $cred := dict -}}
{{- if $item.credential -}}
{{- $c := $item.credential -}}
{{- $ref := $c.secretRef | default "" | toString | trim -}}
{{- if not $ref -}}{{- fail (printf "%s.credential.secretRef is required" $at) -}}{{- end -}}
{{- $cred = dict "secretRef" $ref "header" ($c.header | default "Authorization" | toString | trim) -}}
{{- end -}}
{{- $rules := list -}}
{{- $allows := 0 -}}
{{- range $ri, $r := ($item.rules | default list) -}}
{{- $rat := printf "%s.rules[%d]" $at $ri -}}
{{- $action := $r.action | default "" | toString -}}
{{- if not (has $action (list "Allow" "Deny")) -}}{{- fail (printf "%s.action must be Allow or Deny" $rat) -}}{{- end -}}
{{- if eq $action "Allow" -}}{{- $allows = add1 $allows -}}{{- end -}}
{{- $terms := list -}}
{{- if $r.methods -}}
{{- $quoted := list -}}
{{- range $r.methods -}}
{{- if not (has (toString .) $methods) -}}
{{- fail (printf "%s: unknown method %q (upper-case: %s)" $rat (toString .) (join ", " $methods)) -}}
{{- end -}}
{{- $quoted = append $quoted (printf "%q" (toString .)) -}}
{{- end -}}
{{- $terms = append $terms (printf "request.method in [%s]" (join ", " $quoted)) -}}
{{- end -}}
{{- if $r.path -}}
{{- $ptype := "PathPrefix" -}}
{{- $pval := "" -}}
{{- if kindIs "map" $r.path -}}
{{- $ptype = $r.path.type | default "PathPrefix" | toString -}}
{{- $pval = $r.path.value | default "" | toString -}}
{{- else -}}
{{- $pval = toString $r.path -}}
{{- end -}}
{{- if not (has $ptype (list "Exact" "PathPrefix" "RegularExpression")) -}}
{{- fail (printf "%s.path.type must be Exact, PathPrefix or RegularExpression" $rat) -}}
{{- end -}}
{{- if and (ne $ptype "RegularExpression") (not (hasPrefix "/" $pval)) -}}
{{- fail (printf "%s.path %q must start with /" $rat $pval) -}}
{{- end -}}
{{- if eq $ptype "Exact" -}}{{- $terms = append $terms (printf "request.url_path == %q" $pval) -}}
{{- else if eq $ptype "PathPrefix" -}}{{- $terms = append $terms (printf "request.url_path.startsWith(%q)" $pval) -}}
{{- else -}}{{- $terms = append $terms (printf "request.url_path.matches(%q)" $pval) -}}
{{- end -}}
{{- end -}}
{{- $rules = append $rules (dict "name" (printf "%s-%d" $name $ri) "action" $action "cel" (ternary (join " && " $terms) "true" (gt (len $terms) 0))) -}}
{{- end -}}
{{- if eq $allows 0 -}}
{{- fail (printf "%s.rules needs at least one Allow rule (no match = 403)" $at) -}}
{{- end -}}
{{- $out = append $out (dict "name" $name "host" $u.hostname "port" $port "tls" $tls
      "prefix" ($u.path | default "" | trimSuffix "/") "credential" $cred "rules" $rules) -}}
{{- end -}}
{{- $_ := set $root.Values "__httpApis" ($out | toJson) -}}
{{- end -}}
