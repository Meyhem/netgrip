-- Steering (Phase 6): event projections for the user's interventions.
ALTER TABLE nodes ADD COLUMN paused_from TEXT;           -- status a branch pause interrupted
ALTER TABLE claims ADD COLUMN withdrawn INTEGER NOT NULL DEFAULT 0;
ALTER TABLE investigations ADD COLUMN focus_node_id TEXT;
ALTER TABLE investigations ADD COLUMN ended_early INTEGER NOT NULL DEFAULT 0;
ALTER TABLE investigations ADD COLUMN nodes_extra INTEGER NOT NULL DEFAULT 0;  -- go deeper
ALTER TABLE instructions ADD COLUMN waiting_for TEXT;
