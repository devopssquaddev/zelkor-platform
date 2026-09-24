#!/usr/bin/env ruby
# frozen_string_literal: true

require "pathname"

ROOT = Pathname.new(__dir__).join("..", "templates").expand_path

DEFAULT_INTENT = {
  "postgresql" => "postgresql",
  "valkey" => "valkey",
  "clickhouse" => "clickhouse",
  "qdrant" => "qdrant",
  "seaweedfs" => "seaweedfs",
  "aegra" => "aegra",
  "guardrails" => "guardrails.nemo",
  "langfuse" => "langfuse",
  "observability" => "observability",
  "security" => "security",
  "gateway" => "gateway",
  "hpa.yaml" => "highAvailability",
  "pdb.yaml" => "highAvailability",
  "mcp/deployment-gateway.yaml" => "mcp.gateway",
  "mcp/deployment-postgres.yaml" => "mcp.postgresMCP",
  "mcp/deployment-qdrant.yaml" => "mcp.qdrantMCP",
  "mcp/deployment-egress.yaml" => "mcp.egressMCP",
  "mcp/deployment-sandbox.yaml" => "mcp.sandboxMCP",
  "mcp/secret-sandbox-worker.yaml" => "mcp.sandboxMCP",
  "ai-gateway/service.yaml" => "aiGateway",
  "ai-gateway/mcproute.yaml" => "aiGateway",
  "ai-gateway/aigatewayroute.yaml" => "aiGateway",
  "ai-gateway/clienttrafficpolicy.yaml" => "aiGateway",
  "ai-gateway/unknown-model-reject.yaml" => "aiGateway",
  "ai-gateway/securitypolicies.yaml" => "aiGateway",
  "ai-gateway/secrets.yaml" => "aiGateway",
  "ai-gateway/backends.yaml" => "aiGateway.providers",
}.freeze

BACKENDS_INTENT_SUBS = [
  ["ollamaLocal", "aiGateway.providers.ollamaLocal"],
  ["ollamaCloud", "aiGateway.providers.ollamaCloud"],
  ["openai", "aiGateway.providers.openai"],
  ["anthropic", "aiGateway.providers.anthropic"],
  ["gemini", "aiGateway.providers.gemini"],
  ["azure", "aiGateway.providers.azure"],
  ["bedrock", "aiGateway.providers.bedrock"],
  ["vertex", "aiGateway.providers.vertex"],
  ["cohere", "aiGateway.providers.cohere"],
  ["vllm", "aiGateway.providers.vllm"],
  ["openaiCompat", "aiGateway.providers.openaiCompat"],
].freeze

def intent_for(rel)
  rel = rel.to_s
  return DEFAULT_INTENT[rel] if DEFAULT_INTENT.key?(rel)
  top = rel.split("/").first
  return DEFAULT_INTENT[top] if DEFAULT_INTENT.key?(top)
  DEFAULT_INTENT[rel] || top
end

ROOT.glob("**/*.{yaml,tpl}").each do |path|
  next if path.basename.to_s.start_with?("_")
  next if path.basename.to_s == "validate.yaml"
  next if path.basename.to_s == "extra-manifests.yaml"

  rel = path.relative_path_from(ROOT).to_s
  intent = intent_for(rel)
  text = path.read
  next unless text.include?('include "zelkor-platform.labels" .')

  new_text = text.gsub(
    '{{- include "zelkor-platform.labels" . | nindent 4 }}',
    "{{- include \"zelkor-platform.labels\" (dict \"root\" . \"intent\" \"#{intent}\") | nindent 4 }}"
  ).gsub(
    '{{- include "zelkor-platform.labels" . | nindent 6 }}',
    "{{- include \"zelkor-platform.labels\" (dict \"root\" . \"intent\" \"#{intent}\") | nindent 6 }}"
  ).gsub(
    '{{- include "zelkor-platform.labels" . | nindent 8 }}',
    "{{- include \"zelkor-platform.labels\" (dict \"root\" . \"intent\" \"#{intent}\") | nindent 8 }}"
  )

  if rel == "ai-gateway/backends.yaml"
    BACKENDS_INTENT_SUBS.each do |needle, prov_intent|
      new_text = new_text.gsub(
        /(# [^\n]*#{needle}[^\n]*\n(?:.*\n)*?)({{- include "zelkor-platform.labels" \(dict "root" \. "intent" "aiGateway.providers"\) \| nindent 4 }})/m
      ) do |m|
        m.sub('intent" "aiGateway.providers"', "intent\" \"#{prov_intent}\"")
      end
    end
    # Simpler: replace per-section after generic pass
    sections = new_text.split(/^# /)
    rebuilt = [sections.shift]
    sections.each do |sec|
      block = "# " + sec
      intent_sub = "aiGateway.providers"
      BACKENDS_INTENT_SUBS.each do |needle, prov|
        if block.match?(/#{needle}/i) || block.include?(needle)
          intent_sub = prov
          break
        end
      end
      block = block.gsub(
        'intent" "aiGateway.providers"',
        "intent\" \"#{intent_sub}\""
      )
      rebuilt << block
    end
    new_text = rebuilt.join
  end

  path.write(new_text) if new_text != text
end

puts "Provenance intents applied."
