const PREFIXES = ["postgres__", "qdrant__", "sandbox__", "aigateway__"];

function metadata(ctx) {
  var raw = ctx && ctx.observation ? ctx.observation.metadata : null;
  if (raw == null) return {};
  if (typeof raw === "string") {
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }
  return raw;
}

function evaluate(ctx) {
  var name = String(metadata(ctx).tool_name || "");
  var ok = false;
  for (var i = 0; i < PREFIXES.length; i++) {
    if (name.indexOf(PREFIXES[i]) === 0) ok = true;
  }
  return {
    scores: [
      {
        name: "zelkor-mcp-prefix",
        value: ok,
        dataType: "BOOLEAN",
        comment: ok ? "native MCP prefix" : "tool name has no MCP prefix",
      },
    ],
  };
}
