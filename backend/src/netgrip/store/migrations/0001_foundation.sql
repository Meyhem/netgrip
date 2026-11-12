CREATE TABLE events (
    investigation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    v INTEGER NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    node_id TEXT,
    command_id TEXT,
    data TEXT NOT NULL,
    PRIMARY KEY (investigation_id, seq)
) WITHOUT ROWID;

CREATE TABLE commands (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    type TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX commands_investigation ON commands(investigation_id);

CREATE TABLE investigations (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    state TEXT NOT NULL,
    pause_cause TEXT,
    pause_detail TEXT,
    settings TEXT NOT NULL,
    spending_limit_usd REAL NOT NULL,
    spent_usd REAL NOT NULL DEFAULT 0,
    spend_approximate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    last_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE secrets (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    status TEXT NOT NULL,
    checked_at TEXT,
    message TEXT
);
