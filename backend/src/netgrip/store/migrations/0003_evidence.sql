-- Pages: fetched once, shared by every investigation (V8, V9, D-10). Not event projections.
CREATE TABLE pages (
    url TEXT PRIMARY KEY,
    latest_version_id TEXT
);

CREATE TABLE page_versions (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_sha TEXT NOT NULL,
    text_sha TEXT NOT NULL,
    title TEXT,
    published_at TEXT,
    bytes INTEGER NOT NULL
);
CREATE INDEX page_versions_url ON page_versions(url, fetched_at);

CREATE TABLE investigation_pages (
    investigation_id TEXT NOT NULL,
    page_version_id TEXT NOT NULL,
    PRIMARY KEY (investigation_id, page_version_id)
) WITHOUT ROWID;

CREATE TABLE extractions (
    investigation_id TEXT NOT NULL,
    page_version_id TEXT NOT NULL,
    node_question_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    PRIMARY KEY (investigation_id, page_version_id, node_question_hash)
) WITHOUT ROWID;
