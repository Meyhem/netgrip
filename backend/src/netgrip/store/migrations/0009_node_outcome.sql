-- How each node finished and who excluded it (Phase 5), so the board opens from the snapshot
-- without the events: the seq and time of its last `node.completed`/`node.failed`, the failure
-- reason, and the actor, time and instruction of the `node.inclusion_changed` that excluded it.
-- Event projections; existing rows are filled from the log below.
ALTER TABLE nodes ADD COLUMN finished_seq INTEGER;
ALTER TABLE nodes ADD COLUMN finished_at TEXT;
ALTER TABLE nodes ADD COLUMN failure_reason TEXT;
ALTER TABLE nodes ADD COLUMN excluded_by TEXT;        -- user / replan
ALTER TABLE nodes ADD COLUMN excluded_at TEXT;
ALTER TABLE nodes ADD COLUMN excluded_instruction_id TEXT;

UPDATE nodes SET finished_seq = (
    SELECT MAX(e.seq) FROM events e
    WHERE e.investigation_id = nodes.investigation_id AND e.node_id = nodes.id
      AND e.type IN ('node.completed', 'node.failed')
) WHERE status IN ('Completed', 'Failed');
UPDATE nodes SET finished_at = (
    SELECT e.at FROM events e WHERE e.investigation_id = nodes.investigation_id AND e.seq = nodes.finished_seq
) WHERE finished_seq IS NOT NULL;
UPDATE nodes SET failure_reason = (
    SELECT json_extract(e.data, '$.reason') FROM events e
    WHERE e.investigation_id = nodes.investigation_id AND e.seq = nodes.finished_seq
) WHERE status = 'Failed' AND finished_seq IS NOT NULL;

CREATE TEMP TABLE _excluded AS
SELECT n.id AS node_id,
       (SELECT e.seq FROM events e
        WHERE e.investigation_id = n.investigation_id AND e.type = 'node.inclusion_changed'
          AND EXISTS (SELECT 1 FROM json_each(e.data, '$.node_ids') j WHERE j.value = n.id)
        ORDER BY e.seq DESC LIMIT 1) AS seq,
       n.investigation_id AS investigation_id
FROM nodes n WHERE n.inclusion != 'Included';
UPDATE nodes SET
    excluded_by = (SELECT json_extract(e.data, '$.by') FROM _excluded x JOIN events e
                   ON e.investigation_id = x.investigation_id AND e.seq = x.seq WHERE x.node_id = nodes.id),
    excluded_at = (SELECT e.at FROM _excluded x JOIN events e
                   ON e.investigation_id = x.investigation_id AND e.seq = x.seq WHERE x.node_id = nodes.id),
    excluded_instruction_id = (SELECT json_extract(e.data, '$.instruction_id') FROM _excluded x JOIN events e
                   ON e.investigation_id = x.investigation_id AND e.seq = x.seq WHERE x.node_id = nodes.id)
WHERE inclusion != 'Included';
DROP TABLE _excluded;
