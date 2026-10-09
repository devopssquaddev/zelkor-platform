var STEP_BUDGET = 25;

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

function toolNames(ctx) {
  var raw = metadata(ctx).tool_names;
  if (raw == null) return [];
  var list = raw;
  if (typeof raw === "string") {
    try {
      list = JSON.parse(raw);
    } catch (err) {
      return null;
    }
  }
  if (!Array.isArray(list)) return null;
  return list;
}

function evaluate(ctx) {
  var names = toolNames(ctx);
  var ok = Array.isArray(names) && names.length <= STEP_BUDGET;
  return {
    scores: [
      {
        name: "zelkor-step-budget",
        value: ok,
        dataType: "BOOLEAN",
        comment: ok ? "tool name count is within 25" : "tool name count exceeds 25",
      },
    ],
  };
}
