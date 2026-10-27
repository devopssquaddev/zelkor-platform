-- zelkor-sidecar: tenant-scoped Agent Protocol state for non-Aegra runtimes (CE-14).
-- Every query filters by tenant_id AND graph_id. The runtime container never connects here.

CREATE TABLE IF NOT EXISTS zelkor_threads (
    thread_id          UUID PRIMARY KEY,
    tenant_id          TEXT NOT NULL,
    graph_id           TEXT NOT NULL,
    metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             TEXT NOT NULL DEFAULT 'idle',
    runtime_session_id TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS zelkor_threads_owner_idx
    ON zelkor_threads (tenant_id, graph_id, created_at DESC);
CREATE INDEX IF NOT EXISTS zelkor_threads_metadata_idx
    ON zelkor_threads USING GIN (metadata jsonb_path_ops);

CREATE TABLE IF NOT EXISTS zelkor_runs (
    run_id         UUID PRIMARY KEY,
    thread_id      UUID NOT NULL REFERENCES zelkor_threads (thread_id) ON DELETE CASCADE,
    tenant_id      TEXT NOT NULL,
    graph_id       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    error          TEXT,
    runtime_run_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS zelkor_runs_thread_idx ON zelkor_runs (thread_id, created_at);

CREATE TABLE IF NOT EXISTS zelkor_messages (
    seq        BIGSERIAL PRIMARY KEY,
    thread_id  UUID NOT NULL REFERENCES zelkor_threads (thread_id) ON DELETE CASCADE,
    run_id     UUID,
    message    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS zelkor_messages_thread_idx ON zelkor_messages (thread_id, seq);

-- Durable run events: a DB sequence orders them; event_key makes replays idempotent.
CREATE TABLE IF NOT EXISTS zelkor_run_events (
    seq        BIGSERIAL PRIMARY KEY,
    run_id     UUID NOT NULL REFERENCES zelkor_runs (run_id) ON DELETE CASCADE,
    event_key  TEXT NOT NULL,
    event      TEXT NOT NULL,
    data       JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, event_key)
);
