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

function nameList(ctx) {
  var raw = metadata(ctx).tool_names;
  if (raw == null) return null;
  var list = raw;
  if (typeof raw === "string") {
    try {
      list = JSON.parse(raw);
    } catch (err) {
      return null;
    }
  }
  if (!Array.isArray(list)) return null;
  for (var i = 0; i < list.length; i++) {
    if (typeof list[i] !== "string") return null;
  }
  return list;
}

function evaluate(ctx) {
  var names = nameList(ctx);
  var ok = Array.isArray(names);
  return {
    scores: [
      {
        name: "zelkor-tool-names",
        value: ok,
        dataType: "BOOLEAN",
        comment: ok ? "tool_names is a list of strings" : "tool_names is missing or not names only",
      },
    ],
  };
}
