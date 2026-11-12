-- The orchestrator's gates (Phase 4 Task 5): rejection with its reason and duplicate link (O1),
-- the off-topic flag (E3), the auto-retry hint (D-19) and why the investigation concluded (O3).
ALTER TABLE nodes ADD COLUMN rejection_reason TEXT;
ALTER TABLE nodes ADD COLUMN duplicate_of TEXT;
ALTER TABLE nodes ADD COLUMN off_topic INTEGER NOT NULL DEFAULT 0;
ALTER TABLE nodes ADD COLUMN retry_hint TEXT;
ALTER TABLE investigations ADD COLUMN cut_short_by TEXT;
