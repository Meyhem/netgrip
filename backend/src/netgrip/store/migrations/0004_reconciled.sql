-- Claims already reconciled (one evidence.match per claim). Not an event projection: like
-- `extractions`, a cache of paid model work that a rebuild keeps.
CREATE TABLE reconciled_claims (
    investigation_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    PRIMARY KEY (investigation_id, claim_id)
) WITHOUT ROWID;
