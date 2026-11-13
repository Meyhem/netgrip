-- The stored report (Phase 8): one per investigation, an event projection of `report.created`
-- (its `body` is the structured report), so a rebuild keeps it.
CREATE TABLE reports (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    body TEXT NOT NULL      -- JSON
);
