-- Recovery (Phase 4 Task 8): the relevance gate ran on this Completed node (on-topic via
-- `node.relevance_checked`, off-topic via `node.off_topic`). Without it a restart cannot tell a
-- node whose return work the killed process still owed.
ALTER TABLE nodes ADD COLUMN relevance_checked INTEGER NOT NULL DEFAULT 0;
-- Existing Completed nodes: treat the gate as run (they predate this record; not re-checked).
UPDATE nodes SET relevance_checked = 1 WHERE status = 'Completed';
-- The orchestrator decided on this Failed node (auto retry via `node.reset`, or left Failed via
-- `node.left_failed`). Cleared by every `node.failed`.
ALTER TABLE nodes ADD COLUMN failure_handled INTEGER NOT NULL DEFAULT 0;
UPDATE nodes SET failure_handled = 1 WHERE status = 'Failed';
