-- The orchestrator decided on this Failed node (auto retry via `node.reset`, or left Failed via
-- `node.left_failed`). Cleared by every `node.failed`. Its own migration: 0006 was already
-- applied in the field.
ALTER TABLE nodes ADD COLUMN failure_handled INTEGER NOT NULL DEFAULT 0;
-- Existing data predates both records: treat the gate and the failure decision as done.
UPDATE nodes SET failure_handled = 1 WHERE status = 'Failed';
UPDATE nodes SET relevance_checked = 1 WHERE status = 'Completed';
