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
  var flag = metadata(ctx).tool_repeat;
  var repeated = flag === true || String(flag).toLowerCase() === "true";
  return {
    scores: [
      {
        name: "zelkor-tool-repeat",
        value: !repeated,
        dataType: "BOOLEAN",
        comment: repeated ? "identical tool name repeated" : "tool name is not a repeat",
      },
    ],
  };
}
