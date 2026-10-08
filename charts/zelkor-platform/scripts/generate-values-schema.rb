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
      "name" => { "type" => "string", "description" => "Backend name prefix for MCPRoute tool routing." },
      "service" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "name" => { "type" => "string" },
          "port" => { "type" => %w[integer string] },
        },
        "required" => %w[name port],
      },
      "fqdn" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "hostname" => { "type" => "string" },
          "port" => { "type" => %w[integer string] },
        },
        "required" => %w[hostname port],
      },
      "path" => { "type" => "string", "description" => "MCP path on the backend (default /mcp)." },
      "apiKey" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "secretRef" => {
            "type" => "object",
            "additionalProperties" => false,
            "properties" => {
              "name" => { "type" => "string" },
            },
            "required" => %w[name],
          },
          "header" => { "type" => "string", "description" => "Empty or Authorization for Bearer; else custom header name." },
        },
        "required" => %w[secretRef],
      },
      "tls" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "caSecretRef" => { "type" => "string", "description" => "Secret name for CA cert (FQDN backends)." },
        },
      },
      "toolSelector" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "include" => { "type" => "array", "items" => { "type" => "string" } },
          "includeRegex" => { "type" => "array", "items" => { "type" => "string" } },
        },
      },
      "forwardHeaders" => {
        "type" => "array",
        "items" => {
          "oneOf" => [
            { "type" => "string" },
            {
              "type" => "object",
              "additionalProperties" => false,
              "properties" => { "name" => { "type" => "string" } },
              "required" => %w[name],
            },
          ],
        },
        "description" => "Client headers to forward; Authorization is forbidden.",
      },
      "egress" => {
        "type" => "object",
        "additionalProperties" => false,
        "properties" => {
          "cidrs" => { "type" => "array", "items" => { "type" => "string" } },
          "ports" => { "type" => "array", "items" => { "type" => %w[integer string] } },
        },
      },
    },
    "required" => %w[name],
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

def open_map?(key, path, value)
  return true if value.is_a?(Hash) && value.empty?
  return true if OPEN_MAP_KEYS.include?(key)
  return true if key.end_with?("Probe")
  return true if path.last == "selector" && path[-2] == "nodes"
  path_key(path) == "global"
end

def merge_prior_constraints(node, prior)
  return unless node.is_a?(Hash) && prior.is_a?(Hash)
  %w[minimum maximum minLength maxLength pattern].each do |key|
    node[key] = prior[key] if prior.key?(key) && !node.key?(key)
  end
  nprops = node["properties"]
  pprops = prior["properties"]
  return unless nprops.is_a?(Hash) && pprops.is_a?(Hash)

  pprops.each do |key, child|
    if nprops.key?(key)
      merge_prior_constraints(nprops[key], child)
    else
      nprops[key] = child
    end
  end
end

def prior_description(path)
  return nil unless defined?(PRIOR_SCHEMA) && PRIOR_SCHEMA
  node = PRIOR_SCHEMA
  path.each do |key|
    return nil unless node.is_a?(Hash)
    props = node["properties"]
    return nil unless props.is_a?(Hash)
    node = props[key.to_s]
  end
  return nil unless node.is_a?(Hash)
  node["description"]
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
    sch["additionalProperties"] = false unless open_map?(path.last || "", path, value)
    if (kept = prior_description(path))
      sch["description"] = kept
    end
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
      "description" => prior_description(path) || "List at #{pk}.",
      "items" => items,
    }
  else
    t = infer_type(value)
    desc = prior_description(path) || "Value for #{pk}."
    if t.is_a?(Array)
      { "type" => t, "description" => desc }
    else
      { "type" => t, "description" => desc }
    end
  end
end

values = YAML.load_file(VALUES_PATH)
PRIOR_SCHEMA = File.file?(OUT_PATH) ? JSON.parse(File.read(OUT_PATH)) : nil
root_schema = schema_for(values, [])
root_schema["$schema"] = "https://json-schema.org/draft-07/schema#"
root_schema["additionalProperties"] = false
root_schema["properties"]["nameOverride"] = EXTRA_ROOT_PROPERTIES["nameOverride"]
root_schema["properties"]["fullnameOverride"] = EXTRA_ROOT_PROPERTIES["fullnameOverride"]
root_schema["properties"]["extraManifests"] = EXTRA_ROOT_PROPERTIES["extraManifests"]
merge_prior_constraints(root_schema, PRIOR_SCHEMA) if PRIOR_SCHEMA

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
