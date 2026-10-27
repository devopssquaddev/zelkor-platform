FROM python:3.14.9-slim-trixie AS fetch
ARG OPENCODE_VERSION=1.19.4
ARG TARGETARCH=amd64
# npm registry dist.integrity (sha512) per platform package
ARG OPENCODE_SHA512_AMD64=rQ/l3jmJoxf8ZYnBargg9alURlz6buEilysGODtzkcmcYtcZ91LOgF034oUUHHQl8/y1hbRTDvg6ujqUjQsMXw==
ARG OPENCODE_SHA512_ARM64=bA/QpgwRgv20xVay0b4EGo3IjMQQl4GbODjhXWGUvovoJYYyFosueox2aLASxTbHK6oP1zpUxaZRFhgNrhhfgA==
RUN python - <<'EOF'
import base64, hashlib, os, tarfile, urllib.request
arch = {"amd64": "x64", "arm64": "arm64"}[os.environ["TARGETARCH"]]
want = os.environ["OPENCODE_SHA512_" + os.environ["TARGETARCH"].upper()]
ver = os.environ["OPENCODE_VERSION"]
url = f"https://registry.npmjs.org/opencode-linux-{arch}/-/opencode-linux-{arch}-{ver}.tgz"
data = urllib.request.urlopen(url, timeout=120).read()
got = base64.b64encode(hashlib.sha512(data).digest()).decode()
if got != want:
    raise SystemExit(f"opencode tarball integrity mismatch: {got}")
open("/tmp/oc.tgz", "wb").write(data)
with tarfile.open("/tmp/oc.tgz") as t:
    t.extractall("/tmp/oc", filter="data")
os.makedirs("/opt/opencode/bin", exist_ok=True)
os.replace("/tmp/oc/package/bin/opencode", "/opt/opencode/bin/opencode")
os.chmod("/opt/opencode/bin/opencode", 0o755)
EOF

FROM python:3.14.9-slim-trixie
COPY --from=fetch /opt/opencode /opt/opencode
COPY images/runtime-opencode/opencode.json /opt/zelkor/opencode.json
COPY images/runtime-opencode/entrypoint.sh /opt/zelkor/entrypoint.sh
RUN chmod 0755 /opt/zelkor/entrypoint.sh && chmod -R a+rX /opt/zelkor /opt/opencode \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin zelkor \
    && mkdir -p /app
# Writable state lives under /tmp (emptyDir); the root filesystem can stay read-only.
ENV HOME=/tmp XDG_CONFIG_HOME=/tmp/.config XDG_DATA_HOME=/tmp/.local/share \
    XDG_CACHE_HOME=/tmp/.cache XDG_STATE_HOME=/tmp/.local/state \
    OPENCODE_CONFIG=/opt/zelkor/opencode.json \
    OPENCODE_DISABLE_AUTOUPDATE=true OPENCODE_DISABLE_MODELS_FETCH=true \
    OPENCODE_DISABLE_LSP_DOWNLOAD=true OPENCODE_DISABLE_DEFAULT_PLUGINS=true \
    OPENCODE_DISABLE_CLAUDE_CODE=true
WORKDIR /app
USER 1000
# Customer image: FROM this, COPY AGENTS.md (and agent.json) /app/
ENTRYPOINT ["/opt/zelkor/entrypoint.sh"]
