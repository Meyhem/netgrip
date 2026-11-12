-- Recovery (Phase 4 Task 8): the relevance gate ran on this Completed node (on-topic via
-- `node.relevance_checked`, off-topic via `node.off_topic`). Without it a restart cannot tell a
-- node whose return work the killed process still owed.
ALTER TABLE nodes ADD COLUMN relevance_checked INTEGER NOT NULL DEFAULT 0;
