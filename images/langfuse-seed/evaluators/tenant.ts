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
  var meta = metadata(ctx);
  var user = String(meta.user_id || "").trim();
  var tenant = String(meta.tenant_id || "").trim();
  var ok = !!(user || tenant);
  return {
    scores: [
      {
        name: "zelkor-tenant-userid",
        value: ok,
        dataType: "BOOLEAN",
        comment: ok ? "user or tenant metadata present" : "user and tenant metadata missing",
      },
    ],
  };
}
