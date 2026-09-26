#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "yaml"

CHART_DIR = File.expand_path("..", __dir__)
VALUES_PATH = File.join(CHART_DIR, "values.yaml")
OUT_PATH = File.join(CHART_DIR, "values.schema.json")

V1_STUBS_PATH = File.join(CHART_DIR, "values.v1-intent-stubs.yaml")

OPEN_MAP_KEYS = %w[
  global resources annotations labels nodeSelector tolerations overhead
  extraRailsConfig graphs tenantOrgMappings models orgMappings
].freeze

ENUMS = {
  "platform.telemetry.level" => %w[DEBUG INFO WARNING ERROR CRITICAL],
  "platform.telemetry.format" => %w[json text],
  "databases.mode" => %w[in-cluster-basic operator-cr external],
  "global.tier" => %w[oss pro enterprise],
}.freeze

STRING_OR_OBJECT_PATHS = %w[
  workspace.models.providers.vertex.credentialsJson
].freeze

STRICT_ARRAY_ITEM_SCHEMAS = {
  "workspace.tools.extraBackends" => {
    "type" => "object",
    "additionalProperties" => false,
    "properties" => {
      "name" => { "type" => "string", "description" => "Backend name prefix for MCP gateway routing." },
      "url" => { "type" => "string", "description" => "MCP base URL (in-cluster or external HTTPS)." },
      "path" => { "type" => "string", "description" => "JSON-RPC path (default /mcp)." },
      "timeoutSeconds" => { "type" => %w[integer string], "description" => "Outbound RPC timeout." },
      "forwardAuthorization" => { "type" => "boolean", "description" => "Forward caller Zelkor Bearer (default true; false when backend auth sets Authorization)." },
      "forwardTenantHeader" => { "type" => "boolean", "description" => "Send X-Tenant-ID (default true)." },
      "injectTenantArg" => { "type" => "boolean", "description" => "Default args.tenant_id on tools/call (default true)." },
      "isolation" => { "type" => "string", "description" => "Enterprise: hardware for Kata (Ent only)." },
      "auth" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "type" => { "type" => "string", "enum" => %w[none bearer basic header] },
          "secretRef" => {
            "type" => "object",
            "properties" => { "name" => { "type" => "string" }, "key" => { "type" => "string" } },
            "required" => %w[name],
          },
          "headerName" => { "type" => "string" },
          "usernameSecretRef" => {
            "type" => "object",
            "properties" => { "name" => { "type" => "string" }, "key" => { "type" => "string" } },
            "required" => %w[name],
          },
          "passwordSecretRef" => {
            "type" => "object",
            "properties" => { "name" => { "type" => "string" }, "key" => { "type" => "string" } },
            "required" => %w[name],
          },
        },
      },
      "headers" => { "type" => "object", "additionalProperties" => { "type" => "string" } },
      "headersFrom" => {
        "type" => "array",
        "items" => {
          "type" => "object",
          "properties" => {
            "header" => { "type" => "string" },
            "secretRef" => {
              "type" => "object",
              "properties" => { "name" => { "type" => "string" }, "key" => { "type" => "string" } },
              "required" => %w[name],
            },
          },
          "required" => %w[header secretRef],
        },
      },
      "tls" => {
        "type" => "object",
        "properties" => {
          "caSecretRef" => {
            "type" => "object",
            "properties" => { "name" => { "type" => "string" }, "key" => { "type" => "string" } },
            "required" => %w[name],
          },
        },
      },
      "egress" => {
        "type" => "object",
        "properties" => {
          "cidrs" => { "type" => "array", "items" => { "type" => "string" } },
          "ports" => { "type" => "array", "items" => { "type" => %w[integer string] } },
        },
      },
    },
    "required" => %w[name url],
  },
  "workspace.models.providers.openaiCompat" => {
    "type" => "object",
    "additionalProperties" => false,
    "properties" => {
      "name" => { "type" => "string" },
      "host" => { "type" => "string" },
      "port" => { "type" => %w[integer string] },
      "prefix" => { "type" => "string" },
      "apiKey" => { "type" => "string" },
      "modelMatch" => { "type" => "string" },
      "tls" => { "type" => "boolean" },
    },
    "required" => %w[name host prefix modelMatch],
  },
  "workload.agents.workers" => {
    "type" => "object",
    "additionalProperties" => false,
    "properties" => {
      "graphId" => { "type" => "string" },
      "service" => { "type" => "string" },
      "port" => { "type" => %w[integer string] },
    },
    "required" => %w[graphId service port],
  },
  "platform.telemetry.langfuse.extraProjects" => {
    "type" => "object",
    "additionalProperties" => true,
  },
  "extraManifests" => {
    "type" => %w[object string],
    "description" => "Raw Kubernetes object (map) or templated YAML string.",
  },
}.freeze

EXTRA_ROOT_PROPERTIES = {
  "nameOverride" => { "type" => "string", "description" => "Override chart name." },
  "fullnameOverride" => { "type" => "string", "description" => "Override full release name." },
  "extraManifests" => {
    "type" => "array",
    "description" => "Additional manifests rendered alongside chart output.",
    "items" => STRICT_ARRAY_ITEM_SCHEMAS["extraManifests"],
  },
  "guardrails" => nil, # merged below
}.freeze

def path_key(path)
  path.join(".")
end

def infer_type(value)
  case value
  when Hash then "object"
  when Array then "array"
  when TrueClass, FalseClass then "boolean"
  when Integer then %w[integer string]
  when Float then "number"
  else "string"
  end
end

def open_map?(key, path)
  return true if OPEN_MAP_KEYS.include?(key)
  return true if key.end_with?("Probe")
  return true if path.last == "selector" && path[-2] == "nodes"
  path_key(path) == "global"
end

def schema_for(value, path = [])
  pk = path_key(path)

  if STRING_OR_OBJECT_PATHS.include?(pk)
    return {
      "type" => %w[string object array],
      "description" => "JSON credentials string or structured value for #{pk}.",
    }
  end

  if ENUMS.key?(pk)
    return {
      "type" => "string",
      "enum" => ENUMS[pk],
      "description" => "Allowed values for #{pk}.",
    }
  end

  case value
  when Hash
    props = {}
    value.each do |k, v|
      props[k] = schema_for(v, path + [k])
    end
    if pk == "workspace.policies"
      props["llamaGuard"] = {
        "type" => "object",
        "description" => "Enterprise Llama Guard (reserved; install fails on CE without entitlement).",
        "additionalProperties" => true,
      }
      props["presidio"] = {
        "type" => "object",
        "description" => "Enterprise Presidio masking (reserved; install fails on CE without entitlement).",
        "additionalProperties" => true,
      }
    end
    if pk == "platform.telemetry"
      props["audit"] = {
        "type" => "object",
        "description" => "Enterprise audit sinks (WORM requires Ent).",
        "additionalProperties" => true,
      }
    end
    if pk == "global" && !props.key?("zelkor")
      props["zelkor"] = {
        "type" => "object",
        "description" => "Pro/Ent umbrella hooks (e.g. entitlements).",
        "additionalProperties" => true,
      }
    end
    sch = {
      "type" => "object",
      "description" => pk.empty? ? "Zelkor platform values." : "Values under #{pk}.",
      "properties" => props,
    }
    sch["additionalProperties"] = false unless open_map?(path.last || "", path)
    sch
  when Array
    item_key = pk
    items = STRICT_ARRAY_ITEM_SCHEMAS[item_key]
    items ||= if value.empty?
                { "type" => %w[string object number boolean] }
              else
                schema_for(value.first, path + [0])
              end
    {
      "type" => "array",
      "description" => "List at #{pk}.",
      "items" => items,
    }
  else
    t = infer_type(value)
    desc = "Value for #{pk}."
    if t.is_a?(Array)
      { "type" => t, "description" => desc }
    else
      { "type" => t, "description" => desc }
    end
  end
end

values = YAML.load_file(VALUES_PATH)
root_schema = schema_for(values, [])
root_schema["$schema"] = "https://json-schema.org/draft-07/schema#"
root_schema["additionalProperties"] = false
root_schema["properties"]["nameOverride"] = EXTRA_ROOT_PROPERTIES["nameOverride"]
root_schema["properties"]["fullnameOverride"] = EXTRA_ROOT_PROPERTIES["fullnameOverride"]
root_schema["properties"]["extraManifests"] = EXTRA_ROOT_PROPERTIES["extraManifests"]

if File.file?(V1_STUBS_PATH)
  stubs = YAML.load_file(V1_STUBS_PATH) || {}
  stubs.each do |key, stub_val|
    next if root_schema["properties"].key?(key)

    sch = schema_for(stub_val, [key])
    sch["description"] = "REMOVED in V2 — use platform.* / workspace.* / workload.*. Supplying values fails at render."
    root_schema["properties"][key] = sch
  end
end

File.write(OUT_PATH, JSON.pretty_generate(root_schema) + "\n")
puts "Wrote #{OUT_PATH}"
