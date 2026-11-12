ALTER TABLE investigations ADD COLUMN root_goal TEXT;
ALTER TABLE investigations ADD COLUMN plan_failed_reason TEXT;

CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    display_id TEXT NOT NULL,
    parent_id TEXT,
    kind TEXT NOT NULL,
    question TEXT NOT NULL,
    justification TEXT,
    out_of_scope TEXT,   -- JSON
    done_when TEXT,      -- JSON
    depth INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Proposed',
    inclusion TEXT NOT NULL DEFAULT 'Included',
    budget TEXT,         -- JSON
    activity TEXT,
    verdict TEXT,        -- JSON
    brief TEXT,
    spent_usd REAL NOT NULL DEFAULT 0,
    instruction_count INTEGER NOT NULL DEFAULT 0,
    plan_version_added INTEGER,
    proposed_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    seq INTEGER NOT NULL  -- event seq of node.proposed: stable ordering
);
CREATE INDEX nodes_investigation ON nodes(investigation_id, seq);

CREATE TABLE node_deps (
    investigation_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    PRIMARY KEY (node_id, depends_on_id)
) WITHOUT ROWID;
CREATE INDEX node_deps_investigation ON node_deps(investigation_id);

CREATE TABLE instructions (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    node_id TEXT,
    text TEXT NOT NULL,
    state TEXT NOT NULL,   -- queued / applied / undone
    queued_seq INTEGER NOT NULL,
    applied_seq INTEGER,
    diff TEXT,             -- JSON
    undone INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX instructions_investigation ON instructions(investigation_id, queued_seq);

CREATE TABLE premises (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    text TEXT NOT NULL,
    node_id TEXT,
    outcome TEXT,
    seq INTEGER NOT NULL
);
CREATE INDEX premises_investigation ON premises(investigation_id, seq);

CREATE TABLE plan_versions (
    investigation_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    instruction_id TEXT,
    diff TEXT NOT NULL,    -- JSON
    PRIMARY KEY (investigation_id, version)
) WITHOUT ROWID;
