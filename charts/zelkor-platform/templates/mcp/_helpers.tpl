{{- define "zelkor-platform.mcp.pythonStart" -}}
pip install --no-cache-dir psycopg2-binary httpx >/dev/null 2>&1 || true
mkdir -p /app/mcp/common /app/mcp/wrappers /app/mcp/sandbox /app/mcp/gateway
cp /code/*.py /app/mcp/common/ 2>/dev/null || true
cp /code/postgres_server.py /app/mcp/wrappers/ 2>/dev/null || true
cp /code/qdrant_server.py /app/mcp/wrappers/ 2>/dev/null || true
cp /code/server.py /app/mcp/sandbox/ 2>/dev/null || true
cp /code/worker.py /app/mcp/sandbox/ 2>/dev/null || true
cp /code/pool_manager.py /app/mcp/sandbox/ 2>/dev/null || true
cp /code/gateway_server.py /app/mcp/gateway/server.py 2>/dev/null || true
{{- end }}
