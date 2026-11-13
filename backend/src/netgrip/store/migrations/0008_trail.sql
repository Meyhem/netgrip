-- The trail of each node (Phase 5): one row per step, numbered from 1 per node. A step opens
-- with `node.activity` (or, for a step without one, with its `node.step_completed`) and closes
-- at its `node.step_completed`, the next activity, or the node leaving Running. An event
-- projection, rebuilt from the log. Investigations from before this migration get their trail
-- after a rebuild (POST /api/system/rebuild).
CREATE TABLE node_steps (
    investigation_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    name TEXT,                    -- the step function: plan, search, read, extract, ...
    kind TEXT,                    -- from node.step_completed: decision, search, fetch, ...
    activity TEXT,                -- from node.activity; NULL for a step without one
    detail TEXT,
    summary TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    route TEXT,
    page_version_id TEXT,
    retry TEXT,                   -- JSON {n, m}
    instruction_applied TEXT NOT NULL DEFAULT '[]',  -- JSON [instruction_id], after this step
    PRIMARY KEY (node_id, step)
) WITHOUT ROWID;
CREATE INDEX node_steps_investigation ON node_steps(investigation_id);
