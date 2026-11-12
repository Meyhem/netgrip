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

-- Evidence: event projections (rebuilt from the log). Claims never leave the store (E2).
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    page_version_id TEXT NOT NULL,
    credibility TEXT NOT NULL,       -- Primary | Reputable | Weak
    published_at TEXT,
    origin_key TEXT NOT NULL,        -- original publisher or wire report (V2)
    seq INTEGER NOT NULL
);
CREATE INDEX sources_investigation ON sources(investigation_id, seq);

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    node_id TEXT,
    text TEXT NOT NULL,
    status TEXT NOT NULL,            -- Confirmed | Supported | Unverified | Contested | Refuted
    merged_into TEXT,                -- set when reconciliation found the claim already known
    seq INTEGER NOT NULL
);
CREATE INDEX claims_investigation ON claims(investigation_id, seq);

CREATE TABLE claim_sources (
    investigation_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    stance TEXT NOT NULL,            -- supports | contradicts
    PRIMARY KEY (claim_id, source_id)
) WITHOUT ROWID;

CREATE TABLE contradictions (
    investigation_id TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    PRIMARY KEY (claim_a, claim_b)
) WITHOUT ROWID;
